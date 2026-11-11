"""Interactive CLI for Zeus."""

import argparse
import getpass
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
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import FileHistory

from zeus.cli.commands import (
    _current_skill_label,
    _dispatch_load_env,
    _dispatch_set_zeus_env,
    _handle_auth_command,
    _handle_config_command,
    _handle_learning_command,
    _handle_mcp_command,
    _handle_mode_command,
    _load_env,
    _print_brain_dashboard,
    _print_command_menu,
    _print_config_menu,
    _print_learning_menu,
    _print_mcp_menu,
    _print_mode_menu,
    _print_skills_menu,
    _set_zeus_env,
)
from zeus.cli.renderer import (
    _COLOR_ENABLED,
    _apply_inline_formatting,
    _color,
    _context_bar,
    _format_command_lines,
    _format_duration,
    _format_markdown_for_cli,
    _format_tokens,
    _get_term_width,
    _pad_center,
    _pad_left,
    _print_agent_response,
    _print_banner,
    _print_live_output,
    _print_plan,
    _print_prompt_header,
    _print_step_result,
    _print_tool_execution,
    _print_tool_result,
    _print_user_closing,
    _supports_color,
    _truncate_visible,
    _visible_width,
    _wrap_ansi_line,
)
from zeus.core.agent import run_agent, run_summary  # noqa: E402
from zeus.core.planner import execute_plan_step, generate_bmad_plan, generate_plan  # noqa: E402
from zeus.core.registry import REGISTRY  # noqa: E402
from zeus.core.team import create_default_team  # noqa: E402
from zeus.memory.session_log import get_logger  # noqa: E402
from zeus.observability import get_metrics  # noqa: E402
from zeus.tools import (  # noqa: E402,F401
    browser,
    code_execution,
    config_tools,
    database,
    file,
    git,
    learning_tools,
    manage_packages,
    memory_tools,
    sandbox,
    sandbox_client,
    scheduler,
    ssh_run,
    terminal,
    user_profile_tools,
    web,
)


class ZeusCommandCompleter(Completer):
    """Autocompletion menu for CLI slash commands."""

    COMMANDS = {
        "/new": "Cria uma nova sessão (novo ID)",
        "/reset": "Reseta a sessão atual (mantém ID, zera métricas)",
        "/clear": "Limpa a tela",
        "/summary": "Mostra resumo da sessão",
        "/skills": "Seleciona um skill set/persona para filtrar ferramentas",
        "/auth": "Autentica Google (google_auth) via browser ou revoga credenciais",
        "/mcp": "Gerencia servidores Model Context Protocol (MCP)",
        "/config": "Gerencia configurações do Zeus",
        "/learn": "Aprendizados passados: /learn list, /learn search <query>, /learn add <p> | <s>",
        "/brain": "Dashboard de inteligência e aprendizado contínuo",
        "/models": "Troca o provedor e modelo LLM",
        "/mode": "Alterna entre sandbox, terminal, auto, dryrun e readonly",
        "/plan": "Cria e executa um plano passo a passo (use /plan bmad <ideia> para análise de modelo de negócio)",
        "/team": "Executa com equipe multi-agente",
        "/exit": "Encerra o Zeus",
        "/help": "Mostra a ajuda de comandos",
    }

    SKILL_SETS = ["coding", "security", "research", "memory", "all"]
    MODES = ["sandbox", "terminal", "auto", "dryrun", "readonly"]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            parts = text.split()
            query = parts[0] if parts else text
            # complete skill set names after /skills
            if query == "/skills" and len(parts) <= 2:
                prefix = parts[1] if len(parts) == 2 else ""
                for name in self.SKILL_SETS:
                    if name.startswith(prefix):
                        if prefix:
                            yield Completion(
                                name,
                                start_position=-len(prefix),
                                display=name,
                            )
                        elif document.text_before_cursor.endswith(" "):
                            yield Completion(
                                name,
                                start_position=0,
                                display=name,
                            )
                        else:
                            yield Completion(
                                " " + name,
                                start_position=0,
                                display=name,
                            )
                return
            # complete mode names after /mode
            if query == "/mode" and len(parts) <= 2:
                prefix = parts[1] if len(parts) == 2 else ""
                for name in self.MODES:
                    if name.startswith(prefix):
                        if prefix:
                            yield Completion(
                                name,
                                start_position=-len(prefix),
                                display=name,
                            )
                        elif document.text_before_cursor.endswith(" "):
                            yield Completion(
                                name,
                                start_position=0,
                                display=name,
                            )
                        else:
                            yield Completion(
                                " " + name,
                                start_position=0,
                                display=name,
                            )
                return
            for cmd, desc in self.COMMANDS.items():
                if cmd.startswith(query):
                    yield Completion(
                        cmd,
                        start_position=-len(query),
                        display=cmd,
                        display_meta=desc,
                    )


