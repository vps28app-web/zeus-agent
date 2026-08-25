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
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import FileHistory


class ZeusCommandCompleter(Completer):
    """Autocompletion menu for CLI slash commands."""

    COMMANDS = {
        "/new": "Cria uma nova sessão (novo ID)",
        "/reset": "Reseta a sessão atual (mantém ID, zera métricas)",
        "/clear": "Limpa a tela",
        "/summary": "Mostra resumo da sessão",
        "/skills": "Seleciona um skill set/persona para filtrar ferramentas",
        "/mcp": "Gerencia servidores Model Context Protocol (MCP)",
        "/config": "Gerencia configurações do Zeus",
        "/learn": "Aprendizados passados: /learn list, /learn search <query>, /learn add <p> | <s>",
        "/brain": "Dashboard de inteligência e aprendizado contínuo",
        "/models": "Troca o modelo/provedor LLM",
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
                        yield Completion(
                            name,
                            start_position=-len(prefix),
                            display=name,
                        )
                return
            # complete mode names after /mode
            if query == "/mode" and len(parts) <= 2:
                prefix = parts[1] if len(parts) == 2 else ""
                for name in self.MODES:
                    if name.startswith(prefix):
                        yield Completion(
                            name,
                            start_position=-len(prefix),
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


def _current_skill_label(active_filter: Optional[set]) -> str:
    if not active_filter:
        return "all"
    for key, cfg in SKILL_SETS.items():
        if cfg["tags"] == active_filter:
            return key
    return "custom"


def _print_skills_menu(active_filter: Optional[set]) -> None:
    """Print a visual menu of available skill sets."""
    term_width = _get_term_width()
    title = " 🧛 SKILL SETS "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    current = _current_skill_label(active_filter)

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Ativo:', 90)} {SKILL_SETS[current]['label'] if current in SKILL_SETS else current}")
    print(f"{_color('│', 33)}")
    max_key = max(len(key) for key in SKILL_SETS)
    for key, cfg in SKILL_SETS.items():
        marker = _color("●", 32) if key == current else " "
        pad = " " * (max_key - len(key))
        tags = "todas" if cfg["tags"] is None else ", ".join(sorted(cfg["tags"]))
        print(f"{_color('│', 33)}  {marker} {_color('/skills ' + key, '1;33')}{pad}  {cfg['label']} {_color('[' + tags + ']', 90)}")
    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)}  {_color('Uso:', 90)} /skills <nome>  ou  /skills para este menu")
    print(bottom)
    print()


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
    terminal,
    user_profile_tools,
    web,
)


def _ask_file_permission(session: PromptSession, message: str) -> Any:
    """Interactive confirmation for file write/delete actions with a dynamic card design (Bilingual EN/PT)."""
    from prompt_toolkit.formatted_text import ANSI

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




def _load_env(override: bool = False) -> None:
    """Load .env from ~/.zeus/.env or the project root if present."""
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    paths = [zeus_home / ".env", Path.cwd() / ".env"]
    for env_file in paths:
        if env_file.exists():
            load_dotenv(env_file, override=override)

    # Sync GEMINI_API_KEY and GOOGLE_API_KEY aliases
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key
        os.environ["GOOGLE_API_KEY"] = gemini_key




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


def _format_tokens(count: int) -> str:
    """Format token count into human readable notation (e.g., 500, 1.2k, 12k, 15m)."""
    if count < 1000:
        return str(count)
    elif count < 1_000_000:
        val = count / 1000.0
        return f"{val:.1f}k" if val < 10 else f"{int(val)}k"
    elif count < 1_000_000_000:
        val = count / 1_000_000.0
        return f"{val:.1f}m" if val < 10 else f"{int(val)}m"
    else:
        val = count / 1_000_000_000.0
        return f"{val:.1f}b" if val < 10 else f"{int(val)}b"


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
        f"  {_color('Comandos:', 90)} /new  /reset  /clear  /skills  /models  /mode  /summary  /help  /exit",
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


def _apply_inline_formatting(text: str) -> str:
    """Apply ANSI styling to inline markdown elements: **bold**, `code`, key-value tags."""
    import re
    # Bold **text** -> \033[1;37mtext\033[0m
    text = re.sub(r"\*\*(.*?)\*\*", r"\033[1;37m\1\033[0m", text)
    # Inline code `code` -> \033[1;36mcode\033[0m
    text = re.sub(r"`([^`]+)`", r"\033[1;36m\1\033[0m", text)
    # Key-value pattern (e.g. Status: ok) -> \033[1;33mKey:\033[0m Value
    text = re.sub(r"^([A-Z][a-zA-Z0-9_\s-]{1,25}:)", r"\033[1;33m\1\033[0m", text)
    return text


def _wrap_ansi_line(text: str, max_width: int) -> List[str]:
    """Wrap a string containing ANSI escape sequences so visible width <= max_width."""
    if _visible_width(text) <= max_width:
        return [text]

    words = text.split(" ")
    lines: List[str] = []
    current_line = ""

    for word in words:
        if not current_line:
            current_line = word
        elif _visible_width(current_line + " " + word) <= max_width:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines if lines else [text]


