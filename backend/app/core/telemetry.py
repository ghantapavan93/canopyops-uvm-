"""OpenTelemetry wiring — real distributed tracing.

A server span per request (with W3C ``traceparent`` context propagation, so a
trace continues across service boundaries) and automatic child spans for every
SQLAlchemy statement, so a request → DB call chain is visible as one trace. The
``trace_id`` is surfaced on every structured log line, the error envelope, and
the ``X-Trace-Id`` response header — the thread an SRE follows from a user report
to the exact query. Spans export to an OTLP collector when configured; console
export is opt-in for local inspection.
"""
from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from app.core.config import get_settings

logger = logging.getLogger("canopyops")
_provider: TracerProvider | None = None


def setup_tracing_core(engine, service_suffix: str = "") -> TracerProvider | None:
    """Install the tracer provider + exporters + SQLAlchemy instrumentation.
    Shared by the API and the worker (the worker has no FastAPI app)."""
    global _provider
    s = get_settings()
    if not s.otel_enabled or _provider is not None:
        return _provider

    resource = Resource.create({
        "service.name": s.otel_service_name + service_suffix,
        "service.version": "0.1.0",
        "deployment.environment": s.environment,
    })
    provider = TracerProvider(resource=resource)

    if s.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=s.otel_exporter_otlp_endpoint))
        )
    if s.otel_console_export:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _provider = provider
    # Child spans per SQL statement, parented to the active span.
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)
    logger.info("otel_initialized", extra={"service": s.otel_service_name + service_suffix})
    return provider


def setup_telemetry(app, engine) -> None:
    """Idempotently install tracing on the FastAPI app and the DB engine."""
    provider = setup_tracing_core(engine)
    if provider is None:
        return
    # Server spans + W3C propagation; probes are excluded to keep traces signal.
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, excluded_urls="health,ready,metrics"
    )


def current_trace_id() -> str | None:
    """The active span's 32-hex trace id, or None when tracing is off."""
    ctx = trace.get_current_span().get_span_context()
    if ctx and ctx.is_valid and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return None
