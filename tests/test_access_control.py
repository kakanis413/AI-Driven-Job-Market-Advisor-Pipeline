"""Blocker 1 and 3 from PRODUCTION_READINESS.md.

Blocker 1: the BigQuery path is the slowest in the system and used to emit no
status at all, leaving the panel frozen for ~13s.
Blocker 3: LLM-written SQL had no byte ceiling, behind an endpoint with no auth
and no rate limit.

Auth and rate limiting are OFF unless configured, so the default suite also pins
that the unconfigured path stays exactly as it was.
"""

from __future__ import annotations

import dataclasses

import pytest

PAYLOAD = {"major_name": "Computer Science", "query_context": "Is this risky?"}


# --- Blocker 1: the slow path must announce itself -----------------------------


def test_bigquery_tools_have_status_labels():
    """Every tool the BigQuery toolset exposes needs a label, or the slowest path in
    the system runs silent."""
    from advisor.runtime import _TOOL_STATUS

    for name in ("execute_sql", "get_table_info", "list_table_ids", "get_dataset_info"):
        assert name in _TOOL_STATUS, f"{name} would run with no status shown"


def test_sql_and_schema_read_are_distinguishable():
    """Schema discovery and the query itself are separate waits; collapsing them into
    one label would make a 13s turn look stalled halfway through."""
    from advisor.runtime import _TOOL_STATUS

    assert _TOOL_STATUS["get_table_info"] != _TOOL_STATUS["execute_sql"]


# --- Blocker 3a: SQL cannot bill without a ceiling -----------------------------


def test_bigquery_config_caps_bytes_billed():
    from advisor.config import settings

    assert settings.bigquery_max_bytes_billed > 0
    # The whole `majors` dataset measures ~128MB. A ceiling below that would break
    # legitimate queries; one wildly above it stops being a ceiling.
    assert 128 * 1024**2 <= settings.bigquery_max_bytes_billed <= 2 * 1024**3


def test_toolset_is_read_only_and_capped():
    """WriteMode caps what SQL may do; maximum_bytes_billed caps what it may spend.
    Both are needed — `max_query_result_rows` limits only what comes back."""
    from google.adk.integrations.bigquery.config import WriteMode

    from advisor.config import settings
    from advisor.tools import get_bigquery_toolset

    cfg = get_bigquery_toolset()._tool_settings
    assert cfg.write_mode == WriteMode.BLOCKED
    assert cfg.maximum_bytes_billed == settings.bigquery_max_bytes_billed


# --- Blocker 3b: auth and rate limiting ----------------------------------------


@pytest.fixture
def guarded_client(monkeypatch):
    """A client whose app requires an API key and allows 3 requests/min."""
    import main
    from advisor.config import settings as real

    monkeypatch.setattr(
        main, "settings",
        dataclasses.replace(real, api_key="test-key-123", rate_limit_per_min=3),
    )
    main._RATE_BUCKETS.clear()
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        yield c
    main._RATE_BUCKETS.clear()


def test_unconfigured_endpoint_is_unchanged(client, mock_agent_response):
    """Default config: no key required. Existing deployments must not break."""
    assert client.post("/api/v1/analyze-major", json=PAYLOAD).status_code == 200


def test_missing_key_is_rejected(guarded_client):
    resp = guarded_client.post("/api/v1/analyze-major", json=PAYLOAD)
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "unauthorized"


def test_wrong_key_is_rejected(guarded_client):
    resp = guarded_client.post(
        "/api/v1/analyze-major", json=PAYLOAD, headers={"X-API-Key": "not-the-key"}
    )
    assert resp.status_code == 401


def test_correct_key_passes(guarded_client, mock_agent_response):
    resp = guarded_client.post(
        "/api/v1/analyze-major", json=PAYLOAD, headers={"X-API-Key": "test-key-123"}
    )
    assert resp.status_code == 200


def test_health_probe_stays_open(guarded_client):
    """Cloud Run's probe cannot present a key. Locking it out downs the service."""
    assert guarded_client.get("/healthz").status_code == 200
    assert guarded_client.get("/").status_code == 200


def test_rejection_still_carries_cors_headers(guarded_client):
    """CORS must wrap the guard. Without that ordering a browser reports an opaque
    CORS failure instead of the 401 that actually happened."""
    resp = guarded_client.post(
        "/api/v1/analyze-major",
        json=PAYLOAD,
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 401
    assert "access-control-allow-origin" in {k.lower() for k in resp.headers}


def test_rate_limit_trips_and_reports_retry_after(guarded_client, mock_agent_response):
    hdr = {"X-API-Key": "test-key-123"}
    for _ in range(3):
        assert guarded_client.post("/api/v1/analyze-major", json=PAYLOAD, headers=hdr).status_code == 200

    resp = guarded_client.post("/api/v1/analyze-major", json=PAYLOAD, headers=hdr)
    assert resp.status_code == 429
    assert resp.json()["error_code"] == "rate_limited"
    assert int(resp.headers["Retry-After"]) > 0
