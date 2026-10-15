"""Tests for CLI helpers."""

import io
from contextlib import redirect_stdout

from zeus.cli.main import (
    SKILL_SETS,
    ZeusCommandCompleter,
    _format_tokens,
    _print_command_menu,
    _print_skills_menu,
)


def test_print_command_menu_shows_models_command():
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_command_menu()
    output = buf.getvalue()
    assert "/models" in output
    assert "/provider" not in output
    assert "/models" in ZeusCommandCompleter.COMMANDS
    assert "/provider" not in ZeusCommandCompleter.COMMANDS


    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_command_menu()
    output = buf.getvalue()
    assert "MENU DE COMANDOS" in output
    assert "/new" in output
    assert "/plan" in output
    assert "/exit" in output
    assert "/help" in output


def test_print_skills_menu_shows_available_sets():
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_skills_menu(active_filter=None)
    output = buf.getvalue()
    assert "SKILL SETS" in output
    for key in SKILL_SETS:
        assert f"/skills {key}" in output


def test_print_skills_menu_shows_active_marker():
    buf = io.StringIO()
    active = SKILL_SETS["coding"]["tags"]
    with redirect_stdout(buf):
        _print_skills_menu(active_filter=active)
    output = buf.getvalue()
    assert "coding" in output
    # check that the active set is rendered in the menu
    assert SKILL_SETS["coding"]["label"] in output


def test_format_tokens():
    assert _format_tokens(0) == "0"
    assert _format_tokens(500) == "500"
    assert _format_tokens(1200) == "1.2k"
    assert _format_tokens(12000) == "12k"
    assert _format_tokens(850000) == "850k"
    assert _format_tokens(15000000) == "15m"
    assert _format_tokens(2500000000) == "2.5b"


def test_context_bar_colors_and_clamping(monkeypatch, tmp_path):
    from zeus.cli.main import _context_bar

    monkeypatch.delenv("ZEUS_MAX_CONTEXT_TOKENS", raising=False)
    # empty session => only system estimate (1500 / 8000 = 18%)
    bar = _context_bar("nonexistent_session", width=10)
    assert "%" in bar

    monkeypatch.setenv("ZEUS_MAX_CONTEXT_TOKENS", "4000")
    bar = _context_bar("nonexistent_session", width=10)
    # 1500 / 4000 = 37%
    assert "37%" in bar


def test_context_bar_increases_with_history(monkeypatch, tmp_path):
    from zeus.cli.main import _context_bar
    from zeus.memory.session_log import SessionLogger

    monkeypatch.delenv("ZEUS_MAX_CONTEXT_TOKENS", raising=False)
    logger = SessionLogger()
    logger.log_turn("user", "x " * 2000)  # ~1000 tokens
    bar = _context_bar(logger.session_id, width=10)
    # (1500 + ~1000) / 8000 = ~31-33%
    assert any(p in bar for p in ("31%", "32%", "33%"))


def test_context_bar_respects_color_off(monkeypatch):
    from zeus.cli.main import _context_bar

    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr("zeus.cli.main._COLOR_ENABLED", None, raising=False)
    bar = _context_bar("nonexistent_session", width=10)
    assert "\033[" not in bar
    assert "%" in bar


def test_format_markdown_for_cli():
    from zeus.cli.main import _format_markdown_for_cli
    md = "# Title\n\n## Subtitle\n- **Item 1**: `code` text\n```python\nprint('hello')\n```"
    lines = _format_markdown_for_cli(md, max_width=60)
    text_out = "\n".join(lines)
    assert "TITLE" in text_out
    assert "Subtitle" in text_out
    assert "Item 1" in text_out
    assert "CODE" in text_out
    assert "print('hello')" in text_out


def test_print_agent_response_card_status():
    from zeus.cli.main import _print_agent_response
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_agent_response("All systems operational.", title="TEST", status="ok")
    output = buf.getvalue()
    assert "Resposta Exata" not in output
    assert "TEST" in output
    assert "All systems operational." in output

    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        _print_agent_response("Permission denied", title="SECURITY", status="warning")
    output2 = buf2.getvalue()
    assert "Atenção" in output2
    assert "SECURITY" in output2




def test_print_command_menu_shows_new_modes():
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_command_menu()
    output = buf.getvalue()
    assert "/mode <sandbox|terminal|auto|dryrun|readonly>" in output


def test_handle_mode_command_sets_terminal_mode(monkeypatch):
    import os
    import sys
    cli_main = sys.modules["zeus.cli.main"]

    env_updates = {}

    def fake_set_zeus_env(key, value):
        env_updates[key] = value
        os.environ[key] = value

    monkeypatch.setattr(cli_main, "_set_zeus_env", fake_set_zeus_env)

    cli_main._handle_mode_command("/mode terminal")
    assert env_updates.get("ZEUS_EXECUTION_PERMISSION") == "allow"
    assert env_updates.get("ZEUS_EXECUTION_MODE") == "terminal"
    assert env_updates.get("ZEUS_DRY_RUN") == "0"
    assert env_updates.get("ZEUS_READ_ONLY") == "0"


def test_handle_mode_command_sets_auto_mode(monkeypatch):
    import os
    import sys
    cli_main = sys.modules["zeus.cli.main"]

    env_updates = {}

    def fake_set_zeus_env(key, value):
        env_updates[key] = value
        os.environ[key] = value

    monkeypatch.setattr(cli_main, "_set_zeus_env", fake_set_zeus_env)

    cli_main._handle_mode_command("/mode auto")
    assert env_updates.get("ZEUS_EXECUTION_PERMISSION") == "allow"
    assert env_updates.get("ZEUS_EXECUTION_MODE") == "auto"
    assert env_updates.get("ZEUS_DRY_RUN") == "0"
    assert env_updates.get("ZEUS_READ_ONLY") == "0"


def test_handle_mode_command_sets_dryrun_mode(monkeypatch):
    import os
    import sys
    cli_main = sys.modules["zeus.cli.main"]

    env_updates = {}

    def fake_set_zeus_env(key, value):
        env_updates[key] = value
        os.environ[key] = value

    monkeypatch.setattr(cli_main, "_set_zeus_env", fake_set_zeus_env)

    cli_main._handle_mode_command("/mode dryrun")
    assert env_updates.get("ZEUS_EXECUTION_PERMISSION") == "allow"
    assert env_updates.get("ZEUS_DRY_RUN") == "1"
    assert env_updates.get("ZEUS_READ_ONLY") == "0"


def test_handle_mode_command_sets_readonly_mode(monkeypatch):
    import os
    import sys
    cli_main = sys.modules["zeus.cli.main"]

    env_updates = {}

    def fake_set_zeus_env(key, value):
        env_updates[key] = value
        os.environ[key] = value

    monkeypatch.setattr(cli_main, "_set_zeus_env", fake_set_zeus_env)

    cli_main._handle_mode_command("/mode readonly")
    assert env_updates.get("ZEUS_EXECUTION_PERMISSION") == "deny"
    assert env_updates.get("ZEUS_READ_ONLY") == "1"
    assert env_updates.get("ZEUS_DRY_RUN") == "0"



