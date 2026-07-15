def test_root_healthcheck(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_analyze_major_happy_path(client, mock_agent_response):
    payload = {
        "major_name": "Computer Science", "exposure": 8.4, "median_pay": 125831,
        "growth": "faster", "occupations": [{"soc": "15-1252", "title": "Software Developers", "exposure": 9.0}],
        "query_context": "Is this risky?",
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 200
    assert resp.json()["generated_guidance"] == "This is a mocked advisor response."


def test_analyze_major_missing_field_returns_422(client):
    resp = client.post("/api/v1/analyze-major", json={"major_name": "History"})
    assert resp.status_code == 422


def test_analyze_major_empty_occupations_list_is_accepted(client, mock_agent_response):
    payload = {
        "major_name": "Undeclared", "exposure": 5.0, "median_pay": 50000,
        "growth": "average", "occupations": [], "query_context": "What should I know?",
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 200


def test_analyze_major_null_growth_currently_returns_422(client):
    """
    Documents the real-data mismatch: growth is required in the schema,
    but production data.json sends null. This SHOULD be a bug fix, not
    a permanent test — once agent_config.py allows growth: str | None,
    flip this assertion to expect 200.
    """
    payload = {
        "major_name": "Biology", "exposure": 5.8, "median_pay": 75024,
        "growth": None, "occupations": [], "query_context": "Career outlook?",
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


def test_ask_major_happy_path(client, mock_agent_response):
    payload = {
        "major_name": "Computer Science",
        "query_context": "What jobs can I get with this major?",
    }
    resp = client.post("/api/v1/ask-major", json=payload)
    assert resp.status_code == 200
    assert resp.json()["generated_guidance"] == "This is a mocked advisor response."


def test_ask_major_missing_field_returns_422(client):
    resp = client.post("/api/v1/ask-major", json={"major_name": "History"})
    assert resp.status_code == 422


def test_ask_major_empty_reply_returns_unavailable_status(client):
    """Covers the fallback branch in main.py when the agent returns nothing."""
    async def fake_empty_stream(*args, **kwargs):
        class FakeEvent:
            def is_final_response(self):
                return True
            content = None
        yield FakeEvent()

    from unittest.mock import patch
    with patch("main.runner.run_async", side_effect=fake_empty_stream):
        resp = client.post(
            "/api/v1/ask-major",
            json={"major_name": "Art History", "query_context": "Is this a good major?"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["error"] == "The AI model is not configured or returned no response."