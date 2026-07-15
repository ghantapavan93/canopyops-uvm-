"""OpenTelemetry tracing: every response carries a trace id, W3C trace-context
propagates from an inbound traceparent, the error envelope includes the trace
id, and a request emits a real server span + child DB spans."""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from tests.conftest import auth


def test_response_carries_a_trace_id(client):
    r = client.get("/api/overview")
    tid = r.headers.get("X-Trace-Id")
    assert tid and len(tid) == 32 and int(tid, 16) != 0


def test_w3c_traceparent_propagation(client):
    # a known upstream trace id — the server span must CONTINUE this trace
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    traceparent = f"00-{trace_id}-b7ad6b7169203331-01"
    r = client.get("/api/overview", headers={"traceparent": traceparent})
    assert r.headers.get("X-Trace-Id") == trace_id


def test_error_envelope_includes_trace_id(client):
    # a missing required field raises a Pydantic RequestValidationError, which
    # flows through our structured envelope handler
    r = client.post("/api/audit/plans/whatever", json={},   # 'outcome' is required
                    headers=auth(client, "reviewer@synthetic.test"))
    assert r.status_code == 422
    assert r.json().get("code") == "validation_error"
    assert r.json().get("trace_id"), "the structured error envelope carries the trace id"


def test_request_emits_server_and_db_spans(client):
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    client.get("/api/overview")
    spans = exporter.get_finished_spans()
    kinds = {s.kind for s in spans}
    assert SpanKind.SERVER in kinds, "a server span per request"
    assert SpanKind.CLIENT in kinds, "child spans for the SQLAlchemy DB calls"
    # server and DB spans share one trace (the request → DB chain is one trace)
    server = next(s for s in spans if s.kind == SpanKind.SERVER)
    db = next(s for s in spans if s.kind == SpanKind.CLIENT)
    assert server.context.trace_id == db.context.trace_id
