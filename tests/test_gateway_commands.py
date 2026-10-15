"""Tests for gateway-side Zeus admin commands."""

from zeus.gateway.commands import handle_zeus_command


def test_non_zeus_message_is_not_intercepted():
    assert handle_zeus_command("hello") is None


def test_zeus_command_shows_help():
    response = handle_zeus_command("!zeus")
    assert "Zeus" in response
    assert "!zeus status" in response
    assert "!zeus setup" in response
    assert "!zeus provider" in response
    assert "!zeus model" in response


def test_setup_command_points_to_local_masked_setup():
    response = handle_zeus_command("!zeus setup")
    assert "zeus setup" in response
    assert "mascarad" in response.lower()
    assert "Instagram" in response


def test_status_shows_configuration_without_secrets(monkeypatch):
    monkeypatch.setenv("ZEUS_PROVIDER", "opencode_go")
    monkeypatch.setenv("ZEUS_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "never-print-this-secret")
    response = handle_zeus_command("!zeus status")
    assert isinstance(response, str)
    assert "opencode_go" in response
    assert "deepseek-v4-pro" in response
    assert "configuradas" in response.lower()
    assert "never-print-this-secret" not in response



def test_model_command_updates_saved_model(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.setenv("ZEUS_PROVIDER", "openai")
    monkeypatch.setenv("ZEUS_MODEL", "old-model")

    response = handle_zeus_command("!zeus model gpt-4o")

    assert "gpt-4o" in response
    assert "ZEUS_MODEL=gpt-4o" in (tmp_path / ".env").read_text()


def test_provider_command_requires_key_before_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ZEUS_PROVIDER", "opencode_go")
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "hidden-secret")

    response = handle_zeus_command("!zeus provider openai")

    assert "OPENAI_API_KEY" in response
    assert "zeus setup" in response
    assert not (tmp_path / ".env").exists()


def test_provider_command_switches_when_key_is_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "hidden-secret")

    response = handle_zeus_command("!zeus provider openrouter")

    assert "openrouter" in response
    assert "openrouter/auto" in response
    saved = (tmp_path / ".env").read_text()
    assert "ZEUS_PROVIDER=openrouter" in saved
    assert "ZEUS_MODEL=openrouter/auto" in saved
    assert "hidden-secret" not in response
