"""In-memory and persistent metrics collector."""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ToolMetric:
    calls: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    last_result: Optional[str] = None


@dataclass
class SessionMetrics:
    session_id: str
    started_at: float = field(default_factory=time.time)
    tool_calls: Dict[str, ToolMetric] = field(default_factory=dict)
    llm_calls: int = 0
    llm_total_latency_ms: float = 0.0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    errors: int = 0


class MetricsCollector:
    """Collects metrics for the current process and persists snapshots."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or "global"
        self._session = SessionMetrics(session_id=self.session_id)
        self._lock = threading.Lock()
        self._storage_path = self._storage_dir() / f"{self.session_id}.json"

    @staticmethod
    def _storage_dir() -> Path:
        home = os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus"))
        path = Path(home) / "metrics"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def record_tool_call(self, tool_name: str, latency_ms: float, error: bool = False, result_summary: Optional[str] = None) -> None:
        with self._lock:
            metric = self._session.tool_calls.setdefault(tool_name, ToolMetric())
            metric.calls += 1
            metric.total_latency_ms += latency_ms
            if error:
                metric.errors += 1
                self._session.errors += 1
            if result_summary:
                metric.last_result = result_summary[:500]
        self._persist()

    def record_llm_call(self, latency_ms: float, input_tokens: int = 0, output_tokens: int = 0, error: bool = False) -> None:
        with self._lock:
            self._session.llm_calls += 1
            self._session.llm_total_latency_ms += latency_ms
            self._session.llm_input_tokens += input_tokens
            self._session.llm_output_tokens += output_tokens
            if error:
                self._session.errors += 1
        self._persist()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "session_id": self._session.session_id,
                "started_at": self._session.started_at,
                "duration_sec": time.time() - self._session.started_at,
                "llm_calls": self._session.llm_calls,
                "llm_total_latency_ms": round(self._session.llm_total_latency_ms, 2),
                "llm_input_tokens": self._session.llm_input_tokens,
                "llm_output_tokens": self._session.llm_output_tokens,
                "errors": self._session.errors,
                "tool_calls": {
                    name: {
                        "calls": m.calls,
                        "errors": m.errors,
                        "total_latency_ms": round(m.total_latency_ms, 2),
                        "avg_latency_ms": round(m.total_latency_ms / m.calls, 2) if m.calls else 0.0,
                        "last_result": m.last_result,
                    }
                    for name, m in self._session.tool_calls.items()
                },
            }

    def _persist(self) -> None:
        try:
            self._storage_path.write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
        except Exception:
            pass


_GLOBAL: Optional[MetricsCollector] = None
_GLOBAL_LOCK = threading.Lock()
_METRICS_CACHE: Dict[str, MetricsCollector] = {}


def get_metrics(session_id: Optional[str] = None) -> MetricsCollector:
    global _GLOBAL
    if not session_id or session_id == "global":
        with _GLOBAL_LOCK:
            if _GLOBAL is None:
                _GLOBAL = MetricsCollector("global")
            return _GLOBAL

    with _GLOBAL_LOCK:
        if session_id not in _METRICS_CACHE:
            _METRICS_CACHE[session_id] = MetricsCollector(session_id)
        return _METRICS_CACHE[session_id]
