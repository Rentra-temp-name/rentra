"""Observability behavior tests using the local Postgres test database."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid

import psycopg
import pytest
from starlette.testclient import TestClient

from rentra_api.config import get_settings
from rentra_api.logging_setup import JsonFormatter, _before_send
from rentra_api.main import app


def test_logs_contain_no_phone_coords_ip(caplog):
    caplog.set_level(logging.INFO, logger="rentra_api")
    phone, coords, address = "+9779800001234", "27.7000,85.3000", "198.51.100.45"
    with TestClient(app) as client:
        response = client.get(
            f"/health?phone={phone}&coords={coords}",
            headers={"X-Forwarded-For": address},
        )
    assert response.status_code == 200
    formatted = [JsonFormatter().format(record) for record in caplog.records]
    output = "\n".join(formatted)
    assert all(secret not in output for secret in (phone, coords, address))


def test_ready_fails_when_db_down(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "DATABASE_URL",
        "postgresql://rentra_api:pass@127.0.0.1:54399/postgres?connect_timeout=1",
    )
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert "127.0.0.1" not in response.text
    assert "pass" not in response.text


def test_job_last_success_reported(test_database_url, monkeypatch):
    job = f"metrics_test_{uuid.uuid4().hex}"
    success_at = "2026-10-24 00:00:00+00"
    with psycopg.connect(test_database_url) as conn:
        conn.execute(
            "INSERT INTO app.job_runs (job, started_at, finished_at, error) VALUES (%s, now(), %s, NULL)",
            (job, success_at),
        )
        conn.execute(
            "INSERT INTO app.job_runs (job, started_at, finished_at, error) VALUES (%s, now(), now(), %s)",
            (job, "expected_test_error"),
        )
    monkeypatch.setattr(get_settings(), "METRICS_TOKEN", "test-metrics-token")
    try:
        with TestClient(app) as client:
            response = client.get("/metrics", headers={"Authorization": "Bearer test-metrics-token"})
        assert response.status_code == 200
        metric = re.search(rf'job_last_success_timestamp\{{job="{job}"\}} ([0-9.e+-]+)', response.text)
        assert metric is not None
        assert float(metric.group(1)) == pytest.approx(1792800000.0)
    finally:
        with psycopg.connect(test_database_url) as conn:
            conn.execute("DELETE FROM app.job_runs WHERE job=%s", (job,))


def test_api_works_through_transaction_pooler(monkeypatch):
    pooler_url = os.environ.get("TEST_POOLER_DATABASE_URL")
    if not pooler_url:
        pytest.skip("set TEST_POOLER_DATABASE_URL to verify transaction-pooler compatibility")
    monkeypatch.setattr(get_settings(), "DATABASE_URL", pooler_url)
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_header_not_trusted():
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "attacker-controlled"})
    request_id = response.headers["X-Request-ID"]
    assert request_id != "attacker-controlled"
    assert str(uuid.UUID(request_id)) == request_id


def test_metrics_requires_token(monkeypatch):
    monkeypatch.setattr(get_settings(), "METRICS_TOKEN", None)
    with TestClient(app) as client:
        missing = client.get("/metrics")
    assert missing.status_code == 404
    monkeypatch.setattr(get_settings(), "METRICS_TOKEN", "correct-secret")
    with TestClient(app) as client:
        rejected = client.get("/metrics", headers={"Authorization": "Bearer wrong-secret"})
    assert rejected.status_code == 401


def test_logger_drops_exception_text():
    try:
        raise RuntimeError("private phone +9779800001234")
    except RuntimeError:
        exc_info = __import__("sys").exc_info()
    record = logging.LogRecord("rentra_api", logging.ERROR, "", 1, "private phone +9779800001234", (), exc_info)
    record.event = "matches_query_failed_runtimeerror"
    rendered = JsonFormatter().format(record)
    assert "+9779800001234" not in rendered
    payload = json.loads(rendered)
    assert set(payload) == {
        "ts", "level", "service", "env", "version", "request_id", "route_template",
        "method", "status", "latency_ms", "user_id", "event",
    }


def test_sentry_scrubber_strips_request_and_messages():
    event = {
        "request": {"url": "https://example.test/?phone=secret"},
        "user": {"id": "private-user"}, "server_name": "private-host",
        "exception": {"values": [{"type": "RuntimeError", "value": "secret traceback message"}]},
    }
    scrubbed = _before_send(event, {})
    assert not {"request", "user", "server_name"}.intersection(scrubbed)
    assert scrubbed["exception"]["values"][0]["value"] == "RuntimeError"
