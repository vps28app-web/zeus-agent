"""Tests for metrics collection and caching."""

from zeus.observability.metrics import get_metrics


def test_metrics_caching_by_session_id():
    session_id = "test_session_tokens_123"
    m1 = get_metrics(session_id)
    m2 = get_metrics(session_id)
    assert m1 is m2

    m1.record_llm_call(latency_ms=150.0, input_tokens=500, output_tokens=120)
    snap = m2.snapshot()
    assert snap["llm_input_tokens"] == 500
    assert snap["llm_output_tokens"] == 120

    m2.record_llm_call(latency_ms=100.0, input_tokens=300, output_tokens=80)
    snap2 = m1.snapshot()
    assert snap2["llm_input_tokens"] == 800
    assert snap2["llm_output_tokens"] == 200
