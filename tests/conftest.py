"""Shared fixtures. Fast tests mock the runtime; the live test hits Vertex for real."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURE_DATA = Path(__file__).parent / "fixtures" / "majors.json"

# Point the in-memory lookup at the rich fixture BEFORE any advisor module imports,
# so config.settings.data_file resolves to it.
os.environ["ADVISOR_DATA_FILE"] = str(FIXTURE_DATA)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "sprinternship-sea-2026")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: hits Vertex/Gemini for real (needs ADC)")


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless RUN_LIVE=1, so the default suite is fast and offline."""
    if os.getenv("RUN_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live test; set RUN_LIVE=1 (and ADC) to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def client():
    """FastAPI test client. Used as a context manager so lifespan (data load) runs."""
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def mock_agent_response(monkeypatch):
    """Fakes ONLY the LLM boundary so the fast suite never calls Vertex/Gemini.

    Everything around it is still exercised for real: request validation, the response
    contract, error handling and status codes. Nothing here fakes product data.
    """
    from advisor import runtime as runtime_mod
    from advisor.schemas import AdvisorResponse

    text = "This is a mocked advisor response."

    async def _fake_advise(self, req):
        return AdvisorResponse(generated_guidance=text)

    monkeypatch.setattr(runtime_mod.AdvisorRuntime, "advise", _fake_advise)
    return text


@pytest.fixture
def rich_payload() -> dict:
    return {
        "major_name": "Computer science",
        "exposure": 9.0,
        "median_pay": 99000,
        "growth": "faster",
        "occupations": [
            {"soc": "15-1252", "title": "Software developers", "exposure": 9.0},
            {"soc": "15-1211", "title": "Computer systems analysts", "exposure": 8.5},
        ],
        "query_context": "Should I be worried about AI taking these jobs?",
    }