def _format_markdown_for_cli(text: str, max_width: int = 80) -> List[str]:
    """Format markdown response for CLI rendering with color, structure, and proper line wrapping."""
    import re
    if not text:
        return [""]

    lines = text.splitlines()
    formatted: List[str] = []
    in_code_block = False
    code_lang = ""

    for line in lines:
        stripped = line.strip()

        # Code block delimiter
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_lang = stripped[3:].strip()
                lang_tag = f" [{code_lang}]" if code_lang else ""
                header = f"┌─ 💻 CODE{lang_tag} "
                pad_len = max(2, max_width - _visible_width(header))
                formatted.append(_color(header + "─" * pad_len, "1;30"))
            else:
                in_code_block = False
                formatted.append(_color("└─" + "─" * max(2, max_width - 2), "1;30"))
            continue

        if in_code_block:
            code_line = _color("  " + line, "1;36")
            for wl in _wrap_ansi_line(code_line, max_width):
                formatted.append(wl)
            continue

        if not stripped:
            formatted.append("")
            continue

        # Markdown Headers
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            formatted.append(_color(f"📌 {title.upper()}", "1;33;4"))
            continue
        elif stripped.startswith("## "):
            title = stripped[3:].strip()
            formatted.append(_color(f"🔹 {title}", "1;33"))
            continue
        elif stripped.startswith("### "):
            title = stripped[4:].strip()
            formatted.append(_color(f"▸ {title}", "1;37"))
            continue

        # Bullet lists & numbered lists
        is_bullet = False
        prefix = ""
        content = ""
        if stripped.startswith(("- ", "* ", "• ")):
            prefix = _color("  • ", "1;32")
            content = stripped[2:]
            is_bullet = True
        elif re.match(r"^\d+\.\s", stripped):
            parts = stripped.split(".", 1)
            prefix = _color(f"  {parts[0]}.", "1;32")
            content = parts[1].strip()
            is_bullet = True

        if is_bullet:
            content_styled = _apply_inline_formatting(content)
            avail_width = max(10, max_width - 5)
            wrapped_items = _wrap_ansi_line(content_styled, avail_width)
            if wrapped_items:
                formatted.append(f"{prefix} {wrapped_items[0]}")
                for wi in wrapped_items[1:]:
                    formatted.append(f"    {wi}")
            else:
                formatted.append(prefix)
            continue

        # Regular text paragraph with inline formatting
        styled_line = _apply_inline_formatting(line)
        for wl in _wrap_ansi_line(styled_line, max_width):
            formatted.append(wl)

    return formatted


def _print_agent_response(response: str, title: str = "ZEUS", model: str = "", status: str = "ok") -> None:
    """Print the AI response wrapped in an open-ended left-bordered card dynamic to terminal width."""
    term_width = _get_term_width()
    model_name = os.getenv("ZEUS_MODEL", model or "agent")

    border_color = "36"
    status_label = ""
    if status == "warning":
        border_color = "33"
        status_label = " " + _color("[ Atenção ]", "1;33")
    elif status == "error":
        border_color = "31"
        status_label = " " + _color("[ Erro ]", "1;31")

    header_title = f" 🤖 {title} ({model_name}) "
    inner_width = max(20, term_width - 6)

    top = _color("╭──", border_color) + _color(header_title, f"1;{border_color}") + status_label
    top_vis = _visible_width(top)
    pad_len = max(2, term_width - top_vis - 1)
    top += _color("─" * pad_len, border_color)


    bottom = _color("╰" + "─" * (term_width - 3), border_color)

    from zeus.core.agent import clean_agent_response
    clean_resp = clean_agent_response(str(response or ""))
    formatted_lines = _format_markdown_for_cli(clean_resp, max_width=inner_width)

    print()
    print(top)
    for line in formatted_lines:
        print(f"{_color('│', border_color)} {line}")
    print(bottom)
    print()



def _print_command_menu() -> None:
    """Print a visual menu of available slash commands."""
    term_width = _get_term_width()
    title = " ⚡ MENU DE COMANDOS "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    commands = [
        ("/new", "Cria uma nova sessão (novo ID)"),
        ("/reset", "Reseta a sessão atual (mantém ID, zera métricas)"),
        ("/clear", "Limpa a tela"),
        ("/summary", "Mostra resumo da sessão"),
        ("/skills", "Seleciona um skill set/persona para filtrar ferramentas"),
        ("/mcp", "Gerencia servidores Model Context Protocol (MCP)"),
        ("/config", "Gerencia configurações do Zeus (get/set/list)"),
        ("/learn", "Aprendizados passados (list/search/add/stats/forget)"),
        ("/brain", "Dashboard de inteligência e aprendizado contínuo"),
        ("/models", "Troca o modelo/provedor LLM"),
        ("/mode <sandbox|terminal|auto|dryrun|readonly>", "Alterna modo de execução e segurança"),
        ("/mode status", "Mostra apenas o status atual do agente"),
        ("/plan <tarefa>", "Cria e executa um plano passo a passo"),
        ("/plan bmad <ideia>", "Análise BMAD de modelo de negócio"),
        ("/team <tarefa>", "Executa com equipe multi-agente"),
        ("/help", "Mostra este menu"),
        ("/exit", "Encerra o Zeus"),
    ]

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Digite /comando ou escolha abaixo:', 90)}")
    print(f"{_color('│', 33)}")
    max_cmd = max(len(cmd) for cmd, _ in commands)
    for cmd, desc in commands:
        pad = " " * (max_cmd - len(cmd))
        print(f"{_color('│', 33)}  {_color(cmd, '1;33')}{pad}  {desc}")
    print(bottom)
    print()


