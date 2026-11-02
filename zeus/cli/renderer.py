"""Terminal rendering and ANSI styling utilities for Zeus CLI."""

import os
import re
import shutil
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

_COLOR_ENABLED: Optional[bool] = None


def _supports_color() -> bool:
    """Return True if the terminal supports ANSI colors.

    Honors NO_COLOR, FORCE_COLOR, TERM=dumb, and non-TTY output.
    """
    if os.getenv("FORCE_COLOR", "").strip():
        return True
    if os.getenv("NO_COLOR", "").strip():
        return False
    if os.getenv("TERM", "").lower() == "dumb":
        return False
    if not (sys.stdout.isatty() and sys.stderr.isatty()):
        return False
    return True


def _color(text: str, code: Any) -> str:
    """Wrap text in ANSI color codes when color is enabled."""
    global _COLOR_ENABLED
    main_mod = sys.modules.get("zeus.cli.main")
    if main_mod is not None:
        enabled = getattr(main_mod, "_COLOR_ENABLED", None)
        if enabled is None:
            enabled = _supports_color()
            setattr(main_mod, "_COLOR_ENABLED", enabled)
    else:
        if _COLOR_ENABLED is None:
            _COLOR_ENABLED = _supports_color()
        enabled = _COLOR_ENABLED

    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


def _visible_width(text: str) -> int:
    """Return visible width of a string, stripping ANSI escape codes."""
    return len(re.sub(r"\x1b\[[0-9;]*m", "", text))


def _truncate_visible(text: str, width: int, suffix: str = "...") -> str:
    """Truncate text so visible width <= width, preserving ANSI codes."""
    if _visible_width(text) <= width:
        return text
    suffix_width = _visible_width(suffix)
    avail = max(0, width - suffix_width)
    # Strip ANSI, truncate, then re-apply the leading ANSI codes from original
    plain = re.sub(r"\x1b\[[0-9;]*m", "", text)
    leading_codes = ""
    match = re.match(r"(\x1b\[[0-9;]*m)+", text)
    if match:
        leading_codes = match.group(0)
    truncated = plain[:avail]
    return f"{leading_codes}{truncated}{suffix}\033[0m"


def _pad_center(text: str, width: int) -> str:
    vis = _visible_width(text)
    if vis > width:
        text = _truncate_visible(text, width)
        vis = _visible_width(text)
    pad = width - vis
    left = pad // 2
    right = pad - left
    return " " * left + text + " " * right


def _pad_left(text: str, width: int) -> str:
    vis = _visible_width(text)
    if vis > width:
        text = _truncate_visible(text, width)
        vis = _visible_width(text)
    pad = width - vis
    return text + " " * pad


def _get_term_width() -> int:
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    return max(40, min(cols, 160))


def _format_command_lines(inner_width: int) -> List[str]:
    """Format the slash-command list into two balanced lines inside the banner."""
    prefix = "  Comandos:"
    prefix_width = _visible_width(prefix)
    commands = ["/new", "/reset", "/clear", "/skills", "/models", "/mode", "/summary", "/help", "/exit"]

    # Try to split into two balanced groups
    mid = (len(commands) + 1) // 2
    group1 = commands[:mid]
    group2 = commands[mid:]

    line1 = prefix + " " + "  ".join(group1)
    line2 = " " * prefix_width + " " + "  ".join(group2)

    # If the first group is too wide, fall back to greedy wrapping
    if _visible_width(line1) > inner_width:
        lines: List[str] = []
        current = prefix
        current_width = prefix_width
        indent = " " * prefix_width
        for cmd in commands:
            cmd_width = _visible_width(cmd)
            if current == prefix:
                separator = " "
                sep_width = 1
            else:
                separator = "  "
                sep_width = 2
            if current_width + sep_width + cmd_width <= inner_width:
                current += separator + cmd
                current_width += sep_width + cmd_width
            else:
                lines.append(current)
                current = indent + " " + cmd
                current_width = prefix_width + 1 + cmd_width
        if current:
            lines.append(current)
        return lines

    if _visible_width(line2) > inner_width:
        # Second group too long; move commands to new lines
        lines = [line1]
        current = " " * prefix_width
        current_width = prefix_width
        for cmd in group2:
            cmd_width = _visible_width(cmd)
            separator = "" if current == " " * prefix_width else "  "
            sep_width = 0 if current == " " * prefix_width else 2
            if current_width + sep_width + cmd_width <= inner_width:
                current += separator + cmd
                current_width += sep_width + cmd_width
            else:
                lines.append(current)
                current = " " * prefix_width + cmd
                current_width = prefix_width + cmd_width
        if current:
            lines.append(current)
        return lines

    return [line1, line2]


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


def _context_bar(session_id: str, width: int = 12) -> str:
    """Render an ASCII progress bar showing current context usage percentage.

    Estimates context size from session history plus system prompt, using
    ZEUS_MAX_CONTEXT_TOKENS (default 8000) as the limit. Colors shift from
    green to yellow to red as usage grows.
    """
    from zeus.memory.context import estimate_tokens

    max_tokens = int(os.getenv("ZEUS_MAX_CONTEXT_TOKENS", "8000"))
    if max_tokens <= 0:
        max_tokens = 8000

    try:
        from zeus.memory.session_log import get_session_messages
        messages = get_session_messages(session_id, limit=100)
    except Exception:
        messages = []

    # rough system prompt estimate; actual prompt is built in agent.py
    system_estimate = 1500
    history_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    total_tokens = system_estimate + history_tokens

    ratio = min(total_tokens / max_tokens, 1.0)
    percent = int(ratio * 100)
    filled = int(ratio * width)
    empty = width - filled
    bar_body = "█" * filled + "░" * empty
    if percent < 60:
        color = "1;32"
    elif percent < 85:
        color = "1;33"
    else:
        color = "1;31"
    return _color(f"{bar_body} {percent}%", color)


