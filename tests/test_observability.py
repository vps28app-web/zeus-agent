"""Unit tests for zeus/observability modules."""

import json
import os
import time
from unittest.mock import patch

from zeus.observability.cost import estimate_cost, get_price
from zeus.observability.metrics import MetricsCollector, get_metrics
from zeus.observability.reporter import format_summary, report_summary
from zeus.observability.tracing import Tracer, get_tracer


def test_get_price_known_model():
    price = get_price("openai", "gpt-4o")
    assert price["input"] == 2.5
    assert price["output"] == 10.0


def test_get_price_with_provider_prefix():
    price = get_price("openai", "openai/gpt-4o-mini")
    assert price["input"] == 0.15


def test_get_price_unknown_model_returns_zero():
    price = get_price("unknown", "unknown/model")
    assert price == {"input": 0.0, "output": 0.0}


def test_estimate_cost_calculation():
    cost = estimate_cost("openai", "gpt-4o", 1_000_000, 1_000_000)
    assert cost["input_cost_usd"] == 2.5
    assert cost["output_cost_usd"] == 10.0
    assert cost["total_cost_usd"] == 12.5
    assert cost["currency"] == "USD"


def test_cost_overrides_from_env():
    overrides = json.dumps({"custom/model": {"input": 1.0, "output": 2.0}})
    with patch.dict(os.environ, {"ZEUS_COST_OVERRIDES": overrides}, clear=False):
        price = get_price("custom", "custom/model")
    assert price["input"] == 1.0
    assert price["output"] == 2.0


def test_metrics_records_tool_and_llm_calls():
    metrics = MetricsCollector("test-session")
    metrics.record_tool_call("read_file", 12.5, error=False, result_summary="ok")
    metrics.record_tool_call("read_file", 7.5, error=True, result_summary="fail")
    metrics.record_llm_call(100.0, 10, 5)

    snapshot = metrics.snapshot()
    assert snapshot["session_id"] == "test-session"
    assert snapshot["llm_calls"] == 1
    assert snapshot["llm_input_tokens"] == 10
    assert snapshot["llm_output_tokens"] == 5
    assert snapshot["errors"] == 1

    read_metric = snapshot["tool_calls"]["read_file"]
    assert read_metric["calls"] == 2
    assert read_metric["errors"] == 1
    assert read_metric["avg_latency_ms"] == 10.0


def test_metrics_get_metrics_caches_same_session():
    m1 = get_metrics("shared-session")
    m2 = get_metrics("shared-session")
    assert m1 is m2


def test_metrics_persists_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    metrics = MetricsCollector("persisted-session")
    metrics.record_llm_call(50.0, 3, 2)

    storage_path = tmp_path / "metrics" / "persisted-session.json"
    assert storage_path.exists()
    data = json.loads(storage_path.read_text())
    assert data["llm_calls"] == 1
    assert data["llm_input_tokens"] == 3


def test_tracer_start_and_finish_span():
    tracer = Tracer("trace-test")
    span = tracer.start_span("operation", {"key": "value"})
    time.sleep(0.01)
    span.finish(status="ok", attributes={"result": "success"})

    data = tracer.to_dict()
    assert data["session_id"] == "trace-test"
    assert data["root"]["children"][0]["name"] == "operation"
    assert data["root"]["children"][0]["status"] == "ok"
    assert data["root"]["children"][0]["attributes"]["result"] == "success"
    assert data["root"]["children"][0]["duration_ms"] is not None


def test_tracer_finish_span_without_start_does_not_crash():
    tracer = Tracer("trace-test")
    # Should be safe even if no span was started.
    tracer.finish_span(status="ok")
    data = tracer.to_dict()
    assert data["root"]["status"] == "ok"


def test_tracer_persists_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEUS_HOME", str(tmp_path))
    tracer = Tracer("persisted-trace")
    tracer.add_event("test_event", {"foo": "bar"})

    storage_path = tmp_path / "traces" / "persisted-trace.json"
    assert storage_path.exists()
    data = json.loads(storage_path.read_text())
    assert data["root"]["attributes"]["events"][0]["name"] == "test_event"


def test_get_tracer_without_session_returns_global():
    t1 = get_tracer()
    t2 = get_tracer()
    assert t1 is t2


def test_report_summary_combines_metrics_and_cost():
    metrics = MetricsCollector("report-test")
    metrics.record_llm_call(100.0, 1_000_000, 1_000_000)
    summary = report_summary(metrics, provider="openai", model="gpt-4o")
    assert summary["session_id"] == "report-test"
    assert summary["llm_calls"] == 1
    assert summary["estimated_cost"]["total_cost_usd"] == 12.5
    assert "read_file" not in summary["tool_calls"]


def test_format_summary_human_readable():
    metrics = MetricsCollector("fmt-test")
    metrics.record_llm_call(100.0, 100, 50)
    metrics.record_tool_call("read_file", 10.0)
    summary = report_summary(metrics, provider="openai", model="gpt-4o-mini")
    text = format_summary(summary)
    assert "Session: fmt-test" in text
    assert "LLM calls: 1" in text
    assert "Tokens: 100 in / 50 out" in text
    assert "read_file: 1 calls" in text
