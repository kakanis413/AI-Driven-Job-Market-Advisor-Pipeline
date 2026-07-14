from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_analyze_major():
    payload = {
        "major_name": "Computer Science",
        "exposure": 9.0,
        "median_pay": 99000,
        "growth": "faster",
        "occupations": [
            {"soc": "15-1252", "title": "Software developers", "exposure": 9.0}
        ],
        "query_context": "Is this major too risky because of AI?",
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_node"] == "college_advisor"
    assert len(body["generated_guidance"]) > 0


def test_analyze_major_different_query_gives_different_response():
    base_payload = {
        "major_name": "History",
        "exposure": 3.0,
        "median_pay": 55000,
        "growth": "slower",
        "occupations": [
            {"soc": "25-4013", "title": "Museum technicians", "exposure": 2.0}
        ],
    }
    resp1 = client.post("/api/v1/analyze-major", json={**base_payload, "query_context": "Should I switch majors?"})
    resp2 = client.post("/api/v1/analyze-major", json={**base_payload, "query_context": "What jobs can I get?"})
    assert resp1.json()["generated_guidance"] != resp2.json()["generated_guidance"]