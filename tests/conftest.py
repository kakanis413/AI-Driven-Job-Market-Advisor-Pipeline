import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_agent_response():
    """Patches runner.run_async so tests don't call real Gemini."""
    async def fake_event_stream(*args, **kwargs):
        class FakeEvent:
            def is_final_response(self):
                return True
            content = type("Content", (), {
                "parts": [type("Part", (), {"text": "This is a mocked advisor response."})()]
            })()
        yield FakeEvent()

    with patch("main.runner.run_async", side_effect=fake_event_stream):
        yield