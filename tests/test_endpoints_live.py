import pytest

pytestmark = pytest.mark.live  # tag these so they can be skipped by default


def test_real_agent_gives_grounded_response(client):
    payload = {
        "major_name": "Computer Science", "exposure": 9.0, "median_pay": 99000,
        "growth": "faster", "occupations": [{"soc": "15-1252", "title": "Software developers", "exposure": 9}],
        "query_context": "Should I be worried about AI taking these jobs?",
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 200
    guidance = resp.json()["generated_guidance"]
    assert len(guidance) > 50
    # Loose content check — can't assert exact text from an LLM
    assert "job loss" in guidance.lower() or "transform" in guidance.lower()


def test_real_agent_ask_major_uses_tool_and_responds(client):
    """
    Hits /api/v1/ask-major for real, which exercises the ADK tool-calling
    path (get_major_data) rather than the direct-data path that
    /api/v1/analyze-major uses. This is the only test that actually
    confirms the agent's tool is wired up correctly end-to-end.
    """
    payload = {
        "major_name": "Computer Science",
        "query_context": "What kind of jobs does this major lead to?",
    }
    resp = client.post("/api/v1/ask-major", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # Real tool-backed calls should succeed and not hit the "unavailable" fallback
    assert body["status"] == "active_reasoning"
    assert len(body["generated_guidance"]) > 20