def _print_mcp_menu() -> None:
    """Print status of configured MCP servers and active tools."""
    from zeus.mcp import get_mcp_manager
    mgr = get_mcp_manager()
    statuses = mgr.list_status()

    term_width = _get_term_width()
    title = " 🔌 MODEL CONTEXT PROTOCOL (MCP) "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    print()
    print(top)
    if not statuses:
        print(f"{_color('│', 33)}  {_color('Nenhum servidor MCP configurado.', 90)}")
        print(f"{_color('│', 33)}  {_color('Adicione um servidor:', 90)} /mcp add <nome> <comando_ou_url> [args...]")
    else:
        for srv in statuses:
            status_symbol = _color("● Ativo", 32) if srv["active"] else _color("○ Inativo", 31)
            type_label = _color(f"[{srv['type'].upper()}]", 36)
            cmd = _color(srv["command_or_url"], 90)
            tools_info = _color(f"({srv['tool_count']} ferramentas)", 33) if srv["active"] else ""
            print(f"{_color('│', 33)}  {status_symbol} {_color(srv['name'], '1;37')} {type_label} - {cmd}  {tools_info}")

    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)}  {_color('Comandos MCP:', 90)}")
    print(f"{_color('│', 33)}    • {_color('/mcp list', 33)}                        - Lista servidores e status")
    print(f"{_color('│', 33)}    • {_color('/mcp add <nome> <cmd|url> [args]', 33)} - Adiciona e conecta novo servidor")
    print(f"{_color('│', 33)}    • {_color('/mcp remove <nome>', 33)}              - Remove um servidor MCP")
    print(f"{_color('│', 33)}    • {_color('/mcp reload', 33)}                     - Reconecta todos os servidores")
    print(bottom)
    print()


def _handle_mcp_command(text: str) -> None:
    """Handle /mcp subcommands."""
    from zeus.mcp import get_mcp_manager
    mgr = get_mcp_manager()
    parts = text.split()
    subcmd = parts[1].lower() if len(parts) > 1 else "list"

    if subcmd in ("list", "ls", "status"):
        _print_mcp_menu()
    elif subcmd == "reload":
        print(f"\n{_color('🔄 Reconectando servidores MCP...', 33)}")
        res = mgr.reload()
        for name, ok in res.items():
            status = _color("Conectado", 32) if ok else _color("Falhou", 31)
            print(f"  • {name}: {status}")
        print()
    elif subcmd in ("remove", "rm", "delete"):
        if len(parts) < 3:
            print(f"\n{_color('❌ Uso:', '1;31')} /mcp remove <nome_do_servidor>\n")
            return
        name = parts[2]
        if mgr.remove_server(name):
            print(f"\n{_color('✅ Servidor MCP removido:', 32)} {name}\n")
        else:
            print(f"\n{_color('❌ Servidor MCP não encontrado:', '1;31')} {name}\n")
    elif subcmd in ("add", "connect"):
        if len(parts) < 3:
            print(f"\n{_color('❌ Uso:', '1;31')} /mcp add <nome> [comando_ou_url] [args...]")
            print(f"{_color('Exemplo (Preset):', 90)} /mcp add gemini")
            print(f"{_color('Exemplo (Custom):', 90)} /mcp add meuteste npx -y @modelcontextprotocol/server-memory\n")
            return
        name = parts[2]
        cmd_or_url = parts[3] if len(parts) > 3 else name
        args = parts[4:] if len(parts) > 4 else []
        print(f"\n{_color('🔌 Conectando servidor MCP:', 33)} {name}...")
        ok = mgr.add_server(name, cmd_or_url, args=args)
        if ok:
            client = mgr.clients.get(name)
            tool_cnt = len(client.tools) if client else 0
            print(f"{_color('✅ Conectado com sucesso!', 32)} {tool_cnt} ferramentas disponíveis.\n")
        else:
            print(f"{_color('❌ Falha ao conectar ao servidor MCP.', '1;31')}\n")

    else:
        _print_mcp_menu()


