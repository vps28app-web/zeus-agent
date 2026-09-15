"""Additional tests for zeus/tools/config_tools.py to raise coverage."""

from unittest import mock

from zeus.tools.config_tools import fetch_models, list_available_models


class TestFetchModels:
    def test_fetch_models_openai_success(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [{"id": "gpt-4o"}, {"id": "gpt-3.5-turbo"}]
        }
        with mock.patch("requests.get", return_value=mock_response) as mock_get:
            result = fetch_models("openai")
        mock_get.assert_called_once_with(
            "https://api.openai.com/v1/models",
            headers={"Authorization": "Bearer sk-test"},
            timeout=30,
        )
        assert result["provider"] == "openai"
        assert result["models"] == ["gpt-3.5-turbo", "gpt-4o"]

    def test_fetch_models_openai_missing_key(self):
        result = fetch_models("openai")
        assert "error" in result
        assert "OPENAI_API_KEY" in result["error"]

    def test_fetch_models_openai_request_error(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with mock.patch("requests.get", side_effect=RuntimeError("timeout")):
            result = fetch_models("openai")
        assert "error" in result
        assert "timeout" in result["error"]

    def test_fetch_models_openrouter_success(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": [{"id": "openai/gpt-4o"}]}
        with mock.patch("requests.get", return_value=mock_response):
            result = fetch_models("openrouter")
        assert result["models"] == ["openai/gpt-4o"]

    def test_fetch_models_anthropic_uses_presets(self):
        result = fetch_models("anthropic")
        assert "error" not in result
        assert "claude-sonnet-4-20250514" in result["models"]

    def test_fetch_models_google_success(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-test")
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "models": [{"name": "models/gemini-3.6-flash"}, {"name": "models/gemini-pro"}]
        }
        with mock.patch("requests.get", return_value=mock_response) as mock_get:
            result = fetch_models("google")
        mock_get.assert_called_once_with(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": "gem-test"},
            timeout=30,
        )
        assert result["models"] == ["gemini-3.6-flash", "gemini-pro"]

    def test_fetch_models_google_missing_key(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        result = fetch_models("google")
        assert "error" in result
        assert "GOOGLE_API_KEY" in result["error"]

    def test_fetch_models_deepseek_success(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": [{"id": "deepseek-chat"}]}
        with mock.patch("requests.get", return_value=mock_response):
            result = fetch_models("deepseek")
        assert result["models"] == ["deepseek-chat"]

    def test_fetch_models_mistral_success(self, monkeypatch):
        monkeypatch.setenv("MISTRAL_API_KEY", "ms-test")
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": [{"id": "mistral-large-latest"}]}
        with mock.patch("requests.get", return_value=mock_response):
            result = fetch_models("mistral")
        assert result["models"] == ["mistral-large-latest"]

    def test_fetch_models_ollama_success(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"models": [{"name": "llama3.1"}, {"name": "qwen2.5-coder"}]}
        with mock.patch("requests.get", return_value=mock_response) as mock_get:
            result = fetch_models("ollama")
        mock_get.assert_called_once_with(
            "http://localhost:11434/api/tags",
            timeout=10,
        )
        assert result["models"] == ["llama3.1", "qwen2.5-coder"]

    def test_fetch_models_opencode_go_success(self, monkeypatch):
        monkeypatch.setenv("OPENCODE_GO_API_KEY", "oc-test")
        monkeypatch.setenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": [{"id": "kimi-k2.7-code"}, {"id": "qwen3.8-max"}]}
        with mock.patch("requests.get", return_value=mock_response) as mock_get:
            result = fetch_models("opencode_go")
        mock_get.assert_called_once_with(
            "https://opencode.ai/zen/go/v1/models",
            headers={"Authorization": "Bearer oc-test", "x-opencode-session": "zeus-session"},
            timeout=30,
        )
        assert result["models"] == ["kimi-k2.7-code", "qwen3.8-max"]

    def test_fetch_models_opencode_go_legacy_dict_response(self, monkeypatch):
        monkeypatch.setenv("OPENCODE_GO_API_KEY", "oc-test")
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"kimi-k2.7-code": {}, "qwen3.8-max": {}}
        with mock.patch("requests.get", return_value=mock_response):
            result = fetch_models("opencode_go")
        assert sorted(result["models"]) == ["kimi-k2.7-code", "qwen3.8-max"]

    def test_fetch_models_opencode_go_missing_key(self, monkeypatch):
        monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
        result = fetch_models("opencode_go")
        assert "error" in result
        assert "OPENCODE_GO_API_KEY" in result["error"]

    def test_fetch_models_unknown_provider(self):
        result = fetch_models("unknown-provider")
        assert "error" in result
        assert "não suportado" in result["error"]


class TestListAvailableModelsDynamic:
    def test_list_available_models_uses_fetch_models_when_successful(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": [{"id": "gpt-4o"}]}
        with mock.patch("requests.get", return_value=mock_response):
            result = list_available_models(provider="openai")
        assert result["provider"] == "openai"
        assert result["models"] == ["gpt-4o"]

    def test_list_available_models_fallback_on_fetch_error(self):
        with mock.patch("zeus.tools.config_tools.fetch_models", return_value={"error": "API down"}):
            result = list_available_models(provider="openai")
        assert result["provider"] == "openai"
        assert "gpt-4o" in result["models"]
        assert "warning" in result
        assert "API down" in result["warning"]

    def test_list_available_models_empty_dynamic_uses_fallback(self):
        with mock.patch("zeus.tools.config_tools.fetch_models", return_value={"provider": "openai", "models": []}):
            result = list_available_models(provider="openai")
        assert "gpt-4o" in result["models"]
