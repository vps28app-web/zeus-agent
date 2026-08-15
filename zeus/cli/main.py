"""Interactive CLI for Zeus."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import ANSI

from zeus.core.agent import run_agent, run_summary
from zeus.core.team import create_default_team, Team, Worker
from zeus.memory.session_log import get_logger
from zeus.observability import get_metrics
from zeus.tools import terminal, file, web, memory_tools, sandbox_client, sandbox, git, code_execution, browser, database, scheduler  # noqa: F401


def _load_env() -> None:
    """Load .env from ~/.zeus/.env or the project root if present."""
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    paths = [zeus_home / ".env", Path.cwd() / ".env"]
    for env_file in paths:
        if env_file.exists():
            load_dotenv(env_file, override=False)


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h{minutes:02d}m"


def _color(text: str, code: int) -> str:
    return f"\033[{code}m{text}\033[0m"


def _visible_width(text: str) -> int:
    """Return visible width of a string, stripping ANSI escape codes."""
    import re
    return len(re.sub(r"\x1b\[[0-9;]*m", "", text))


def _pad_center(text: str, width: int) -> str:
    vis = _visible_width(text)
    pad = width - vis
    left = pad // 2
    right = pad - left
    return " " * left + text + " " * right


def _pad_left(text: str, width: int) -> str:
    vis = _visible_width(text)
    pad = width - vis
    return text + " " * pad


def _print_banner(logger, metrics) -> None:
    """Print a styled startup banner with session info inside a double-line box."""
    model = os.getenv("ZEUS_MODEL", "unknown")
    provider = os.getenv("ZEUS_PROVIDER", "unknown")
    snap = metrics.snapshot()
    duration = _format_duration(time.time() - snap.get("started_at", time.time()))

    zeus_ascii = [
        _color('███████╗ ███████╗ ██   ██ ███████╗', 36),
        _color('╚══███╔╝ ██╔════╝ ██   ██ ██╔════╝', 36),
        _color('  ███╔╝  █████╗   ██   ██ ███████╗', 36),
        _color(' ███╔╝   ██╔══╝   ██   ██ ╚════██║', 36),
        _color('███████╗ ███████╗ ╚████╔╝ ███████║', 36),
        _color('╚══════╝ ╚══════╝  ╚═══╝ ╚══════╝', 36),
    ]

    label = f"{_color('Zeus Agent Harness', 1)}{_color('  v0.1.0', 90)}"
    info_lines = [
        f"  {_color('Provider:', 90)} {provider}",
        f"  {_color('Model:', 90)}    {model}",
        f"  {_color('Session:', 90)}  {logger.session_id[:12]}",
        f"  {_color('Uptime:', 90)}   {duration}",
        "",
        f"  {_color('Comandos:', 90)} /new  /reset  /clear  /models  /summary  /help  /exit",
    ]

    inner_width = 72
    top = _color('╔' + '═' * inner_width + '╗', 90)
    bottom = _color('╚' + '═' * inner_width + '╝', 90)

    def box_line(text: str = "", center: bool = False) -> str:
        if center:
            content = _pad_center(text, inner_width)
        else:
            content = _pad_left(text, inner_width)
        return _color('║', 90) + content + _color('║', 90)

    lines = ["", top]
    for row in zeus_ascii:
        lines.append(box_line(row, center=True))
    lines.append(box_line())
    lines.append(box_line(label, center=True))
    lines.append(box_line())
    for info in info_lines:
        lines.append(box_line(info))
    lines.append(bottom)
    lines.append("")
    print("\n".join(lines))


def _build_prompt(logger, metrics) -> str:
    model = os.getenv("ZEUS_MODEL", "unknown")
    snap = metrics.snapshot()
    in_tokens = snap.get("llm_input_tokens", 0)
    out_tokens = snap.get("llm_output_tokens", 0)
    duration = _format_duration(time.time() - snap.get("started_at", time.time()))
    session_short = logger.session_id[:8]

    bar = "\u00bb"  # » (seta dupla)
    return (
        f"{_color('Zeus', 36)} - {_color(model, 33)} "
        f"| {_color('in', 90)}:{_color(str(in_tokens), 32)} {_color('out', 90)}:{_color(str(out_tokens), 31)} "
        f"| {_color(duration, 35)} "
        f"| {_color(session_short, 90)}\n"
        f"{_color(bar, 90)} "
    )


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="Zeus Agent Harness")
    parser.add_argument("-q", "--query", help="Single query, non-interactive")
    parser.add_argument("--session", help="Session ID for logging")
    parser.add_argument("--summary", action="store_true", help="Print session summary after query")
    parser.add_argument("--team", action="store_true", help="Use multi-agent team orchestration")
    parser.add_argument("command", nargs="?", choices=["setup-model", "gateway"], help="Top-level commands (setup-model, gateway)")
    parser.add_argument("gateway_args", nargs=argparse.REMAINDER, help="Gateway subcommand arguments")
    args = parser.parse_args()

    if args.command == "gateway" or args.gateway_args:
        from zeus.gateway.cli import main as gateway_main
        sys.argv = ["zeus-gateway"] + (args.gateway_args if args.command == "gateway" else args.gateway_args[1:])
        gateway_main()
        return

    if args.command == "setup-model":
        from zeus.cli.setup_commands import setup_model
        sys.exit(0 if setup_model() else 1)

    logger = get_logger(args.session)
    metrics = get_metrics(logger.session_id)

    if args.query:
        logger.log_turn("user", args.query)
        if args.team:
            team = create_default_team(session_id=logger.session_id)
            response = team.run(args.query)
        else:
            response = run_agent(args.query, session_id=logger.session_id)
        logger.log_turn("assistant", response)
        print(response)
        if args.summary:
            print("\n--- Session summary ---")
            print(run_summary(session_id=logger.session_id))
        return

    session = PromptSession(history=FileHistory(".zeus_history"))
    _print_banner(logger, metrics)

    while True:
        prompt_text = _build_prompt(logger, metrics)
        try:
            user_input = session.prompt(ANSI(prompt_text))
        except (EOFError, KeyboardInterrupt):
            print("\nSaindo...")
            break

        text = user_input.strip()
        if not text:
            continue
        if text in ("/sair", "/quit", "/exit"):
            print("Saindo...")
            break
        if text == "/new":
            logger = get_logger(new_session=True)
            metrics = get_metrics(logger.session_id)
            print(f"Nova sessão: {logger.session_id}\n")
            continue
        if text == "/reset":
            # Preserve session ID but reset metrics and re-log system context
            old_session = logger.session_id
            logger = get_logger(old_session)
            metrics = get_metrics(old_session)
            print(f"Sessão resetada: {logger.session_id}\n")
            continue
        if text == "/clear":
            # clear/cls is a fixed, user-invoked terminal command with no external input.
            subprocess.run(["clear"] if os.name != "nt" else ["cls"], check=False)
            _print_banner(logger, metrics)
            continue
        if text == "/summary":
            print(run_summary(session_id=logger.session_id))
            continue
        if text in ("/help", "/?"):
            print("Comandos disponíveis:")
            print("  /new      - Cria uma nova sessão (novo ID)")
            print("  /reset    - Reseta a sessão atual (mantém ID, zera métricas)")
            print("  /clear    - Limpa a tela")
            print("  /summary  - Mostra resumo da sessão")
            print("  /models   - Troca o modelo/provedor LLM")
            print("  /sair     - Encerra o Zeus")
            print("  /exit, /quit - Alias para /sair")
            print("  /help     - Mostra esta ajuda")
            print("  /team <tarefa> - Executa com equipe multi-agente")
            continue

        if text == "/models":
            from zeus.cli.setup_commands import setup_model
            setup_model()
            continue

        if text.startswith("/team "):
            task = text[len("/team "):].strip()
            if not task:
                print("Uso: /team <tarefa>")
                continue
            logger.log_turn("user", text)
            try:
                team = create_default_team(session_id=logger.session_id)
                response = team.run(task)
                logger.log_turn("assistant", response)
                print(response)
            except Exception as e:
                logger.log_turn("error", str(e))
                print(f"Erro: {e}", file=sys.stderr)
            continue

        logger.log_turn("user", text)
        try:
            response = run_agent(text, session_id=logger.session_id)
            logger.log_turn("assistant", response)
            print(response)
        except Exception as e:
            logger.log_turn("error", str(e))
            print(f"Erro: {e}", file=sys.stderr)

    print(f"Session log: {logger.log_path}")
    print(run_summary(session_id=logger.session_id))


if __name__ == "__main__":
    main()