def _print_brain_dashboard() -> None:
    """Print continuous learning and intelligence statistics dashboard."""
    from zeus.memory.learning import LearningStore
    from zeus.memory.reasoning import ReasoningMemory
    from zeus.memory.store import MemoryStore
    from zeus.memory.user_profile import UserProfileStore

    l_store = LearningStore()
    l_stats = l_store.get_stats()

    m_store = MemoryStore()
    m_keys = m_store.keys()

    p_store = UserProfileStore()
    profiles = p_store.list_profiles()

    r_mem = ReasoningMemory()
    r_entries = r_mem.recall("", limit=100)

    term_width = _get_term_width()
    title = " 🧠 ZEUS CONTINUOUS LEARNING & BRAIN DASHBOARD "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 36) + _color(title, "1;36") + _color("─" * line_length, 36)
    bottom = _color("╰" + "─" * (term_width - 3), 36)

    print()
    print(top)
    print(f"{_color('│', 36)}  {_color('📊 Padrões Aprendidos (Continuous Learning Store):', '1;37')}")
    print(f"{_color('│', 36)}    • Total de Aprendizados: {_color(str(l_stats['total_learnings']), 33)}")
    print(f"{_color('│', 36)}    • Auto-Aprendidos em Sessões: {_color(str(l_stats['auto_learned']), 32)}")
    print(f"{_color('│', 36)}    • Alta Relevância (Score > 0): {_color(str(l_stats['high_effectiveness']), 32)}")
    if l_stats["tags_summary"]:
        tags_str = ", ".join(f"{k}:{v}" for k, v in list(l_stats["tags_summary"].items())[:6])
        print(f"{_color('│', 36)}    • Tags Principais: {_color(tags_str, 90)}")

    print(f"{_color('│', 36)}")
    print(f"{_color('│', 36)}  {_color('💡 Raciocínios e Estratégias Salvas (Reasoning Memory):', '1;37')}")
    print(f"{_color('│', 36)}    • Padrões de Raciocínio: {_color(str(len(r_entries)), 33)}")

    print(f"{_color('│', 36)}")
    print(f"{_color('│', 36)}  {_color('👤 Conhecimento sobre Usuário & Perfil:', '1;37')}")
    print(f"{_color('│', 36)}    • Perfis Ativos: {_color(str(len(profiles)), 33)}")
    print(f"{_color('│', 36)}    • Chaves de Conhecimento Persistente: {_color(str(len(m_keys)), 33)}")

    print(f"{_color('│', 36)}")
    print(f"{_color('│', 36)}  {_color('⚡ O Zeus aprende autonomamente após resoluções e avalia feedback do usuário!', 90)}")
    print(bottom)
    print()


def _print_learning_menu() -> None:
    """Print a visual menu for the /learn command."""
    term_width = _get_term_width()
    title = " 📚 APRENDIZADOS "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Comandos:', 90)}")
    print(f"{_color('│', 33)}    • {_color('/learn', 33)}                       - Menu de aprendizados")
    print(f"{_color('│', 33)}    • {_color('/learn list', 33)}                  - Lista recentes")
    print(f"{_color('│', 33)}    • {_color('/learn search <query>', 33)}        - Busca aprendizados por palavra-chave")
    print(f"{_color('│', 33)}    • {_color('/learn add <p> | <s> [tags]', 33)} - Adiciona aprendizado manual")
    print(f"{_color('│', 33)}    • {_color('/learn rate <id> <+1/-1>', 33)}    - Avalia aprendizado")
    print(f"{_color('│', 33)}    • {_color('/learn stats', 33)}                 - Dashboard de inteligência / brain")
    print(f"{_color('│', 33)}    • {_color('/learn forget <id>', 33)}            - Remove aprendizado específico")
    print(bottom)
    print()


