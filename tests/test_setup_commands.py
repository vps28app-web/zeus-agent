"""Tests for the interactive provider setup flow."""

import importlib
import os
import sys

from zeus.cli import setup_commands


def test_setup_command_dispatches_to_full_wizard(monkeypatch):
    cli_main = importlib.import_module("zeus.cli.main")
    calls = []
    monkeypatch.setattr(sys, "argv", ["zeus", "setup"])
    monkeypatch.setattr(cli_main, "_load_env", lambda: None)
    monkeypatch.setattr(
        "zeus.cli.onboarding.run_setup_wizard",
        lambda: calls.append(True) or True,
    )

    assert cli_main.main() == 0
    assert calls == [True]


def test_setup_model_keeps_existing_api_key_without_prompt(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.setenv("ZEUS_PROVIDER", "opencode_go")
    monkeypatch.setenv("ZEUS_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "old-key")
    monkeypatch.setenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
    monkeypatch.setattr(
        setup_commands,
        "_select_provider_interactive",
        lambda providers, current: "opencode_go",
    )
    monkeypatch.setattr(setup_commands, "fetch_models", lambda provider: {"error": "unauthorized"})
    monkeypatch.setattr(
        setup_commands,
        "_select_model_interactive",
        lambda provider, models, current, source: "deepseek-v4-pro",
    )
    prompts = []
    monkeypatch.setattr(
        setup_commands,
        "_get_input",
        lambda prompt, secret=False: prompts.append((prompt, secret)) or "replacement-key",
    )

    assert setup_commands._setup_model() is True

    saved = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENCODE_GO_API_KEY=" not in saved
    assert os.environ["OPENCODE_GO_API_KEY"] == "old-key"
    assert prompts == []
    assert "replacement-key" not in capsys.readouterr().out


def test_setup_model_prompts_for_missing_api_key(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.setenv("ZEUS_PROVIDER", "opencode_go")
    monkeypatch.setenv("ZEUS_MODEL", "deepseek-v4-pro")
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.setenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
    monkeypatch.setattr(
        setup_commands,
        "_select_provider_interactive",
        lambda providers, current: "opencode_go",
    )
    monkeypatch.setattr(setup_commands, "fetch_models", lambda provider: {"error": "missing key"})
    monkeypatch.setattr(
        setup_commands,
        "_select_model_interactive",
        lambda provider, models, current, source: "deepseek-v4-pro",
    )
    prompts = []

    def fake_prompt(prompt, secret=False):
        prompts.append((prompt, secret))
        return "new-key"

    monkeypatch.setattr(setup_commands, "_get_input", fake_prompt)

    assert setup_commands._setup_model() is True

    saved = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENCODE_GO_API_KEY=new-key" in saved
    assert os.environ["OPENCODE_GO_API_KEY"] == "new-key"
    assert prompts == [("OPENCODE_GO_API_KEY (deixe em branco para pular)", True)]
    assert "new-key" not in capsys.readouterr().out
