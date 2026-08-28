"""Hardening tests for Zeus CLI behavior."""

import subprocess
import sys
from unittest import mock

import pytest

import zeus.gateway.cli as gateway_cli_module
from zeus.cli.main import _color, _handle_config_command, _supports_color, main


def _get_cli_main_module():
    """Return the zeus.cli.main module object (not the main function shadowed by __init__)."""
    return sys.modules["zeus.cli.main"]


class TestColorSupport:
    def test_supports_color_respects_no_color(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        assert _supports_color() is False

    def test_supports_color_force_color_overrides_no_tty(self, monkeypatch):
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert _supports_color() is True

    def test_supports_color_dumb_term_disabled(self, monkeypatch):
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        with mock.patch.object(sys.stdout, "isatty", return_value=True), \
             mock.patch.object(sys.stderr, "isatty", return_value=True):
            assert _supports_color() is False

    def test_color_disabled_when_no_color(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        _get_cli_main_module()._COLOR_ENABLED = None
        assert _color("text", "1;31") == "text"

    def test_color_enabled_when_forced(self, monkeypatch):
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        _get_cli_main_module()._COLOR_ENABLED = None
        assert _color("text", "1;31") == "\033[1;31mtext\033[0m"


class TestCliArgumentParsing:
    def test_version_flag_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "-m", "zeus.cli", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_no_color_flag_disables_color(self, monkeypatch, capsys):
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            with mock.patch.object(sys, "argv", ["zeus", "--version"]):
                main()
        assert exc_info.value.code == 0

    def test_query_mode_returns_nonzero_on_agent_error(self, monkeypatch):
        cli_mod = _get_cli_main_module()
        monkeypatch.setattr(
            cli_mod,
            "run_agent",
            mock.Mock(side_effect=RuntimeError("LLM indisponível")),
        )
        monkeypatch.setattr(
            "zeus.memory.session_log.get_logger",
            mock.Mock(),
        )
        monkeypatch.setattr(
            "zeus.observability.metrics.get_metrics",
            mock.Mock(),
        )
        with mock.patch.object(sys, "argv", ["zeus", "-q", "hello"]):
            result = main()
        assert result == 1


class TestConfigCommandHardening:
    def test_config_get_masks_secret_value(self, monkeypatch, capsys):
        monkeypatch.setenv("ZEUS_TELEGRAM_TOKEN", "supersecrettoken1234")
        monkeypatch.setenv("NO_COLOR", "1")
        _get_cli_main_module()._COLOR_ENABLED = False
        _handle_config_command("/config get ZEUS_TELEGRAM_TOKEN")
        captured = capsys.readouterr()
        assert "supersecrettoken1234" not in captured.out
        assert "***" in captured.out or "****" in captured.out

    def test_config_get_shows_plain_non_secret_value(self, monkeypatch, capsys):
        monkeypatch.setenv("ZEUS_PROVIDER", "openrouter")
        monkeypatch.setenv("NO_COLOR", "1")
        _get_cli_main_module()._COLOR_ENABLED = False
        _handle_config_command("/config get ZEUS_PROVIDER")
        captured = capsys.readouterr()
        assert "openrouter" in captured.out

    def test_config_get_missing_key_shows_error(self, monkeypatch, capsys):
        monkeypatch.delenv("MISSING_ZEUS_KEY_XYZ", raising=False)
        monkeypatch.setenv("NO_COLOR", "1")
        _get_cli_main_module()._COLOR_ENABLED = False
        _handle_config_command("/config get MISSING_ZEUS_KEY_XYZ")
        captured = capsys.readouterr()
        assert "não configurado" in captured.out


class TestGatewayCliHardening:
    def test_malformed_telegram_chat_ids_raises_clear_error(self, monkeypatch):
        monkeypatch.setenv("ZEUS_TELEGRAM_ALLOWED_CHAT_IDS", "123,abc,456")
        with pytest.raises(RuntimeError) as exc_info:
            gateway_cli_module._telegram_chat_ids_from_env()
        assert "não numéricos" in str(exc_info.value)

    def test_malformed_single_chat_id_raises_clear_error(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "not-a-number")
        monkeypatch.delenv("ZEUS_TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
        monkeypatch.delenv("TELEGRAM_ALLOWED_USERS", raising=False)
        with pytest.raises(RuntimeError) as exc_info:
            gateway_cli_module._telegram_chat_ids_from_env()
        assert "número inteiro" in str(exc_info.value)

    def test_gateway_version_flag_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "-m", "zeus.gateway", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_gateway_start_without_config_returns_one(self, monkeypatch):
        monkeypatch.setattr(gateway_cli_module, "ensure_configured", mock.Mock(return_value=False))
        with mock.patch.object(sys, "argv", ["zeus-gateway", "start", "telegram"]):
            result = gateway_cli_module.main()
        assert result == 1


class TestSignalAndExitCodes:
    def test_main_returns_int(self):
        assert callable(main)
        assert main.__annotations__.get("return") is int

    def test_gateway_main_returns_int(self):
        assert callable(gateway_cli_module.main)
        assert gateway_cli_module.main.__annotations__.get("return") is int
