"""Trace identifiers shared by one user turn and its child invocations."""
from __future__ import annotations

from dataclasses import dataclass, field
import uuid


@dataclass
class TraceContext:
    trace_id: str = field(default_factory=lambda: f"trace-{uuid.uuid4().hex}")
    turn_id: str = field(default_factory=lambda: f"turn-{uuid.uuid4().hex}")

    def child_span(self, parent_span_id: str | None = None) -> dict[str, str | None]:
        return {
            "trace_id": self.trace_id,
            "turn_id": self.turn_id,
            "span_id": f"span-{uuid.uuid4().hex}",
            "parent_span_id": parent_span_id,
        }
