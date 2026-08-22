"""Unit tests for zeus/tools/config_tools.py."""


from zeus.tools.config_tools import (
    _upsert_env,
    get_zeus_config,
    list_available_models,
    update_zeus_config,
)


def test_get_zeus_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.setenv("ZEUS_PROVIDER", "openai")
    monkeypatch.setenv("ZEUS_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    result = get_zeus_config()
    assert result["zeus_provider"] == "openai"
    assert result["zeus_model"] == "gpt-4o"
    assert "OPENAI_API_KEY" in result["api_keys_status"]
    assert "-key" in result["api_keys_status"]["OPENAI_API_KEY"]


def test_update_zeus_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    result = update_zeus_config("GEMINI_API_KEY", "abc123")
    assert result["status"] == "success"
    assert result["key"] == "GEMINI_API_KEY"
    assert "123" in result["new_value_masked"]

    env_path = tmp_path / ".env"
    content = env_path.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=abc123" in content


def test_update_zeus_config_syncs_google_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    update_zeus_config("GEMINI_API_KEY", "shared-secret")
    import os
    assert os.getenv("GOOGLE_API_KEY") == "shared-secret"


def test_update_zeus_config_empty_key():
    result = update_zeus_config("   ", "value")
    assert "error" in result


def test_upsert_env_updates_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    env_path = tmp_path / ".env"
    env_path.write_text("OLD=value1\n", encoding="utf-8")

    _upsert_env("OLD", "value2")
    content = env_path.read_text(encoding="utf-8")
    assert "OLD=value2" in content
    assert "OLD=value1" not in content


def test_upsert_env_uncomments_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    env_path = tmp_path / ".env"
    env_path.write_text("#KEY=value1\n", encoding="utf-8")

    _upsert_env("KEY", "value2")
    content = env_path.read_text(encoding="utf-8")
    assert "KEY=value2" in content


def test_list_available_models_all():
    result = list_available_models()
    assert "providers" in result
    assert "presets" in result


def test_list_available_models_provider():
    result = list_available_models(provider="openrouter")
    assert result["provider"] == "openrouter"
    assert len(result["models"]) > 0


def test_list_available_models_unknown_provider():
    result = list_available_models(provider="invalid")
    assert "error" in result