def _apply_inline_formatting(text: str) -> str:
    """Apply ANSI styling to inline markdown elements: **bold**, `code`, key-value tags."""
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
    ]

    inner_width = max(50, min(_get_term_width() - 4, 80))
    info_lines.extend(_format_command_lines(inner_width))

    top = _color('╔' + '═' * inner_width + '╗', 90)
    bottom = _color('╚' + '═' * inner_width + '╝', 90)

    def box_line(text: str = "", center: bool = False) -> str:
        text = _truncate_visible(text, inner_width)
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


def _print_user_closing() -> None:
    """Close the user input box visually adapting to terminal width."""
    term_width = _get_term_width()
    print(_color("╰" + "─" * (term_width - 3), 33))


def _print_tool_execution(name: Optional[str], args: Any) -> None:
    """Print a notification when the agent executes a tool."""
    tool_name = name or ""
    terminal_tools = {
        "run_terminal",
        "run_sandboxed",
        "run_sandboxed_command",
        "run_background_command",
        "execute_shell_script",
    }

    if tool_name in terminal_tools:
        # Se for comando no terminal, exibe o comando limpo sendo executado
        cmd = ""
        if isinstance(args, dict):
            cmd = args.get("command") or args.get("cmd") or args.get("script") or ""
        elif isinstance(args, str):
            cmd = args
        cmd = str(cmd).strip()
        if len(cmd) > 80:
            cmd = cmd[:77] + "..."
        if cmd:
            print(f"  {_color('⚡ Executando:', 35)} {_color(cmd, '1;35')}")
        else:
            print(f"  {_color('⚡ Executando...', 35)}")
    else:
        # Para ferramentas internas (web_search, web_extract, etc.), apenas indica que está trabalhando
        print(f"  {_color('⚡ Executando...', 35)}")


def _print_live_output(chunk: str, stream: str) -> None:
    """Print a chunk of live command output as it arrives."""
    if not chunk:
        return
    if stream == "stderr":
        print(f"  {_color(chunk, 31)}")
    else:
        print(f"  {chunk}")


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
                line_content = diff_line[1:]
                print(f"{_color('│', 33)} {_color('🔴 - ', '1;31')}{_color(line_content[:inner_width - 5], 31)}")
            elif diff_line.startswith("+"):
                line_content = diff_line[1:]
                print(f"{_color('│', 33)} {_color('🟢 + ', '1;32')}{_color(line_content[:inner_width - 5], 32)}")
            else:
                line_content = diff_line[1:] if diff_line.startswith(" ") else diff_line
                print(f"{_color('│', 33)}    {_color(line_content[:inner_width - 4], 90)}")
        print(bottom)
        print()
        return


def _print_prompt_header(logger, metrics) -> None:
    term_width = _get_term_width()
    provider = os.getenv("ZEUS_PROVIDER", "openrouter")
    model = os.getenv("ZEUS_MODEL", "unknown")
    snap = metrics.snapshot()
    in_tokens = _format_tokens(snap.get("llm_input_tokens", 0))
    out_tokens = _format_tokens(snap.get("llm_output_tokens", 0))
    duration = _format_duration(time.time() - snap.get("started_at", time.time()))
    context_bar = _context_bar(logger.session_id)

    from zeus.mcp.manager import MCPManager
    mcp_mgr = MCPManager.get_instance()
    connected = [name for name, c in mcp_mgr.clients.items() if c.is_connected]

    # Current execution mode label.
    from zeus.security.permissions import get_global_permission_manager
    pm = get_global_permission_manager()
    exec_level = pm.exec_level
    runtime_mode = pm.execution_mode
    if pm.read_only:
        mode_label = "readonly"
        mode_color = "1;34"
    elif exec_level == "deny":
        mode_label = "deny"
        mode_color = "1;31"
    elif exec_level == "sandbox_only":
        mode_label = "sandbox"
        mode_color = "1;32"
    elif runtime_mode == "auto":
        mode_label = "auto"
        mode_color = "1;35"
    else:
        mode_label = "terminal"
        mode_color = "1;33"
    if pm.dry_run and mode_label in ("terminal", "auto"):
        mode_label += "+dryrun"

    llm_conn = f"🌐 API:{provider}"
    tools_conn = f"🔌 MCP:{','.join(connected)}" if connected else "⚡ Tools:Native"

    rest = (
        f" {model} ({llm_conn}) | {tools_conn} "
        f"| in:{in_tokens} out:{out_tokens} | {duration} | {context_bar} "
    )
    title = (
        f"\033[1;33m 👤 VOCÊ | "
        f"\033[{mode_color}mMODO:{mode_label}"
        f"\033[1;33m |{rest}"
    )
    remaining = max(5, term_width - _visible_width(title) - 6)

    top = _color("╭──", 33) + title + _color("─" * remaining, 33)
    print(f"\n{top}")
