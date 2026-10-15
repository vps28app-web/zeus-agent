"""Tests for interactive secret configuration commands."""

from zeus.cli.main import _handle_config_command, _print_config_menu


def test_config_menu_includes_opencode_key_example(capsys):
    _print_config_menu({"api_keys_status": {}})
    output = capsys.readouterr().out
    assert "/config set OPENCODE_GO_API_KEY" in output


def test_config_set_secret_prompts_masked_and_saves(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    prompts = []

    def fake_secret_prompt(prompt, secret=False):
        prompts.append((prompt, secret))
        return "replacement-secret"

    monkeypatch.setattr("zeus.cli.setup_commands._get_input", fake_secret_prompt)
    _handle_config_command("/config set OPENCODE_GO_API_KEY")

    assert len(prompts) == 1
    assert prompts[0][1] is True
    assert "OPENCODE_GO_API_KEY=replacement-secret" in (tmp_path / ".env").read_text()
    assert "replacement-secret" not in capsys.readouterr().out


def test_config_set_secret_rejects_inline_value(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))

    _handle_config_command("/config set OPENCODE_GO_API_KEY unsafe-inline-secret")

    assert not (tmp_path / ".env").exists()
    output = capsys.readouterr().out
    assert "mascarada" in output.lower()
    assert "unsafe-inline-secret" not in output
