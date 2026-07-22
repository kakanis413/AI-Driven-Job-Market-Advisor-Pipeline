"""Fast endpoint tests. The LLM is faked via `mock_agent_response`, so these never
call Vertex/Gemini — but validation, the response contract, status codes and error
handling are all exercised for real.

Rewritten against the current API: `/api/v1/ask-major` no longer exists (the advisor
package exposes a single `/api/v1/analyze-major`), and `growth`/`median_pay` are now
nullable, matching the real `data.json`.
"""


def test_root_healthcheck(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_healthz_reports_config(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # The single-root-agent refactor dropped `majors_loaded`/`multi_agent` from
    # healthz; these are the config keys it reports now.
    for key in ("model", "vertex", "project", "bigquery_dataset"):
        assert key in body


def test_analyze_major_happy_path(client, mock_agent_response):
    payload = {
        "major_name": "Computer Science",
        "exposure": 8.4,
        "median_pay": 125831,
        "growth": "faster",
        "occupations": [
            {"soc": "15-1252", "title": "Software Developers", "exposure": 9.0}
        ],
        "query_context": "Is this risky?",
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["generated_guidance"] == mock_agent_response
    # `degraded` went away with the multi-agent → single-agent fallback; the
    # single root agent reports its route instead.
    assert body["status"] == "active_reasoning"
    assert "route" in body


def test_analyze_major_missing_question_returns_422(client):
    """query_context is required — a major with no question is invalid."""
    resp = client.post("/api/v1/analyze-major", json={"major_name": "History"})
    assert resp.status_code == 422


def test_analyze_major_empty_occupations_list_is_accepted(client, mock_agent_response):
    """Real data has majors whose occupations aren't mapped yet."""
    payload = {
        "major_name": "Undeclared",
        "exposure": 5.0,
        "median_pay": 50000,
        "growth": "average",
        "occupations": [],
        "query_context": "What should I know?",
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 200


def test_analyze_major_null_growth_is_accepted(client, mock_agent_response):
    """The real data.json sends growth: null for most majors — the schema allows it.

    (This previously asserted 422; the schema was fixed so real records aren't rejected.)
    """
    payload = {
        "major_name": "Biology",
        "exposure": 5.8,
        "median_pay": 75024,
        "growth": None,
        "occupations": [],
        "query_context": "Career outlook?",
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 200


def test_analyze_major_null_pay_is_accepted(client, mock_agent_response):
    """Some majors in the real data have median_pay: null — must not 422."""
    payload = {
        "major_name": "Fine Arts",
        "exposure": 6.0,
        "median_pay": None,
        "growth": None,
        "occupations": [],
        "query_context": "Is this a risky major?",
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 200


def test_analyze_major_exposure_out_of_range_returns_422(client):
    """Exposure is a 0-10 score; anything outside that range is bad data."""
    payload = {
        "major_name": "Economics",
        "exposure": 42,
        "median_pay": 80000,
        "growth": "average",
        "occupations": [],
        "query_context": "Outlook?",
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 422


def test_analyze_major_malformed_json_returns_422(client):
    resp = client.post(
        "/api/v1/analyze-major",
        content="not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422
