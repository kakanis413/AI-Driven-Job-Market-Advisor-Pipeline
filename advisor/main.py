# advisor/main.py
#
# NOT a second app. The served application is the root-level `main.py` — both the
# Dockerfile (`uvicorn main:app`) and `npm run dev:backend` launch that module.
#
# This file used to define its own FastAPI instance with a divergent copy of
# /api/v1/analyze-major and the SSE endpoint. Nothing imported it, so edits made
# here (including a streaming endpoint) never reached a running server. It now
# re-exports the real app, so `uvicorn advisor.main:app` and `uvicorn main:app`
# are the same process and there is only one place to change a route.

from main import app  # noqa: F401

__all__ = ["app"]