def _handle_learning_command(text: str) -> None:
    """Handle /learn subcommands."""
    from zeus.memory.learning import LearningStore

    parts = text.split(maxsplit=1)
    subcmd = parts[1].lower().strip() if len(parts) > 1 else "menu"

    store = LearningStore()

    if subcmd == "menu" or subcmd == "":
        _print_learning_menu()
        return

    if subcmd in ("stats", "brain", "dashboard"):
        _print_brain_dashboard()
        return

    if subcmd == "list":
        learnings = store.list_recent(limit=10)
        print(f"\n{_color('📚 Aprendizados recentes:', 33)}")
        if not learnings:
            print(f"  {_color('Nenhum aprendizado registrado ainda.', 90)}")
        for item in learnings:
            score = item.get("effectiveness_score", 0)
            score_color = 32 if score > 0 else 31 if score < 0 else 90
            item_id = item.get("id")
            item_problem = item.get("problem", "")[:60]
            item_tags = ", ".join(item.get("tags", []))
            print(f"  {_color(f'[{item_id}]', '1;33')} {item_problem}")
            print(f"    {_color('Score:', score_color)} {score} {_color('Tags:', 90)} {item_tags}")
        print()
        return

    if subcmd.startswith("search "):
        query = subcmd[len("search "):].strip()
        results = store.search(query, limit=5)
        print(f"\n{_color('🔍 Resultados:', 33)} {query}\n")
        if not results:
            print(f"  {_color('Nenhum aprendizado encontrado para essa busca.', 90)}")
        for item in results:
            item_id = item.get("id")
            item_problem = item.get("problem", "")
            item_solution = item.get("solution", "")[:120]
            print(f"  {_color(f'[{item_id}]', '1;33')} {item_problem}")
            print(f"    {_color('Solução:', 90)} {item_solution}")
        print()
        return

    if subcmd.startswith("add "):
        payload = subcmd[len("add "):].strip()
        if "|" not in payload:
            print(f"\n{_color('❌ Uso:', '1;31')} /learn add <problema> | <solução> [tags:tag1,tag2]\n")
            return
        problem, rest = payload.split("|", 1)
        solution = rest.strip()
        tags = []
        if "tags:" in solution:
            solution, tags_str = solution.rsplit("tags:", 1)
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        learning_id = store.save(
            problem=problem.strip(),
            solution=solution.strip(),
            tags=list(set(tags + ["manual"])),
            effectiveness_score=2,
        )
        print(f"\n{_color('✅ Aprendizado salvo:', 32)} ID {learning_id}\n")
        return

    if subcmd.startswith("rate "):
        rest = subcmd[len("rate "):].strip()
        tokens = rest.split()
        if len(tokens) < 2 or not tokens[0].isdigit() or tokens[1] not in ("+1", "-1"):
            print(f"\n{_color('❌ Uso:', '1;31')} /learn rate <id> <+1/-1>\n")
            return
        learning_id = int(tokens[0])
        helpful = tokens[1] == "+1"
        store.rate(learning_id, helpful)
        print(f"\n{_color('✅ Feedback registrado:', 32)} ID {learning_id} {'+1' if helpful else '-1'}\n")
        return

    if subcmd.startswith("forget ") or subcmd.startswith("delete "):
        rest = subcmd.split(maxsplit=1)[1].strip()
        if not rest.isdigit():
            print(f"\n{_color('❌ Uso:', '1;31')} /learn forget <id>\n")
            return
        learning_id = int(rest)
        store.delete(learning_id)
        print(f"\n{_color('✅ Aprendizado removido:', 32)} ID {learning_id}\n")
        return

    _print_learning_menu()


def _print_config_menu(config: Dict[str, Any]) -> None:
    """Print current Zeus configuration in a visual card."""
    term_width = _get_term_width()
    title = " ⚙️ CONFIGURAÇÃO ZEUS "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Provider:', 90)} {config.get('zeus_provider', 'unknown')}")
    print(f"{_color('│', 33)}  {_color('Model:', 90)}    {config.get('zeus_model', 'unknown')}")
    print(f"{_color('│', 33)}  {_color('Config file:', 90)} {config.get('config_file', 'unknown')}")
    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)}  {_color('API Keys:', 90)}")
    for key, value in config.get("api_keys_status", {}).items():
        print(f"{_color('│', 33)}    • {_color(key, '1;37')}: {value}")
    print(f"{_color('│', 33)}")
    print(f"{_color('│', 33)}  {_color('Comandos:', 90)}")
    print(f"{_color('│', 33)}    • {_color('/config', 33)}                  - Mostra configuração atual")
    print(f"{_color('│', 33)}    • {_color('/config get <key>', 33)}      - Lê valor de uma variável")
    print(f"{_color('│', 33)}    • {_color('/config set <key> <value>', 33)} - Define variável no .env")
    print(f"{_color('│', 33)}    • {_color('/config list-models [provider]', 33)} - Lista modelos disponíveis")
    print(bottom)
    print()


