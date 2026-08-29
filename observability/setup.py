"""OpenTelemetry setup with Jaeger-compatible OTLP export.

Tracing is deliberately optional: if the exporter is unavailable or Jaeger is
offline, the application continues to run and logs the configuration issue.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)
_provider = None


def configure_observability() -> bool:
    global _provider
    if _provider is not None:
        return True
    if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
        logger.info("OpenTelemetry is disabled (OTEL_SDK_DISABLED=true)")
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        service_name = os.getenv("OTEL_SERVICE_NAME", "orchestrator")
        resource = Resource.create({
            "service.name": service_name,
            "service.version": os.getenv("APP_VERSION", "0.1.0"),
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        })
        provider = TracerProvider(resource=resource)
        exporter = None
        if os.getenv("OTEL_CONSOLE_EXPORTER", "false").lower() == "true":
            exporter = ConsoleSpanExporter()
        else:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
                exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
            except ImportError:
                logger.warning("OTLP exporter is not installed; using console exporter")
                exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _provider = provider
        logger.info("OpenTelemetry enabled: service=%s endpoint=%s", service_name,
                    os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "default"))
        return True
    except Exception:
        logger.exception("OpenTelemetry setup failed; continuing without tracing")
        return False


def shutdown_observability() -> None:
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:
            logger.exception("OpenTelemetry shutdown failed")


def instrument_fastapi_app(app) -> None:
    """Enable safe framework instrumentation when contrib packages exist."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        # A WebSocket remains open for the whole chat session. Tracing every
        # frame creates a multi-hour root span and noisy zero-duration children;
        # websocket_handler creates a span per user turn instead.
        excluded = os.getenv("OTEL_FASTAPI_EXCLUDED_URLS", r"/ws/.*")
        FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded)
    except ImportError:
        logger.info("FastAPI OpenTelemetry instrumentation is not installed")
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        logger.info("HTTPX OpenTelemetry instrumentation is not installed")
