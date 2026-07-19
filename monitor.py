"""
Radar de Pautas - monitor de fontes por clube
------------------------------------------------
Le config.json (fontes por clube), verifica o que ha de novo
desde a ultima execucao (guardado em state/state.json) e dispara
uma notificacao no WhatsApp (via CallMeBot) para cada item novo.

Uso local:
    export CALLMEBOT_PHONE="55XXXXXXXXXXX"
    export CALLMEBOT_APIKEY="123456"
    python monitor.py

Em producao isso roda via GitHub Actions (ver .github/workflows/monitor.yml),
a cada N minutos, sem precisar de servidor proprio.
"""

import html
import json
import os
import re
import sys
from pathlib import Path

import feedparser
import requests

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state" / "state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

MAX_ITEMS_PER_SOURCE = 10
MAX_IDS_KEPT_PER_SOURCE = 300

# janela de HTML apos o link, onde procuramos o titulo da noticia (h1-h6)
TITLE_SEARCH_WINDOW = 700
TITLE_TAG_PREFERRED_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.DOTALL)
TITLE_TAG_ANY_RE = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def extract_nearby_title(html_text: str, end_pos: int, fallback: str) -> str:
    window = html_text[end_pos: end_pos + TITLE_SEARCH_WINDOW]
    for pattern in (TITLE_TAG_PREFERRED_RE, TITLE_TAG_ANY_RE):
        m = pattern.search(window)
        if m:
            cleaned = html.unescape(HTML_TAG_RE.sub("", m.group(1)))
            cleaned = " ".join(cleaned.split())
            if cleaned:
                return cleaned
    return fallback


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_rss(source: dict) -> list[dict]:
    feed = feedparser.parse(source["url"])
    items = []
    for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
        link = entry.get("link")
        if not link:
            continue
        items.append(
            {
                "id": entry.get("id") or link,
                "title": (entry.get("title") or "").strip(),
                "link": link,
            }
        )
    return items


def fetch_scrape_list(source: dict) -> list[dict]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    # o Content-Type de alguns sites nao declara charset, e requests cai pra
    # ISO-8859-1 por padrao mesmo quando o conteudo real e UTF-8 (mojibake)
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    page_html = resp.text

    pattern = source["url_pattern"]

    items = []
    seen_links = set()
    for m in re.finditer(pattern, page_html):
        raw = m.group(0)
        link = raw if raw.startswith("http") else source.get("base_url", "").rstrip("/") + "/" + raw.lstrip("/")
        if link in seen_links:
            continue
        seen_links.add(link)
        title = extract_nearby_title(page_html, m.end(), source["name"])
        items.append({"id": link, "title": title, "link": link})
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    return items


def get_items(source: dict) -> list[dict]:
    source_type = source["type"]
    if source_type in ("rss", "youtube_rss"):
        return fetch_rss(source)
    if source_type == "scrape_list":
        return fetch_scrape_list(source)
    raise ValueError(f"Tipo de fonte desconhecido: {source_type}")


def notify_whatsapp(message: str):
    phone = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    if not phone or not apikey:
        print("[AVISO] CALLMEBOT_PHONE/CALLMEBOT_APIKEY nao configurados. "
              "Mensagem que seria enviada:")
        print(message)
        print("-" * 40)
        return

    url = "https://api.callmebot.com/whatsapp.php"
    params = {"phone": phone, "text": message, "apikey": apikey}
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        print(f"[OK] Notificacao enviada: {message.splitlines()[0]}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar WhatsApp: {e}")


def run():
    config = load_json(CONFIG_PATH, {"clubs": {}})
    state = load_json(STATE_PATH, {})

    total_new = 0

    for club_key, club in config["clubs"].items():
        sources = club.get("sources", [])
        if not sources:
            continue

        club_state = state.setdefault(club_key, {})

        for source in sources:
            source_key = source["id"]
            already_seen = set(club_state.get(source_key, []))
            is_first_run = source_key not in club_state

            try:
                items = get_items(source)
            except Exception as e:
                print(f"[ERRO] {club['name']} / {source['name']}: {e}")
                continue

            new_items = [it for it in items if it["id"] not in already_seen]

            # do mais antigo para o mais novo, pra notificar na ordem certa
            for it in reversed(new_items):
                if not is_first_run:
                    msg = (
                        f"\U0001F6A8 {club['name']} - {source['name']}\n"
                        f"{it['title']}\n"
                        f"{it['link']}"
                    )
                    notify_whatsapp(msg)
                    total_new += 1
                already_seen.add(it["id"])

            if is_first_run and new_items:
                print(f"[INFO] Primeira execucao de '{source['name']}' "
                      f"({club['name']}): {len(new_items)} itens registrados, "
                      f"sem notificar.")

            # nao deixa a lista de ids crescer pra sempre
            club_state[source_key] = list(already_seen)[-MAX_IDS_KEPT_PER_SOURCE:]

    save_json(STATE_PATH, state)
    print(f"[FIM] {total_new} novidade(s) notificada(s) nesta execucao.")


if __name__ == "__main__":
    run()
