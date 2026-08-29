"""Optional OpenTelemetry observability for the orchestrator."""

from .setup import configure_observability, instrument_fastapi_app, shutdown_observability
from .tracing import tracer, span_attributes, trace_span

__all__ = [
    "configure_observability",
    "shutdown_observability",
    "instrument_fastapi_app",
    "tracer",
    "span_attributes",
    "trace_span",
]