SKILL_SETS: Dict[str, Dict[str, Any]] = {
    "coding": {
        "label": "💻 Coding",
        "description": "Ferramentas para desenvolvimento: terminal, arquivo, git, execução de código.",
        "tags": {"terminal", "file", "git", "code", "sandbox", "execute"},
    },
    "security": {
        "label": "🔒 Security",
        "description": "Acesso restrito: leitura de arquivos, memória e database; sem escrita.",
        "tags": {"file", "read", "memory", "database"},
    },
    "research": {
        "label": "🔍 Research",
        "description": "Ferramentas de pesquisa: web, browser e leitura de arquivos.",
        "tags": {"web", "research", "browser", "file", "read"},
    },
    "memory": {
        "label": "🧠 Memory",
        "description": "Gerenciamento de memória e perfil do usuário.",
        "tags": {"memory", "user", "database", "read"},
    },
    "all": {
        "label": "🌎 All",
        "description": "Todas as ferramentas disponíveis (padrão).",
        "tags": None,
    },
}


def _ask_file_permission(session: PromptSession, message: str) -> Any:
    """Interactive confirmation for file write/delete actions with a dynamic card design (Bilingual EN/PT)."""
    term_width = _get_term_width()
    title = " 🔒 FILE PERMISSION / PERMISSÃO DE ARQUIVO "
    line_length = max(10, term_width - len(title) - 6)

    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    print()
    print(top)
    for line in message.splitlines():
        if any(w in line for w in ("Permitir", "Allow", "Operação", "Operation", "Solicitação", "Request")):
            print(f"{_color('│', 33)}  {_color(line, '1;37')}")
        elif any(w in line for w in ("Arquivo:", "File:", "Caminho:", "Path:")):
            print(f"{_color('│', 33)}  {_color(line, '1;36')}")
        elif any(w in line for w in ("Options:", "Opções:", "Escolha", "Choose")):
            print(f"{_color('│', 33)}  {_color(line, 90)}")
        else:
            print(f"{_color('│', 33)}  {line}")
    print(f"{_color('│', 33)}")
    print(
        f"{_color('│', 33)}  "
        f"{_color('[y]', '1;32')} {_color('Yes / Sim (1x)', 37)}   "
        f"{_color('[a]', '1;34')} {_color('Always / Sempre (Session)', 37)}   "
        f"{_color('[p]', '1;35')} {_color('Persist / Persistir (Global)', 37)}   "
        f"{_color('[n]', '1;31')} {_color('No / Negar', 37)}"
    )
    print(bottom)

    try:
        answer = session.prompt(
            ANSI(f"{_color('❓', 33)} Choose / Escolha ({_color('y', '1;32')}/{_color('a', '1;34')}/{_color('p', '1;35')}/{_color('n', '1;31')}): ")
        )
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower()


def _ask_terminal_permission_prompt(message: str) -> Any:
    """Confirmation for terminal/host commands in terminal mode.

    Returns True (once), "always" (rest of session), or False (deny).
    """
    print()
    print(_color(" ⚠️  TERMINAL EXECUTION / EXECUÇÃO NO TERMINAL ", "1;33"))
    for line in message.splitlines():
        if line.strip():
            print(f"{_color('│', 33)} {line}")
    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)} {_color('[s]', '1;32')} Sim, executar agora")
    print(f"{_color('│', 33)} {_color('[a]', '1;34')} Sim, autorizar TODOS até o fim da sessão")
    print(f"{_color('│', 33)} {_color('[n]', '1;31')} Não")
    try:
        answer = active_session.prompt(
            ANSI(f"{_color('❓', 33)} Executar? / Run? ({_color('s', '1;32')}/{_color('a', '1;34')}/{_color('n', '1;31')}): ")
        )
    except (EOFError, KeyboardInterrupt):
        return False
    choice = answer.strip().lower()
    if choice in ("a", "always", "sempre", "todos"):
        return "always"
    if choice in ("s", "sim", "y", "yes"):
        return True
    return False


def _prompt_hidden(message: str) -> str:
    """Read a line with fully hidden input (no echo, no asterisks)."""
    return getpass.getpass(message)


