"""Observability surfaces — readiness probe + Prometheus exposition."""
from __future__ import annotations


def test_ready_reports_db_and_postgis(client):
    res = client.get("/api/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["postgis"]                       # PostGIS version string present


def test_prometheus_exposition_format(client):
    client.get("/api/health")                    # generate at least one sample
    res = client.get("/api/metrics/prometheus")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    body = res.text
    # counter + its TYPE line, and a percentile gauge with a quantile label
    assert "# TYPE canopyops_requests_total counter" in body
    assert "canopyops_requests_total " in body
    assert 'canopyops_request_latency_ms{quantile="0.5"}' in body
    assert "canopyops_endpoint_requests_total{endpoint=" in body


def test_metrics_json_snapshot(client):
    client.get("/api/overview")
    snap = client.get("/api/metrics").json()
    assert snap["total_requests"] >= 1
    assert "latency_ms" in snap and "p95" in snap["latency_ms"]
