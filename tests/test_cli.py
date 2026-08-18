"""Tests for CLI helpers."""

import io
from contextlib import redirect_stdout

from zeus.cli.main import _print_command_menu


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
