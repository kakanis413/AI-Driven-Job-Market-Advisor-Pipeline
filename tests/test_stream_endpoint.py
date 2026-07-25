"""The SSE path: /api/v1/analyze-major/stream.

These exist because the streaming endpoint's failure modes are silent. A broken
frame doesn't 500 — it delivers a truncated answer that looks plausible, which is
worse. So the assertions are about the wire format, not just the status code.
"""

from __future__ import annotations

import json


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Minimal SSE reader: returns [(event_name, payload), ...]."""
    out: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if name is not None:
            out.append((name, data if data is not None else {}))
    return out


PAYLOAD = {
    "major_name": "Computer science",
    "exposure": 8.4,
    "median_pay": 125831,
    "growth": "faster",
    "occupations": [],
    "query_context": "Is this risky?",
}


def test_stream_emits_tokens_then_done(client, mock_agent_stream):
    resp = client.post("/api/v1/analyze-major/stream", json=PAYLOAD)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["status", "token", "token", "token", "done"]


def test_status_events_carry_a_label(client, mock_agent_stream):
    """A turn that calls a slow tool emits no token for seconds. The status label is
    what stands between the student and an apparently frozen panel."""
    events = _parse_sse(client.post("/api/v1/analyze-major/stream", json=PAYLOAD).text)
    statuses = [payload for name, payload in events if name == "status"]
    assert statuses == [{"label": "Checking recent headlines…"}]


def test_stream_reassembles_to_the_exact_answer(client, mock_agent_stream):
    """Newlines and non-ASCII must survive the wire. A raw `data:` field would
    have terminated the event at the first \\n and dropped the last chunk."""
    resp = client.post("/api/v1/analyze-major/stream", json=PAYLOAD)
    text = "".join(
        payload["text"] for name, payload in _parse_sse(resp.text) if name == "token"
    )
    assert text == "".join(mock_agent_stream)
    assert "\n\n" in text
    assert "don’t" in text


def test_stream_reports_failure_as_a_terminal_error_event(client, monkeypatch):
    """The HTTP status is already 200 by the time the agent fails, so the error
    has to ride the stream — otherwise the client hangs on a silent truncation."""
    from advisor import runtime as runtime_mod

    async def _boom(self, req):
        raise RuntimeError("simulated upstream failure")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(runtime_mod.AdvisorRuntime, "advise_stream", _boom)

    resp = client.post("/api/v1/analyze-major/stream", json=PAYLOAD)
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    assert events[-1][0] == "error"
    error = events[-1][1]
    assert error["error_code"]
    assert "retryable" in error
    assert ("done", {}) not in events


def test_stream_validates_the_same_contract_as_the_blocking_route(client):
    resp = client.post("/api/v1/analyze-major/stream", json={"major_name": "History"})
    assert resp.status_code == 422
