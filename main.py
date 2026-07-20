"""FastAPI serving layer for the production multi-agent advisor.

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

from advisor import data_source, errors, news
from advisor.config import apply_vertex_env, settings
from advisor.runtime import get_runtime
from advisor.schemas import AdvisorRequest, AdvisorResponse, ErrorResponse, NewsFeed

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("advisor.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    apply_vertex_env()
    n = len(data_source.majors())
    get_runtime()  # build agents/runners once at startup
    log.info(
        "advisor ready | model=%s vertex=%s project=%s | majors=%d | "
        "multi_agent=%s news=%s bigquery=%s fallback=%s",
        settings.model, settings.use_vertex, settings.project, n,
        settings.enable_multi_agent, settings.enable_news,
        settings.enable_bigquery, settings.enable_fallback,
    )
    yield


app = FastAPI(title="AI-Driven Job Market Advisor", version="2.0.0", lifespan=lifespan)

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
    # 503 for transient/retryable, 502 for the rest — never a raw 500 stack trace.
    return _error_json(exc, 503 if exc.retryable else 502)


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": "2.0.0"}


@app.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "model": settings.model,
        "vertex": settings.use_vertex,
        "majors_loaded": len(data_source.majors()),
        "multi_agent": settings.enable_multi_agent,
        "news_enabled": settings.enable_news,
        "bigquery_enabled": settings.enable_bigquery,
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
        "response | path=%s agents=%s search=%s latency=%dms degraded=%s",
        resp.route.path, resp.route.agents_called, resp.route.used_search,
        resp.route.latency_ms, resp.degraded,
    )
    return resp


@app.get("/api/v1/news", response_model=NewsFeed)
async def news_feed(family: str) -> NewsFeed:
    """Per-family news digest, search-grounded and cached (NEWS_TAB.md §6)."""
    canon = news.canonical_family(family)
    if canon is None:
        return JSONResponse(  # type: ignore[return-value]
            status_code=422,
            content={"error": f"unknown family {family!r}", "families": news.FAMILIES},
        )
    feed = await news.get_news_runtime().get_feed(canon)
    log.info("news | family=%s items=%d fetched_at=%s", canon, len(feed.items), feed.fetched_at)
    return feed
