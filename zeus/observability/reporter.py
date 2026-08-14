"""Reporter that combines metrics, cost, and traces into a summary."""

import json
from typing import Any, Dict, Optional

from zeus.observability.metrics import MetricsCollector
from zeus.observability.cost import estimate_cost


def report_summary(metrics: MetricsCollector, provider: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """Build a summary report from metrics."""
    snapshot = metrics.snapshot()
    cost = estimate_cost(
        provider or "unknown",
        model or "unknown",
        snapshot.get("llm_input_tokens", 0),
        snapshot.get("llm_output_tokens", 0),
    )
    return {
        "session_id": snapshot["session_id"],
        "duration_sec": snapshot["duration_sec"],
        "llm_calls": snapshot["llm_calls"],
        "llm_input_tokens": snapshot["llm_input_tokens"],
        "llm_output_tokens": snapshot["llm_output_tokens"],
        "llm_total_latency_ms": snapshot["llm_total_latency_ms"],
        "errors": snapshot["errors"],
        "tool_calls": snapshot["tool_calls"],
        "estimated_cost": cost,
    }


def format_summary(summary: Dict[str, Any]) -> str:
    """Human-readable summary."""
    lines = [
        f"Session: {summary['session_id']}",
        f"Duration: {summary['duration_sec']:.1f}s",
        f"LLM calls: {summary['llm_calls']}",
        f"Tokens: {summary['llm_input_tokens']} in / {summary['llm_output_tokens']} out",
        f"Estimated cost: ${summary['estimated_cost']['total_cost_usd']:.6f} USD",
        f"Errors: {summary['errors']}",
        "Tool calls:",
    ]
    for name, data in summary["tool_calls"].items():
        lines.append(f"  - {name}: {data['calls']} calls, {data['errors']} errors, avg {data['avg_latency_ms']}ms")
    return "\n".join(lines)