def _handle_mode_command(text: str) -> None:
    """Handle /mode subcommands to switch execution permission and runtime mode."""
    from zeus.security.permissions import PermissionManager

    parts = text.split(maxsplit=1)
    subcmd = parts[1].lower().strip() if len(parts) > 1 else ""

    pm = PermissionManager()

    if subcmd in ("", "menu"):
        _print_mode_menu(show_commands=True)
        return

    if subcmd == "status":
        _print_mode_menu(show_commands=False)
        return

    if subcmd in ("sandbox", "safe"):
        _set_zeus_env("ZEUS_EXECUTION_PERMISSION", "sandbox_only")
        _set_zeus_env("ZEUS_EXECUTION_MODE", "terminal")
        _set_zeus_env("ZEUS_DRY_RUN", "0")
        _set_zeus_env("ZEUS_READ_ONLY", "0")
        print(f"\n{_color('🛡️  Modo sandbox ativado.', 32)}")
        print(f"{_color('   Terminal do host bloqueado.', 90)}\n")
        return

    if subcmd in ("terminal", "host"):
        _set_zeus_env("ZEUS_EXECUTION_PERMISSION", "allow")
        _set_zeus_env("ZEUS_EXECUTION_MODE", "terminal")
        _set_zeus_env("ZEUS_DRY_RUN", "0")
        _set_zeus_env("ZEUS_READ_ONLY", "0")
        print(f"\n{_color('⚡ Modo terminal ativado.', 33)}")
        print(f"{_color('   run_terminal liberado com confirmação humana.', 90)}")
        print(f"{_color('   Comandos de alto risco pedirão aprovação.', 31)}\n")
        return

    if subcmd == "auto":
        _set_zeus_env("ZEUS_EXECUTION_PERMISSION", "allow")
        _set_zeus_env("ZEUS_EXECUTION_MODE", "auto")
        _set_zeus_env("ZEUS_DRY_RUN", "0")
        _set_zeus_env("ZEUS_READ_ONLY", "0")
        print(f"\n{_color('🚀 Modo automático ativado.', 35)}")
        print(f"{_color('   run_terminal executa sem confirmação.', 90)}")
        print(f"{_color('   Apenas o resultado é apresentado.', 90)}\n")
        return

    if subcmd == "dryrun":
        _set_zeus_env("ZEUS_EXECUTION_PERMISSION", "allow")
        _set_zeus_env("ZEUS_EXECUTION_MODE", "terminal")
        _set_zeus_env("ZEUS_DRY_RUN", "1")
        _set_zeus_env("ZEUS_READ_ONLY", "0")
        print(f"\n{_color('👁️  Modo dry-run ativado.', 36)}")
        print(f"{_color('   Ferramentas mutantes são apenas simuladas.', 90)}\n")
        return

    if subcmd == "readonly":
        _set_zeus_env("ZEUS_EXECUTION_PERMISSION", "deny")
        _set_zeus_env("ZEUS_EXECUTION_MODE", "terminal")
        _set_zeus_env("ZEUS_DRY_RUN", "0")
        _set_zeus_env("ZEUS_READ_ONLY", "1")
        print(f"\n{_color('🔍 Modo somente leitura ativado.', 34)}")
        print(f"{_color('   Apenas ferramentas de leitura estão liberadas.', 90)}\n")
        return

    if subcmd.startswith("file "):
        level = subcmd[len("file "):].strip()
        if level not in PermissionManager.FILE_LEVELS:
            print(f"\n{_color('❌ Nível de arquivo inválido:', '1;31')} {level}")
            print(f"{_color('Use:', 90)} /mode file read_only | project_only | unrestricted\n")
            return
        _set_zeus_env("ZEUS_FILE_PERMISSION", level)
        print(f"\n{_color('📁  Permissão de arquivo:', 32)} {level}\n")
        return

    print(f"\n{_color('❌ Modo desconhecido:', '1;31')} {subcmd}")
    print(f"{_color('Use:', 90)} /mode sandbox | terminal | auto | dryrun | readonly | file <nível>\n")


