"""Tests for CLI helpers."""

import io
from contextlib import redirect_stdout

from zeus.cli.main import SKILL_SETS, _format_tokens, _print_command_menu, _print_skills_menu


def test_print_command_menu_shows_slash_commands():
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


