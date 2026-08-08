"""
Executa o Radar de Pautas nesta maquina e sincroniza o historico com o GitHub.
-----------------------------------------------------------------------------
Roda pela Tarefa Agendada do Windows a cada 15 minutos. Serve para receber a
notificacao rapido enquanto o PC esta ligado -- o GitHub Actions continua
rodando como rede de seguranca para quando ele estiver desligado.

Os dois compartilham o mesmo state/state.json pelo repositorio: antes de rodar
puxamos o historico (git pull) e no fim devolvemos (git push). Assim o que um
ja avisou o outro nao repete.

As credenciais ficam em local.env (fora do Git), no formato:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).parent
ENV_FILE = REPO / "local.env"
LOG_FILE = REPO / "local_run.log"
MAX_LOG_BYTES = 1_000_000

# evita piscar janela de console a cada execucao (rodamos via pythonw)
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def log(msg: str) -> None:
    carimbo = datetime.now().strftime("%d/%m %H:%M:%S")
    linha = f"[{carimbo}] {msg}"
    print(linha)
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
            # nao deixa o log crescer pra sempre: mantem so a metade final
            texto = LOG_FILE.read_text(encoding="utf-8", errors="replace")
            LOG_FILE.write_text(texto[len(texto) // 2:], encoding="utf-8")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def git(*args, timeout=120):
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True,
        timeout=timeout, creationflags=NO_WINDOW,
    )


def carregar_credenciais() -> bool:
    if not ENV_FILE.exists():
        log(f"ERRO: {ENV_FILE.name} nao encontrado. Sem ele nao da pra notificar.")
        return False
    for linha in ENV_FILE.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ[chave.strip()] = valor.strip()
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        log("ERRO: TELEGRAM_BOT_TOKEN ausente no local.env.")
        return False
    return True


def sincronizar_antes() -> None:
    """Puxa o historico do GitHub pra nao repetir o que ja foi avisado la."""
    # descarta alteracao local do state pra o pull nunca travar por conflito
    git("checkout", "--", "state/state.json")
    # --autostash guarda qualquer outra alteracao pendente e devolve depois,
    # senao um arquivo mexido no repo faz o pull abortar e a gente roda com
    # historico velho (o que gera notificacao repetida)
    r = git("pull", "--rebase", "--autostash", "origin", "main")
    if r.returncode != 0:
        log(f"AVISO: git pull falhou ({r.stderr.strip()[:120]}). "
            "Rodando assim mesmo -- pode repetir notificacao.")


def devolver_estado() -> None:
    """Devolve o historico atualizado, pro GitHub Actions nao repetir."""
    git("add", "state/state.json")
    if git("diff", "--staged", "--quiet").returncode == 0:
        return  # nada mudou, nao ha o que enviar

    git("commit", "-m", "Atualiza estado do radar (execucao local) [skip ci]")
    if git("push").returncode == 0:
        return

    # alguem (o GitHub Actions) enviou antes: rebase em cima e tenta de novo
    log("push recusado, tentando de novo apos rebase...")
    if git("pull", "--rebase", "--autostash", "origin", "main").returncode == 0:
        if git("push").returncode == 0:
            log("push concluido na segunda tentativa.")
            return
    log("AVISO: nao consegui enviar o estado. A proxima execucao tenta de novo.")


def rodar_monitor() -> None:
    r = subprocess.run(
        [sys.executable, str(REPO / "monitor.py")],
        cwd=REPO, capture_output=True, text=True, timeout=600,
        creationflags=NO_WINDOW,
    )
    for linha in (r.stdout or "").splitlines():
        if linha.strip():
            log(linha.rstrip())
    if r.returncode != 0:
        log(f"ERRO no monitor.py: {(r.stderr or '')[-300:]}")


def main() -> int:
    if not carregar_credenciais():
        return 1
    sincronizar_antes()
    rodar_monitor()
    devolver_estado()
    return 0


if __name__ == "__main__":
    sys.exit(main())
