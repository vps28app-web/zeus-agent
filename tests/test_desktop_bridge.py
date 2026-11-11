"""Unit tests for zeus/cli/desktop_bridge.py and reasoning effort support."""

import io
import json
from unittest.mock import MagicMock, patch

from zeus.cli import desktop_bridge
from zeus.core.router import _stream_response, normalize_reasoning_effort


def test_normalize_reasoning_effort():
    assert normalize_reasoning_effort("Mínimo") == "minimal"
    assert normalize_reasoning_effort("minimo") == "minimal"
    assert normalize_reasoning_effort("Baixo") == "low"
    assert normalize_reasoning_effort("Medium") == "medium"
    assert normalize_reasoning_effort("Médio") == "medium"
    assert normalize_reasoning_effort("Alto") == "high"
    assert normalize_reasoning_effort("") is None
    assert normalize_reasoning_effort("unknown") is None


def test_stream_response_handles_non_streaming_dict():
    fake_gemini = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Resposta Gemini"}],
                }
            }
        ],
        "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 8},
    }
    chunks = []
    res = _stream_response(fake_gemini, "google_api", callback=chunks.append)
    assert chunks == ["Resposta Gemini"]
    assert res["choices"][0]["message"]["content"] == "Resposta Gemini"
    assert res["usage"] == {"prompt_tokens": 12, "completion_tokens": 8}


def test_turn_stream_filter_streams_markdown_and_suppresses_json():
    out = io.StringIO()
    emitter = desktop_bridge._JsonlEmitter(out)

    # Normal natural language streams live
    flt = desktop_bridge._TurnStreamFilter(emitter)
    flt.feed("Olá, ")
    flt.feed("mundo!")
    flt.flush_pending()
    lines = [json.loads(l) for l in out.getvalue().strip().splitlines()]
    assert any(l["type"] == "stream_chunk" for l in lines)
    assert "".join(l["content"] for l in lines if l["type"] == "stream_chunk") == "Olá, mundo!"

    # Structured JSON turn suppresses raw JSON tokens
    out2 = io.StringIO()
    emitter2 = desktop_bridge._JsonlEmitter(out2)
    flt2 = desktop_bridge._TurnStreamFilter(emitter2)
    flt2.feed('{"reasoning": "pensando", "response": "ok"}')
    flt2.flush_pending()
    lines2 = [json.loads(l) for l in out2.getvalue().strip().splitlines()]
    assert not any(l["type"] == "stream_chunk" for l in lines2)
    assert any(l["type"] == "status" for l in lines2)


def test_build_desktop_catalog_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    monkeypatch.setenv("ZEUS_PROVIDER", "openai")
    monkeypatch.setenv("ZEUS_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    cat = desktop_bridge.build_desktop_catalog()
    assert len(cat["providers"]) >= 10
    assert len(cat["commands"]) >= 10
    assert "tools" in cat
    assert cat["env"]["provider"] == "openai"
    assert cat["env"]["configured_keys"]["OPENAI_API_KEY"] is True
    assert "ecosystem" in cat


def test_run_desktop_bridge_slash_command_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    fake_stdout = io.StringIO()
    fake_stdin = io.StringIO("")

    with patch.object(desktop_bridge.sys, "stdout", fake_stdout), patch.object(
        desktop_bridge.sys, "stdin", fake_stdin
    ):
        rc = desktop_bridge.run_desktop_bridge(query="/help", session_id="test_desktop_slash")

    assert rc == 0
    events = [json.loads(line) for line in fake_stdout.getvalue().strip().splitlines()]
    types = [e["type"] for e in events]
    assert "final_response" in types
    assert "metrics" in types
    assert "done" in types
    assert events[-1]["success"] is True


def test_run_desktop_bridge_interactive_permission_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    fake_stdout = io.StringIO()
    # Provide an empty stdin initially; we'll replace readline dynamically when permission_request is emitted
    responses = iter(
        [
            json.dumps({"type": "permission_response", "decision": "once"}) + "\n",
        ]
    )

    class _FakeStdin:
        def readline(self):
            return next(responses, "")

    def fake_run_agent(query, **kwargs):
        # Simulate tool calling permission callback
        from zeus.security.permissions import get_global_permission_manager

        pm = get_global_permission_manager()
        approved = pm.confirm_callback("Executar comando git status?")
        assert approved is True
        cb = kwargs.get("stream_callback")
        if cb:
            cb("Executado com sucesso!")
        return "Executado com sucesso!"

    with patch.object(desktop_bridge.sys, "stdout", fake_stdout), patch.object(
        desktop_bridge.sys, "stdin", _FakeStdin()
    ), patch.object(desktop_bridge, "run_agent", side_effect=fake_run_agent):
        rc = desktop_bridge.run_desktop_bridge(query="rode git status", session_id="test_perm_rt")

    assert rc == 0
    events = [json.loads(line) for line in fake_stdout.getvalue().strip().splitlines()]
    types = [e["type"] for e in events]
    assert "permission_request" in types
    assert "stream_chunk" in types
    assert events[-1] == {"type": "done", "success": True}


def test_run_desktop_bridge_plan_command_cancel(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    fake_stdout = io.StringIO()
    fake_stdin = io.StringIO(json.dumps({"type": "permission_response", "decision": "deny"}) + "\n")

    fake_plan = {
        "goal": "Testar plano",
        "steps": [{"step": 1, "action": "Verificar arquivos", "tool": "list_directory"}],
    }

    with patch.object(desktop_bridge.sys, "stdout", fake_stdout), patch.object(
        desktop_bridge.sys, "stdin", fake_stdin
    ), patch.object(desktop_bridge, "generate_plan", return_value=fake_plan):
        rc = desktop_bridge.run_desktop_bridge(query="/plan testar", session_id="test_plan_cancel")

    assert rc == 0
    events = [json.loads(line) for line in fake_stdout.getvalue().strip().splitlines()]
    assert any(e["type"] == "permission_request" and e["kind"] == "plan_confirm" for e in events)
    final_msgs = [e["content"] for e in events if e["type"] == "final_response"]
    assert any("cancelado" in m.lower() for m in final_msgs)
