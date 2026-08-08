"""
Radar de Pautas - monitor de fontes por clube
------------------------------------------------
Le config.json (fontes por clube), verifica o que ha de novo
desde a ultima execucao (guardado em state/state.json) e dispara
uma notificacao no Telegram (via bot do Telegram) para cada item novo.

Uso local:
    export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
    export TELEGRAM_CHAT_ID="123456789"
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

# No Windows a saida padrao e cp1252 e quebra ao imprimir emoji (o 🚨 das
# notificacoes). Como o print vem depois do envio, isso fazia uma mensagem
# entregue com sucesso ser reportada como falha.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

MAX_ITEMS_PER_SOURCE = 10
MAX_IDS_KEPT_PER_SOURCE = 300

# janela de HTML apos o link, onde procuramos o titulo da noticia (h1-h6).
# Alguns sites colocam <img> enormes entre o link e o titulo; nesses casos da
# pra aumentar so naquela fonte, com "title_window" na config.
TITLE_SEARCH_WINDOW = 700
TITLE_TAG_PREFERRED_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.DOTALL)
TITLE_TAG_ANY_RE = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def extract_nearby_title(html_text: str, end_pos: int,
                         window_size: int = TITLE_SEARCH_WINDOW,
                         custom_pattern: str | None = None) -> str | None:
    """Devolve o titulo achado perto do link, ou None se nao achar."""
    window = html_text[end_pos: end_pos + window_size]
    # alguns sites nao usam h1-h6 no titulo da chamada (ex: <div class=
    # "box-title">); nesses da pra dizer na config onde o titulo esta
    padroes = (TITLE_TAG_PREFERRED_RE, TITLE_TAG_ANY_RE)
    if custom_pattern:
        padroes = (re.compile(custom_pattern, re.DOTALL),) + padroes
    for pattern in padroes:
        m = pattern.search(window)
        if m:
            cleaned = html.unescape(HTML_TAG_RE.sub("", m.group(1)))
            cleaned = " ".join(cleaned.split())
            if cleaned:
                return cleaned
    return None


def item_cap(source: dict) -> int:
    """Quantos itens varrer na origem.

    Com filtro por palavra-chave vale varrer bem mais antes de peneirar,
    senao a noticia do clube pode ficar de fora do corte por causa do que
    os outros times publicaram na mesma pagina.
    """
    if source.get("filter_keywords") or source.get("exclude_keywords"):
        return MAX_ITEMS_PER_SOURCE * 5
    return MAX_ITEMS_PER_SOURCE


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
    for entry in feed.entries[:item_cap(source)]:
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
        title = extract_nearby_title(
            page_html, m.end(),
            source.get("title_window", TITLE_SEARCH_WINDOW),
            source.get("title_pattern"),
        )
        item = {"id": link, "title": title or source["name"], "link": link}
        if title is None:
            # marca que o titulo e so o nome da fonte, pra esse texto nao
            # entrar na peneira de palavra-chave (o nome costuma conter o
            # proprio nome do clube, o que deixaria passar qualquer coisa)
            item["title_fallback"] = True
        items.append(item)
        if len(items) >= item_cap(source):
            break
    return items


def fetch_json_list(source: dict) -> list[dict]:
    """Le uma API que devolve JSON (mais estavel que raspar HTML).

    Campos esperados na config da fonte:
      items_path    - caminho ate a lista, separado por ponto (ex: "results.noticias")
      id_field      - campo usado como identificador unico
      title_field   - campo com o titulo
      link_template - molde do link, com {campo} preenchido pelo item
    """
    resp = requests.get(source["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    for key in source.get("items_path", "").split("."):
        if key:
            data = data[key]

    items = []
    for entry in data[:item_cap(source)]:
        items.append(
            {
                "id": str(entry[source.get("id_field", "id")]),
                "title": str(entry[source.get("title_field", "titulo")]).strip(),
                "link": source["link_template"].format(**entry),
            }
        )
    return items


def matches_keywords(item: dict, keywords: list[str]) -> bool:
    partes = [item.get("link", "")]
    if not item.get("title_fallback"):
        partes.append(item.get("title", ""))
    alvo = " ".join(partes).lower()
    return any(k.lower() in alvo for k in keywords)


def get_items(source: dict) -> list[dict]:
    source_type = source["type"]
    if source_type in ("rss", "youtube_rss"):
        items = fetch_rss(source)
    elif source_type == "scrape_list":
        items = fetch_scrape_list(source)
    elif source_type == "json_list":
        items = fetch_json_list(source)
    else:
        raise ValueError(f"Tipo de fonte desconhecido: {source_type}")

    # fontes que misturam varios clubes (ex: caderno de esportes regional)
    # podem restringir o que interessa por palavra-chave
    keywords = source.get("filter_keywords")
    if keywords:
        items = [it for it in items if matches_keywords(it, keywords)]

    # assuntos que nunca viram pauta do canal (ex: futebol feminino, base).
    # A excecao resgata o que toca o time principal: "sobe do sub-20 para o
    # profissional" e pauta, mesmo casando com a palavra excluida.
    excluir = source.get("exclude_keywords")
    if excluir:
        resgate = source.get("exclude_except", [])
        items = [
            it for it in items
            if not matches_keywords(it, excluir)
            or (resgate and matches_keywords(it, resgate))
        ]

    return items[:MAX_ITEMS_PER_SOURCE]


def notify_telegram(message: str):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("[AVISO] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID nao configurados. "
              "Mensagem que seria enviada:")
        print(message)
        print("-" * 40)
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        r = requests.post(url, data=payload, timeout=20)
        r.raise_for_status()
        print(f"[OK] Notificacao enviada: {message.splitlines()[0]}")
    except Exception as e:
        print(f"[ERRO] Falha ao enviar Telegram: {e}")


def run():
    config = load_json(CONFIG_PATH, {"clubs": {}})
    state = load_json(STATE_PATH, {})

    # assuntos descartados em todas as fontes de todos os clubes, e as
    # palavras que resgatam o item mesmo tendo casado com a exclusao
    excluir_global = config.get("exclude_keywords_global", [])
    resgate_global = config.get("exclude_except_global", [])

    total_new = 0

    for club_key, club in config["clubs"].items():
        sources = club.get("sources", [])
        if not sources:
            continue

        club_state = state.setdefault(club_key, {})

        for source in sources:
            if excluir_global:
                source = {
                    **source,
                    "exclude_keywords": list(source.get("exclude_keywords", []))
                    + excluir_global,
                    "exclude_except": list(source.get("exclude_except", []))
                    + resgate_global,
                }
            source_key = source["id"]
            # seen_ids guarda a ordem de chegada (mais antigo -> mais novo), pra
            # o corte no fim descartar de fato os mais antigos. O set e so pra
            # consulta rapida.
            seen_ids = list(club_state.get(source_key, []))
            already_seen = set(seen_ids)
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
                    notify_telegram(msg)
                    total_new += 1
                if it["id"] not in already_seen:
                    already_seen.add(it["id"])
                    seen_ids.append(it["id"])

            if is_first_run and new_items:
                print(f"[INFO] Primeira execucao de '{source['name']}' "
                      f"({club['name']}): {len(new_items)} itens registrados, "
                      f"sem notificar.")

            # nao deixa a lista crescer pra sempre; como seen_ids esta em ordem
            # de chegada, o corte descarta os mais antigos e mantem os recentes
            club_state[source_key] = seen_ids[-MAX_IDS_KEPT_PER_SOURCE:]

    save_json(STATE_PATH, state)
    print(f"[FIM] {total_new} novidade(s) notificada(s) nesta execucao.")


if __name__ == "__main__":
    run()
