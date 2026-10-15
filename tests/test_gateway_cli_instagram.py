"""Tests for Instagram gateway CLI routing."""

import sys

from zeus.gateway import cli as gateway_cli


def test_gateway_setup_instagram_dispatches(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["zeus-gateway", "setup", "instagram"])
    monkeypatch.setattr(gateway_cli, "_load_env", lambda: None)
    monkeypatch.setattr(gateway_cli, "setup_instagram", lambda: True)

    assert gateway_cli.main() == 0


def test_gateway_start_instagram_dispatches(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["zeus-gateway", "start", "instagram", "--mode", "manual"])
    monkeypatch.setattr(gateway_cli, "_load_env", lambda: None)
    monkeypatch.setattr(gateway_cli, "ensure_configured", lambda platform: platform == "instagram")
    monkeypatch.setattr(gateway_cli, "_start_instagram", lambda: calls.append(True))

    assert gateway_cli.main() == 0
    assert calls == [True]