def _ask_sudo_password(message: str) -> Optional[str]:
    """Prompt for sudo password without echoing it to the terminal or logs."""
    print()
    print(_color(" 🔐 SUDO REQUIRED / SUDO NECESSÁRIO ", "1;33"))
    print(_color(message, 90))
    try:
        password = _prompt_hidden(_color("Senha sudo: ", "1;33"))
    except (EOFError, KeyboardInterrupt):
        return None
    return password if password else None


def _ask_ssh_password(message: str) -> Optional[str]:
    """Prompt for SSH password without echoing it to the terminal or logs."""
    print()
    print(_color(" 🔑 SSH PASSWORD REQUIRED / SENHA SSH NECESSÁRIA ", "1;33"))
    print(_color(message, 90))
    try:
        password = _prompt_hidden(_color("Senha SSH: ", "1;33"))
    except (EOFError, KeyboardInterrupt):
        return None
    return password if password else None


def _handle_sudo_required(result: Dict[str, Any], session: PromptSession) -> Optional[Dict[str, Any]]:
    """If a tool needs sudo, prompt for password securely and retry once."""
    if not isinstance(result, dict) or not result.get("sudo_required"):
        return None

    pid = result.get("pid")
    command = result.get("command", "")
    msg = result.get("message", "Sudo required.")
    password = _ask_sudo_password(msg)
    if password is None:
        print(_color("Operação cancelada.", "1;31"))
        return {"cancelled": True, "error": "Sudo password not provided."}

    try:
        if command:
            parts = command.split()
            sudo_parts = ["sudo", "-S"] + parts[1:]
        else:
            sudo_parts = ["sudo", "-S", "kill", "-9", str(pid)]
        proc = subprocess.run(
            sudo_parts,
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        password = ""
        if proc.returncode != 0:
            print(_color(f"Sudo falhou: {proc.stderr.strip()}", "1;31"))
            return {"error": proc.stderr.strip()}
        print(_color("Sudo executado com sucesso.", "1;32"))
        return {"success": True}
    except Exception as e:
        print(_color(f"Erro ao executar sudo: {e}", "1;31"))
        return {"error": str(e)}


def _ask_confirmation(session: PromptSession, text: str) -> bool:
    """Ask the user for y/n confirmation."""
    try:
        answer = session.prompt(ANSI(f"\n{_color('❓', 33)} {text} (s/n): "))
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in ("s", "sim", "y", "yes")


active_session: Optional[PromptSession] = None


def _ask_file_permission_prompt(msg: str) -> Any:
    if active_session is None:
        return False

    term_width = _get_term_width()
    title = " 🔒 PERMISSÃO DE ARQUIVO NECESSÁRIA "
    line_len = max(10, term_width - len(title) - 6)

    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_len, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    print()
    print(top)
    for line in msg.splitlines():
        if line.strip():
            print(f"{_color('│', 33)} {line}")
    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)} {_color('Reply / Responda:', '1;37')}")
    print(f"{_color('│', 33)}   • {_color('(y)', '1;32')} yes / sim {_color('(once / uma vez)', 90)}")
    print(f"{_color('│', 33)}   • {_color('(a)', '1;36')} always / sempre {_color('(this session / nesta sessão)', 90)}")
    print(f"{_color('│', 33)}   • {_color('(p)', '1;35')} persist / persistir {_color('(permanent / permanente)', 90)}")
    print(f"{_color('│', 33)}   • {_color('(n)', '1;31')} no / negar")
    print(bottom)

    try:
        answer = active_session.prompt(ANSI(f"{_color('│ ❯ Opção', '1;33')} {_color('[y/a/p/n]:', 90)} "))
    except (EOFError, KeyboardInterrupt):
        return "deny"

    choice = answer.strip().lower()
    if choice in ("a", "always", "sempre"):
        return "always"
    if choice in ("p", "persist", "persistir"):
        return "persist"
    if choice in ("y", "yes", "s", "sim"):
        return "once"
    return "deny"


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="Zeus Agent Harness")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors in output")
    parser.add_argument("-q", "--query", help="Single query, non-interactive")
    parser.add_argument("--session", help="Session ID for logging")
    parser.add_argument("--summary", action="store_true", help="Print session summary after query")
    parser.add_argument("--team", action="store_true", help="Use multi-agent team orchestration")
    parser.add_argument("--desktop-json", action="store_true", help="Run structured JSONL bridge for Zeus Desktop")
    parser.add_argument("--desktop-catalog", action="store_true", help="Output dynamic desktop catalog JSON and exit")
    parser.add_argument("command", nargs="?", choices=["setup", "setup-model", "gateway"], help="Top-level commands (setup, setup-model, gateway)")
    parser.add_argument("gateway_args", nargs=argparse.REMAINDER, help="Gateway subcommand arguments")
    args = parser.parse_args()

    global _COLOR_ENABLED
    if args.no_color or args.desktop_json:
        _COLOR_ENABLED = False

    if args.desktop_catalog:
        from zeus.cli.desktop_bridge import build_desktop_catalog
        print(json.dumps(build_desktop_catalog(), ensure_ascii=False, default=str))
        return 0

    if args.desktop_json:
        from zeus.cli.desktop_bridge import run_desktop_bridge
        return run_desktop_bridge(
            query=args.query,
            session_id=args.session,
            use_team=args.team,
        )

    if args.command == "gateway" or args.gateway_args:
        os.environ.pop("ZEUS_LOCAL_CLI", None)
        from zeus.gateway.cli import main as gateway_main
        sys.argv = ["zeus-gateway"] + (args.gateway_args if args.command == "gateway" else args.gateway_args[1:])
        gateway_main()
        return 0

    if args.command == "setup":
        from zeus.cli.onboarding import run_setup_wizard
        return 0 if run_setup_wizard() else 1

    if args.command == "setup-model":
        from zeus.cli.setup_commands import setup_model
        return 0 if setup_model() else 1

    # Expose workspace switching only to local CLI agent sessions, never gateways.
    os.environ["ZEUS_LOCAL_CLI"] = "1"

    logger = get_logger(args.session)
    metrics = get_metrics(logger.session_id)

    if args.query:
        logger.log_turn("user", args.query)
        try:
            if args.team:
                team = create_default_team(session_id=logger.session_id)
                response = team.run(args.query)
            else:
                response = run_agent(args.query, session_id=logger.session_id, tool_callback=_print_tool_execution)
        except Exception as e:
            logger.log_turn("error", str(e))
            print(f"\n{_color('❌ Erro:', '1;31')} {e}\n", file=sys.stderr)
            return 1
        logger.log_turn("assistant", response)
        _print_agent_response(response)
        if args.summary:
            print("\n--- Resumo da sessão ---")
            print(run_summary(session_id=logger.session_id))
        return 0

    # Pre-load max_turns from config.yaml so interactive sessions respect it.
    from zeus.config.settings import load_config as _load_config
    _config_max_turns = _load_config().get("max_turns")
    if _config_max_turns is not None:
        try:
            _config_max_turns = int(_config_max_turns)
        except Exception:
            _config_max_turns = None

    session = PromptSession(
        history=FileHistory(str(Path.cwd() / ".zeus_history")),
        completer=ZeusCommandCompleter(),
    )
    global active_session
    active_session = session

    # Connect interactive file permission callback.
    from zeus.tools.file import set_file_permission_callback
    set_file_permission_callback(_ask_file_permission_prompt)

    # Stream live terminal output so the user can see command progress instead
    # of waiting blindly for a long command (e.g. apt upgrade) to finish.
    from zeus.tools.terminal import set_stream_callback
    set_stream_callback(_print_live_output)

    # Wire the same interactive confirmation callback into the global PermissionManager
    # so that terminal-mode tool confirmations (human-in-the-loop) can prompt the user.
    from zeus.security.permissions import PermissionManager, set_global_permission_manager
    set_global_permission_manager(
        PermissionManager(
            confirm_callback=_ask_terminal_permission_prompt,
            password_callback=_ask_sudo_password,
            exec_level=os.getenv("ZEUS_EXECUTION_PERMISSION", "sandbox_only"),
        )
    )

    _print_banner(logger, metrics)
    active_skill: Optional[set] = None

    # Auto-start configured MCP servers upon startup
    try:
        from zeus.mcp.manager import MCPManager
        MCPManager.get_instance().start_all()
    except Exception:
        pass

    while True:
        _print_prompt_header(logger, get_metrics(logger.session_id))
        prompt_arrow = ANSI(_color("│ ❯ ", "1;33"))
        try:
            user_input = session.prompt(prompt_arrow)
        except KeyboardInterrupt:
            print(f"\n{_color('⚡ Digite /exit ou pressione Ctrl+D para sair.', 90)}")
            continue
        except EOFError:
            print(f"\n{_color('👋 Até mais!', 36)}\n")
            break

        text = user_input.strip()
        if not text:
            continue
        if text == "/exit":
            print(f"\n{_color('👋 Até mais!', 36)}\n")
            break

        if text == "/new":
            logger = get_logger(new_session=True)
            metrics = get_metrics(logger.session_id)
            active_skill = None
            print(f"\n{_color('✨ Nova sessão criada:', 32)} {logger.session_id}\n")
            continue
        if text == "/reset":
            old_session = logger.session_id
            logger = get_logger(old_session)
            metrics = get_metrics(old_session)
            active_skill = None
            print(f"\n{_color('🔄 Sessão resetada:', 33)} {logger.session_id}\n")
            continue
        if text == "/clear":
            subprocess.run(["clear"] if os.name != "nt" else ["cls"], check=False)
            _print_banner(logger, metrics)
            continue
        if text == "/summary":
            print(run_summary(session_id=logger.session_id))
            continue
        if text in ("/", "/help", "/?"):
            _print_command_menu()
            continue

        if text == "/mcp" or text.startswith("/mcp "):
            _handle_mcp_command(text)
            continue

        if text == "/auth" or text.startswith("/auth "):
            _handle_auth_command(text)
            continue

        if text == "/config" or text.startswith("/config "):
            _handle_config_command(text)
            continue

        if text == "/brain":
            _print_brain_dashboard()
            continue

        if text == "/learn" or text.startswith("/learn "):
            _handle_learning_command(text)
            continue

        if text == "/skills":
            _print_skills_menu(active_skill)
            continue

        if text.startswith("/skills "):
            skill_name = text[len("/skills "):].strip()
            if skill_name not in SKILL_SETS:
                print(f"\n{_color('❌ Skill set desconhecido:', '1;31')} {skill_name}")
                print(f"{_color('Use:', 90)} /skills coding | security | research | memory | all\n")
                continue
            active_skill = SKILL_SETS[skill_name]["tags"]
            label = SKILL_SETS[skill_name]["label"]
            print(f"\n{_color('🔧 Skill set ativado:', 32)} {label}")
            count = len(REGISTRY.schemas(tag_allowlist=active_skill))
            print(f"{_color('Ferramentas disponíveis:', 90)} {count}\n")
            continue

        if text in ("/models", "/provider"):
            from zeus.cli.setup_commands import setup_model
            setup_model()
            _load_env(override=True)
            continue

        if text == "/mode" or text.startswith("/mode "):
            _handle_mode_command(text)
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
            except KeyboardInterrupt:
                logger.log_turn("system", "Interrupted by user (Ctrl+C)")
                print(f"\n{_color('⚡ Execução da equipe interrompida pelo usuário (Ctrl+C).', 33)}\n")
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
                if task.lower().startswith("bmad "):
                    plan = generate_bmad_plan(task[len("bmad "):].strip())
                else:
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
            except KeyboardInterrupt:
                logger.log_turn("system", "Interrupted by user (Ctrl+C)")
                print(f"\n{_color('⚡ Execução do plano interrompida pelo usuário (Ctrl+C).', 33)}\n")
            except Exception as e:
                logger.log_turn("error", str(e))
                print(f"\n{_color('❌ Erro:', '1;31')} {e}\n", file=sys.stderr)
            continue

        logger.log_turn("user", text)
        _print_user_closing()
        try:
            response = run_agent(
                text,
                session_id=logger.session_id,
                max_turns=_config_max_turns,
                tool_callback=_print_tool_execution,
                tool_result_callback=_print_tool_result,
                tool_filter=active_skill,
            )

            # Handle sudo escalation requested by a tool (e.g. restart_sandbox).
            if isinstance(response, dict) and response.get("sudo_required"):
                sudo_res = _handle_sudo_required(response, session)
                if sudo_res and sudo_res.get("success"):
                    print(f"\n{_color('✅ Sudo executado. Retomando operação...', 32)}\n")
                    pending = response.get("pending_input", text)
                    response = run_agent(
                        pending,
                        session_id=logger.session_id,
                        max_turns=_config_max_turns,
                        tool_callback=_print_tool_execution,
                        tool_result_callback=_print_tool_result,
                        tool_filter=active_skill,
                    )
                else:
                    err_msg = (sudo_res or {}).get("error", "Sudo cancelled")
                    response = f"Operação cancelada: {err_msg}"

            # Handle SSH user requested by the ssh_run tool (plain text prompt).
            if isinstance(response, dict) and response.get("ssh_user_required"):
                ssh_req = response["ssh_user_required"]
                host = ssh_req.get("host", "")
                port = ssh_req.get("port", 22)
                command = ssh_req.get("command", "")
                print()
                print(_color(" 👤 SSH USER REQUIRED / USUÁRIO SSH NECESSÁRIO ", "1;33"))
                print(_color(f"  Host: {host} (port {port})", 90))
                print(_color(f"  Command: {command}", 90))
                try:
                    ssh_user = session.prompt(ANSI(f"{_color('❓', 33)} Usuário SSH: "))
                except (EOFError, KeyboardInterrupt):
                    ssh_user = ""
                ssh_user = ssh_user.strip()
                if ssh_user:
                    print(_color(f"Usuário {ssh_user} recebido. Reconectando...", "1;32"))
                    from zeus.tools.ssh_run import ssh_run
                    ssh_result = ssh_run(
                        host=host,
                        command=command,
                        user=ssh_user,
                        port=port,
                    )
                    print(_color("Resultado SSH:", "1;32"))
                    print(json.dumps(ssh_result, indent=2, default=str))
                    response = f"SSH result: {json.dumps(ssh_result, default=str)}"
                else:
                    response = "Operação cancelada: usuário SSH não fornecido."

            # Handle SSH password requested by the ssh_run tool.
            if isinstance(response, dict) and response.get("ssh_password_required"):
                ssh_req = response["ssh_password_required"]
                host = ssh_req.get("host", "")
                user = ssh_req.get("user", "")
                port = ssh_req.get("port", 22)
                command = ssh_req.get("command", "")
                target = f"{user}@{host}" if user else host
                msg = (
                    f"Host: {target} (port {port})\n"
                    f"Command: {command}"
                )
                password = _ask_ssh_password(msg)
                if password:
                    print(_color("Senha recebida. Reconectando...", "1;32"))
                    pending = response.get("pending_input", text)
                    from zeus.tools.ssh_run import ssh_run
                    ssh_result = ssh_run(
                        host=host,
                        command=command,
                        user=user,
                        port=port,
                        password=password,
                    )
                    password = ""
                    print(_color("Resultado SSH:", "1;32"))
                    print(json.dumps(ssh_result, indent=2, default=str))
                    response = f"SSH result: {json.dumps(ssh_result, default=str)}"
                else:
                    response = "Operação cancelada: senha SSH não fornecida."

            # Handle interactive permission confirmation if required
            while isinstance(response, dict) and response.get("permission_required"):
                perm = response["permission_required"]
                action = perm.get("action", "escrita")
                path_str = perm.get("path", "")
                msg = (
                    f"File permission request / Solicitação de permissão de arquivo:\n"
                    f"  • Operation / Operação: {action}\n"
                    f"  • File / Arquivo: {path_str}"
                )
                choice = _ask_file_permission_prompt(msg)
                if choice in ("once", "always", "persist"):
                    from zeus.tools.file import get_file_permission_manager
                    pm = get_file_permission_manager()
                    pm.grant_permission(action, Path(path_str), scope=choice)
                    print(f"\n{_color('✅ Permissão concedida!', 32)} Retomando operação...\n")
                    pending = response.get("pending_input", text)
                    response = run_agent(
                        pending,
                        session_id=logger.session_id,
                        max_turns=_config_max_turns,
                        tool_callback=_print_tool_execution,
                        tool_result_callback=_print_tool_result,
                        tool_filter=active_skill,
                    )
                else:
                    resp_text = (
                        f"Permissão negada pelo usuário para '{action}' no arquivo '{path_str}'. "
                        "A operação de escrita foi cancelada por segurança."
                    )
                    response = resp_text
                    break

            status = "ok"
            if isinstance(response, str) and response.startswith("Guardrail Blocked:"):
                resp_text = response
                status = "warning"
            elif isinstance(response, str) and response.startswith("LLM error:"):
                resp_text = response
                status = "error"
            else:
                resp_text = str(response)
            logger.log_turn("assistant", resp_text)
            _print_agent_response(resp_text, status=status)

        except KeyboardInterrupt:
            logger.log_turn("system", "Interrupted by user (Ctrl+C)")
            print(f"\n{_color('⚡ Execução interrompida pelo usuário (Ctrl+C).', 33)}\n")
        except Exception as e:
            logger.log_turn("error", str(e))
            print(f"\n{_color('❌ Erro:', '1;31')} {e}\n", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
