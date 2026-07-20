"""FastAPI serving layer for the simple 3-agent advisor.

Thin by design: validation + structured errors here, all orchestration in advisor.runtime.
Keeps the existing POST /api/v1/analyze-major contract so the current React app (which
already posts there via src/lib/advisor.ts) works with zero frontend changes.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from advisor import errors
from advisor.config import apply_vertex_env, settings
from advisor.runtime import get_runtime
from advisor.schemas import AdvisorRequest, AdvisorResponse, ErrorResponse

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("advisor.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    apply_vertex_env()
    get_runtime()  # build agents/runners once at startup
    log.info(
        "advisor ready | model=%s vertex=%s project=%s dataset=%s",
        settings.model, settings.use_vertex, settings.project, settings.bigquery_dataset,
    )
    yield


app = FastAPI(title="AI-Driven Job Market Advisor", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def _error_json(exc: errors.AdvisorError, status_code: int) -> JSONResponse:
    body = ErrorResponse(
        error=exc.detail, error_code=exc.error_code, retryable=exc.retryable
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


@app.exception_handler(errors.AdvisorError)
async def _advisor_error_handler(_: Request, exc: errors.AdvisorError) -> JSONResponse:
    # 503 for transient/retryable, 502 for the rest - never a raw 500 stack trace.
    return _error_json(exc, 503 if exc.retryable else 502)


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": "3.0.0"}


@app.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "model": settings.model,
        "vertex": settings.use_vertex,
        "project": settings.project,
        "bigquery_dataset": settings.bigquery_dataset,
    }


@app.post("/api/v1/analyze-major", response_model=AdvisorResponse)
async def analyze_major(req: AdvisorRequest) -> AdvisorResponse:
    """Primary endpoint the React AdvisorPanel calls. Returns grounded guidance."""
    log.info("request | major=%r q=%r", req.major_name, req.query_context[:80])
    try:
        resp = await get_runtime().advise(req)
    except errors.AdvisorError:
        raise
    except Exception as exc:  # noqa: BLE001 - classify anything unexpected
        raise errors.classify(exc) from exc
    log.info(
        "response | path=%s agents=%s search=%s latency=%dms",
        resp.route.path, resp.route.agents_called, resp.route.used_search,
        resp.route.latency_ms,
    )
    return resp