def _set_zeus_env(key: str, value: str) -> None:
    """Update an env variable both in the current process and in ~/.zeus/.env."""
    os.environ[key] = value
    zeus_home = Path(os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus")))
    env_file = zeus_home / ".env"

    lines: List[str] = []
    if env_file.exists():
        with env_file.open("r", encoding="utf-8") as f:
            lines = f.readlines()

    found = False
    new_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} =") or stripped.startswith(f"#{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    zeus_home.mkdir(parents=True, exist_ok=True)
    with env_file.open("w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _print_mode_menu(show_commands: bool = True) -> None:
    """Print current execution mode and available options in a status card."""
    from zeus.security.permissions import PermissionManager

    pm = PermissionManager()
    exec_mode = pm.exec_level
    file_mode = pm.file_level
    runtime_mode = pm.execution_mode
    dry_run = pm.dry_run

    term_width = _get_term_width()
    title = " STATUS DO AGENTE "
    line_length = max(10, term_width - len(title) - 6)
    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
    bottom = _color("╰" + "─" * (term_width - 3), 33)
    sep = _color("│" + "─" * (term_width - 3), 33)

    if exec_mode == "sandbox":
        exec_label = f"{_color('●', 32)} {_color('SANDBOX', '1;32')}"
        exec_detail = "Restringe comandos ao sandbox"
    elif runtime_mode == "auto":
        exec_label = f"{_color('●', 35)} {_color('AUTO', '1;35')}"
        exec_detail = "Executa comandos automaticamente"
    else:
        exec_label = f"{_color('●', 33)} {_color('TERMINAL', '1;33')} ({_color('Manual', 37)})"
        exec_detail = "Permite comandos com confirmação"

    file_labels = {
        "read_only": f"{_color('Apenas Leitura', 32)}",
        "project_only": f"{_color('Projeto Apenas', 33)}",
        "unrestricted": f"{_color('Total', 31)}",
    }
    file_label = file_labels.get(file_mode, file_mode)

    dry_label = _color("ATIVADO", 36) if dry_run else _color("DESATIVADO", 90)

    print()
    print(top)
    print(f"{_color('│', 33)}  {_color('Modo de Execução:', 90)}    {exec_label}")
    print(f"{_color('│', 33)}  {_color('Permissão de Arquivos:', 90)} {file_label}")
    print(f"{_color('│', 33)}  {_color('Simulação (Dry-run):', 90)} {dry_label}")
    if show_commands:
        print(sep)
        print(f"{_color('│', 33)}  {_color('COMANDOS DE CONFIGURAÇÃO', '1;37')}")
        print(f"{_color('│', 33)}  • {_color('/mode status', 33)}    - Mostra apenas o status atual")
        print(f"{_color('│', 33)}  • {_color('/mode sandbox', 33)}   - {exec_detail if exec_mode == 'sandbox' else 'Restringe comandos ao sandbox'}")
        print(f"{_color('│', 33)}  • {_color('/mode terminal', 33)}  - Permite comandos com confirmação")
        print(f"{_color('│', 33)}  • {_color('/mode auto', 33)}      - Executa comandos automaticamente")
        print(f"{_color('│', 33)}  • {_color('/mode dryrun', 33)}    - Apenas simula as ações")
        print(f"{_color('│', 33)}  • {_color('/mode file <read_only|project_only|unrestricted>', 33)}")
    print(bottom)
    print()


def _handle_config_command(text: str) -> None:
    """Handle /config subcommands."""
    from zeus.tools.config_tools import get_zeus_config, list_available_models, update_zeus_config

    parts = text.split(maxsplit=2)
    subcmd = parts[1].lower() if len(parts) > 1 else "show"

    if subcmd in ("show", "get", "list"):
        if subcmd == "get" and len(parts) >= 3:
            key = parts[2].strip().upper()
            value = os.getenv(key)
            status = f"{_color('Configurado:', 32)} ***{value[-4:]}" if value else f"{_color('Não configurado', 31)}"
            print(f"\n{_color('🔑', 33)} {key}: {status}\n")
        elif subcmd == "list" and len(parts) >= 3:
            provider = parts[2].strip()
            models = list_available_models(provider)
            if "error" in models:
                print(f"\n{_color('❌', '1;31')} {models['error']}\n")
            else:
                print(f"\n{_color('🤖 Modelos', 33)} {_color(provider, '1;33')}:")
                for m in models.get("models", []):
                    print(f"  • {m}")
                print()
        else:
            _print_config_menu(get_zeus_config())

    elif subcmd in ("set", "update"):
        if len(parts) < 3 or " " not in parts[2]:
            print(f"\n{_color('❌ Uso:', '1;31')} /config set <KEY> <value>\n")
            return
        key, value = parts[2].split(" ", 1)
        result = update_zeus_config(key, value)
        if result.get("status") == "success":
            print(f"\n{_color('✅ Configuração salva:', 32)} {result['key']} = {result['new_value_masked']}\n")
            if result['key'] in ("ZEUS_PROVIDER", "ZEUS_MODEL"):
                _load_env(override=True)
                print(f"{_color('🔄 Sessão atual recarregada:', 33)} provider={os.getenv('ZEUS_PROVIDER')} model={os.getenv('ZEUS_MODEL')}\n")
        else:
            print(f"\n{_color('❌ Erro:', '1;31')} {result.get('error', 'unknown')}\n")

    else:
        _print_config_menu(get_zeus_config())



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
    inner_width = max(20, term_width - 6)

    header_top = _color("╭──", 32) + _color(title, "1;32")
    top_vis = _visible_width(header_top)
    pad_len = max(2, term_width - top_vis - 1)
    top = header_top + _color("─" * pad_len, 32)
    bottom = _color("╰" + "─" * (term_width - 3), 32)

    formatted_lines = _format_markdown_for_cli(str(step.get("result", "")), max_width=inner_width)

    print()
    print(top)
    for line in formatted_lines:
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


def _print_tool_result(name: Optional[str], args: Any, result: Dict[str, Any]) -> None:
    """Print detailed visual output for file creation (code) and file edits (line diffs)."""
    if not isinstance(result, dict):
        return

    res_data = result.get("result") if isinstance(result.get("result"), dict) else result
    if not isinstance(res_data, dict) or res_data.get("status") != "success":
        return

    term_width = _get_term_width()
    inner_width = max(20, term_width - 8)

    # 1. File Created Case
    if res_data.get("action") == "created" or (name in ("write_file", "create_file") and "content" in res_data and "old_content" not in res_data and "diff" not in res_data):
        file_path = res_data.get("path") or (args.get("path") if isinstance(args, dict) else "arquivo")
        content = res_data.get("content") or (args.get("content") if isinstance(args, dict) else "")

        title = f" 📄 ARQUIVO CRIADO: {file_path} "
        line_length = max(10, term_width - len(title) - 6)
        top = _color("╭──", 32) + _color(title, "1;32") + _color("─" * line_length, 32)
        bottom = _color("╰" + "─" * (term_width - 3), 32)

        print()
        print(top)
        lines = content.splitlines()
        max_preview = 60
        for idx, line_text in enumerate(lines[:max_preview], 1):
            num_str = f"{idx:3d} │ "
            truncated_line = line_text[:inner_width - len(num_str)]
            print(f"{_color('│', 32)} {_color(num_str, 90)}{_color(truncated_line, 37)}")
        if len(lines) > max_preview:
            remaining_lines = len(lines) - max_preview
            print(f"{_color('│', 32)} {_color(f'  ... ({remaining_lines} linhas ocultas)', 90)}")
        print(bottom)
        print()
        return

    # 2. File Modified Case (Diff Display)
    if res_data.get("action") == "modified" or "diff" in res_data or (name in ("write_file", "replace_file_content", "modify_file") and "old_content" in res_data):
        file_path = res_data.get("path") or (args.get("path") if isinstance(args, dict) else "arquivo")
        diff_text = res_data.get("diff", "")

        if not diff_text and "old_content" in res_data and "content" in res_data:
            import difflib
            old_lines = res_data["old_content"].splitlines(keepends=True)
            new_lines = res_data["content"].splitlines(keepends=True)
            diff_text = "".join(difflib.unified_diff(old_lines, new_lines, fromfile="antigo", tofile="novo"))

        if not diff_text:
            return

        title = f" 📝 ARQUIVO ALTERADO: {file_path} "
        line_length = max(10, term_width - len(title) - 6)
        top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * line_length, 33)
        bottom = _color("╰" + "─" * (term_width - 3), 33)

        print()
        print(top)
        diff_lines = diff_text.splitlines()
        for diff_line in diff_lines:
            if diff_line.startswith("---") or diff_line.startswith("+++"):
                continue
            if diff_line.startswith("@@"):
                print(f"{_color('│', 33)} {_color(diff_line[:inner_width], '1;33')}")
            elif diff_line.startswith("-"):
                # Linha Antiga (Vermelho)
                line_content = diff_line[1:]
                print(f"{_color('│', 33)} {_color('🔴 - ', '1;31')}{_color(line_content[:inner_width - 5], 31)}")
            elif diff_line.startswith("+"):
                # Nova Linha Alterada (Verde)
                line_content = diff_line[1:]
                print(f"{_color('│', 33)} {_color('🟢 + ', '1;32')}{_color(line_content[:inner_width - 5], 32)}")
            else:
                # Linha Inalterada (Contexto)
                line_content = diff_line[1:] if diff_line.startswith(" ") else diff_line
                print(f"{_color('│', 33)}    {_color(line_content[:inner_width - 4], 90)}")
        print(bottom)
        print()
        return


