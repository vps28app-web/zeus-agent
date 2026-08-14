"""Structured tracing for agent execution."""

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TraceSpan:
    name: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "ok"  # ok | error
    attributes: Dict[str, Any] = field(default_factory=dict)
    children: List["TraceSpan"] = field(default_factory=list)

    def finish(self, status: str = "ok", attributes: Optional[Dict[str, Any]] = None) -> None:
        self.end_time = time.time()
        self.status = status
        if attributes:
            self.attributes.update(attributes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round((self.end_time - self.start_time) * 1000, 2) if self.end_time else None,
            "status": self.status,
            "attributes": self.attributes,
            "children": [c.to_dict() for c in self.children],
        }


class Tracer:
    """Simple tracer that records spans per session and persists as JSON."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.trace_id = uuid.uuid4().hex[:16]
        self.root = TraceSpan(name="session", attributes={"session_id": self.session_id, "trace_id": self.trace_id})
        self._current: List[TraceSpan] = [self.root]
        self._lock = threading.Lock()
        self._storage_path = self._storage_dir() / f"{self.session_id}.json"

    @staticmethod
    def _storage_dir() -> Path:
        home = os.getenv("ZEUS_HOME", os.path.expanduser("~/.zeus"))
        path = Path(home) / "traces"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> TraceSpan:
        span = TraceSpan(name=name, attributes=attributes or {})
        with self._lock:
            self._current[-1].children.append(span)
            self._current.append(span)
        return span

    def finish_span(self, status: str = "ok", attributes: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            if len(self._current) > 1:
                span = self._current.pop()
                span.finish(status=status, attributes=attributes)
        self._persist()

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        event = {
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        }
        with self._lock:
            self._current[-1].attributes.setdefault("events", []).append(event)
        self._persist()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "root": self.root.to_dict(),
        }

    def _persist(self) -> None:
        try:
            self._storage_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        except Exception:
            pass


_GLOBAL_TRACER: Optional[Tracer] = None
_GLOBAL_TRACER_LOCK = threading.Lock()


def get_tracer(session_id: Optional[str] = None) -> Tracer:
    global _GLOBAL_TRACER
    if session_id:
        return Tracer(session_id)
    with _GLOBAL_TRACER_LOCK:
        if _GLOBAL_TRACER is None:
            _GLOBAL_TRACER = Tracer("global")
        return _GLOBAL_TRACER
