"""Interactive CLI for Zeus."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import ANSI

from zeus.core.agent import run_agent, run_summary
from zeus.core.planner import generate_plan, execute_plan_step
from zeus.core.team import create_default_team, Team, Worker
from zeus.memory.session_log import get_logger
from zeus.observability import get_metrics
from zeus.tools import terminal, file, web, memory_tools, sandbox_client, sandbox, git, code_execution, browser, database, scheduler, user_profile_tools  # noqa: F401


def _ask_file_permission(message: str) -> Any:
    """Interactive confirmation for file write/delete actions."""
    from prompt_toolkit.formatted_text import ANSI

    print()
    print(message)
    try:
        answer = session.prompt(ANSI(f"{_color('❓', 33)} Escolha (y/a/p/n): "))
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower()


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


def _color(text: str, code: Any) -> str:
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

    inner_width = max(60, min(_get_term_width() - 4, 120))
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


def _get_term_width() -> int:
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    return max(40, min(cols, 160))


def _print_agent_response(response: str, title: str = "ZEUS", model: str = "") -> None:
    """Print the AI response wrapped in an open-ended left-bordered card dynamic to terminal width."""
    term_width = _get_term_width()
    model_name = os.getenv("ZEUS_MODEL", model or "agent")
    header_title = f" 🤖 {title} ({model_name}) "
    line_length = max(10, term_width - len(header_title) - 6)

    top = _color("╭──", 36) + _color(header_title, "1;36") + _color("─" * line_length, 36)
    bottom = _color("╰" + "─" * (term_width - 3), 36)

    print()
    print(top)
    for line in response.splitlines():
        print(f"{_color('│', 36)} {line}")
    print(bottom)
    print()


def _print_plan(plan: Dict[str, Any]) -> None:
    """Print a structured plan card."""
    term_width = _get_term_width()
    title = f" 📋 PLANO: {plan.get('title', 'Sem título')} "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 34) + _color(title, "1;34") + _color("─" * line_length, 34)
    bottom = _color("╰" + "─" * (term_width - 3), 34)

    print()
    print(top)
    for step in plan.get("steps", []):
        num = step.get("step", "?")
        action = step.get("action", "")
        hint = step.get("tool_hint", "any")
        print(f"{_color('│', 34)}  {num}. {action} {_color(f'[{hint}]', 90)}")
    print(bottom)
    print()


def _print_step_result(step: Dict[str, Any], total: int) -> None:
    """Print the result of a single plan step."""
    term_width = _get_term_width()
    title = f" ✅ Passo {step['step']}/{total}: {step['action'][:40]} "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 32) + _color(title, "1;32") + _color("─" * line_length, 32)
    bottom = _color("╰" + "─" * (term_width - 3), 32)

    print()
    print(top)
    for line in str(step.get("result", "")).splitlines():
        print(f"{_color('│', 32)} {line}")
    print(bottom)
    print()


def _ask_confirmation(session: PromptSession, text: str) -> bool:
    """Ask the user for y/n confirmation."""
    try:
        answer = session.prompt(ANSI(f"\n{_color('❓', 33)} {text} (s/n): "))
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("s", "sim", "y", "yes")


def _print_user_closing() -> None:
    """Close the user input box visually adapting to terminal width."""
    term_width = _get_term_width()
    print(_color("╰" + "─" * (term_width - 3), 33))


def _print_tool_execution(name: Optional[str], args: Any) -> None:
    """Print a notification when the agent executes a tool."""
    args_str = json.dumps(args) if isinstance(args, (dict, list)) else str(args or {})
    if len(args_str) > 65:
        args_str = args_str[:62] + "..."
    tool_name = name or "ferramenta"
    print(f"  {_color('⚡ Executando:', 35)} {_color(tool_name, '1;35')}({_color(args_str, 90)})")


def _build_prompt(logger, metrics) -> str:
    term_width = _get_term_width()
    model = os.getenv("ZEUS_MODEL", "unknown")
    snap = metrics.snapshot()
    in_tokens = snap.get("llm_input_tokens", 0)
    out_tokens = snap.get("llm_output_tokens", 0)
    duration = _format_duration(time.time() - snap.get("started_at", time.time()))
    session_short = logger.session_id[:8]

    title = f" 👤 VOCÊ | {model} | in:{in_tokens} out:{out_tokens} | {duration} | {session_short} "
    remaining = max(5, term_width - len(title) - 6)

    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * remaining, 33)
    prompt_arrow = _color("│ ❯ ", "1;33")

    return f"\n{top}\n{prompt_arrow}"


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

    # Connect interactive file permission callback.
    from zeus.tools.file import set_file_permission_callback
    set_file_permission_callback(_ask_file_permission)

    if args.query:
        logger.log_turn("user", args.query)
        if args.team:
            team = create_default_team(session_id=logger.session_id)
            response = team.run(args.query)
        else:
            response = run_agent(args.query, session_id=logger.session_id, tool_callback=_print_tool_execution)
        logger.log_turn("assistant", response)
        _print_agent_response(response)
        if args.summary:
            print("\n--- Resumo da sessão ---")
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
            print(f"\n{_color('✨ Nova sessão criada:', 32)} {logger.session_id}\n")
            continue
        if text == "/reset":
            old_session = logger.session_id
            logger = get_logger(old_session)
            metrics = get_metrics(old_session)
            print(f"\n{_color('🔄 Sessão resetada:', 33)} {logger.session_id}\n")
            continue
        if text == "/clear":
            subprocess.run(["clear"] if os.name != "nt" else ["cls"], check=False)
            _print_banner(logger, metrics)
            continue
        if text == "/summary":
            print(run_summary(session_id=logger.session_id))
            continue
        if text in ("/help", "/?"):
            print("\nComandos disponíveis:")
            print("  /new      - Cria uma nova sessão (novo ID)")
            print("  /reset    - Reseta a sessão atual (mantém ID, zera métricas)")
            print("  /clear    - Limpa a tela")
            print("  /summary  - Mostra resumo da sessão")
            print("  /models   - Troca o modelo/provedor LLM")
            print("  /plan <tarefa> - Cria e executa um plano passo a passo")
            print("  /team <tarefa> - Executa com equipe multi-agente")
            print("  /sair     - Encerra o Zeus")
            print("  /exit, /quit - Alias para /sair")
            print("  /help     - Mostra esta ajuda\n")
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
            _print_user_closing()
            try:
                team = create_default_team(session_id=logger.session_id)
                response = team.run(task)
                logger.log_turn("assistant", response)
                _print_agent_response(response, title="Equipe Multi-Agente")
            except Exception as e:
                logger.log_turn("error", str(e))
                print(f"\n{_color('❌ Erro:', '1;31')} {e}\n", file=sys.stderr)
            continue

        if text.startswith("/plan "):
            task = text[len("/plan "):].strip()
            if not task:
                print("Uso: /plan <tarefa>")
                continue
            logger.log_turn("user", text)
            _print_user_closing()
            try:
                plan = generate_plan(task)
                _print_plan(plan)
                if _ask_confirmation(session, "Executar este plano?"):
                    results: List[Dict[str, Any]] = []
                    steps = plan.get("steps", [])
                    for step in steps:
                        result = execute_plan_step(
                            step,
                            original_request=task,
                            previous_results=results,
                            session_id=logger.session_id,
                        )
                        results.append(result)
                        _print_step_result(result, len(steps))
                    summary = "\n\n".join(
                        f"Passo {r['step']}: {r['action']}\n{r['result']}"
                        for r in results
                    )
                    logger.log_turn("assistant", summary)
                    _print_agent_response(summary, title="RESULTADO DO PLANO")
                else:
                    print(f"\n{_color('Plano cancelado.', 33)}\n")
            except Exception as e:
                logger.log_turn("error", str(e))
                print(f"\n{_color('❌ Erro:', '1;31')} {e}\n", file=sys.stderr)
            continue

        logger.log_turn("user", text)
        _print_user_closing()
        try:
            response = run_agent(text, session_id=logger.session_id, tool_callback=_print_tool_execution)
            logger.log_turn("assistant", response)
            _print_agent_response(response)
        except Exception as e:
            logger.log_turn("error", str(e))
            print(f"\n{_color('❌ Erro:', '1;31')} {e}\n", file=sys.stderr)

    print(f"Session log: {logger.log_path}")
    print(run_summary(session_id=logger.session_id))


if __name__ == "__main__":
    main()