def _print_prompt_header(logger, metrics, active_skill: Optional[set] = None) -> None:
    term_width = _get_term_width()
    provider = os.getenv("ZEUS_PROVIDER", "openrouter")
    model = os.getenv("ZEUS_MODEL", "unknown")
    snap = metrics.snapshot()
    in_tokens = _format_tokens(snap.get("llm_input_tokens", 0))
    out_tokens = _format_tokens(snap.get("llm_output_tokens", 0))
    duration = _format_duration(time.time() - snap.get("started_at", time.time()))
    session_short = logger.session_id[:8]
    skill_label = _current_skill_label(active_skill)

    from zeus.mcp.manager import MCPManager
    mcp_mgr = MCPManager.get_instance()
    connected = [name for name, c in mcp_mgr.clients.items() if c.is_connected]

    llm_conn = f"🌐 API:{provider}"
    tools_conn = f"🔌 MCP:{','.join(connected)}" if connected else "⚡ Tools:Native"

    title = f" 👤 VOCÊ | {model} ({llm_conn}) | {tools_conn} | in:{in_tokens} out:{out_tokens} | {duration} | {session_short} | {skill_label} "
    remaining = max(5, term_width - len(title) - 6)

    top = _color("╭──", 33) + _color(title, "1;33") + _color("─" * remaining, 33)
    print(f"\n{top}")




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
            response = run_agent(args.query, session_id=logger.session_id, tool_callback=_print_tool_execution)
        logger.log_turn("assistant", response)
        _print_agent_response(response)
        if args.summary:
            print("\n--- Resumo da sessão ---")
            print(run_summary(session_id=logger.session_id))
        return

    session = PromptSession(
        history=FileHistory(".zeus_history"),
        completer=ZeusCommandCompleter(),
    )
    global active_session
    active_session = session

    # Connect interactive file permission callback.
    from zeus.tools.file import set_file_permission_callback
    set_file_permission_callback(_ask_file_permission_prompt)

    # Wire the same interactive confirmation callback into the global PermissionManager
    # so that terminal-mode tool confirmations (human-in-the-loop) can prompt the user.
    from zeus.security.permissions import PermissionManager, set_global_permission_manager
    set_global_permission_manager(PermissionManager(confirm_callback=_ask_file_permission_prompt))

    _print_banner(logger, metrics)
    active_skill: Optional[set] = None

    # Auto-start configured MCP servers upon startup
    try:
        from zeus.mcp.manager import MCPManager
        MCPManager.get_instance().start_all()
    except Exception:
        pass


    while True:

        _print_prompt_header(logger, get_metrics(logger.session_id), active_skill)
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

        if text == "/models":
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
                tool_callback=_print_tool_execution,
                tool_result_callback=_print_tool_result,
                tool_filter=active_skill,
            )

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



if __name__ == "__main__":
    main()
