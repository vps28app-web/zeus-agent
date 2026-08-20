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
