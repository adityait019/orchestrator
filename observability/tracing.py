"""Small tracing helpers used at orchestrator boundaries."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace

tracer = trace.get_tracer("orchestrator")


def span_attributes(**values) -> dict:
    return {key: value for key, value in values.items() if value is not None}


@contextmanager
def trace_span(name: str, **attributes) -> Iterator:
    with tracer.start_as_current_span(name, attributes=span_attributes(**attributes)) as span:
        yield span
