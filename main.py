"""FastAPI serving layer for the simple 3-agent advisor.

Thin by design: validation + structured errors here, all orchestration in advisor.runtime.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv

load_dotenv()

from advisor.config import apply_vertex_env, settings

apply_vertex_env()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from advisor import errors, news
from advisor.runtime import get_runtime
from advisor.schemas import AdvisorRequest, AdvisorResponse, ErrorResponse, NewsFeed

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("advisor.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_runtime()
    asyncio.create_task(news.prewarm_all_families())
    asyncio.create_task(news.background_refresh_loop())
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


def _build_fallback_response(req: AdvisorRequest) -> AdvisorResponse:
    """Generate a helpful fallback response using available data when the agent fails."""
    from advisor.schemas import RouteInfo

    major = req.major_name or "your chosen field"

    # Build response based on available data
    parts = []

    if req.exposure is not None:
        exposure_level = "high" if req.exposure >= 7 else "moderate" if req.exposure >= 4 else "lower"
        parts.append(
            f"{major} has a {exposure_level} AI exposure score of {req.exposure}/10. "
            "This measures how much the daily tasks in this field will be augmented by AI tools — "
            "it does not mean jobs will disappear, but rather that the work will evolve."
        )

    if req.median_pay:
        parts.append(f"The median early-career pay is ${req.median_pay:,}.")

    if req.growth:
        growth_text = {
            "faster": "faster than average",
            "average": "at an average pace",
            "slower": "slower than average",
            "declining": "declining"
        }.get(req.growth, req.growth)
        parts.append(f"Employment in this field is projected to grow {growth_text}.")

    if req.occupations:
        top_occs = [o.title for o in req.occupations[:3]]
        parts.append(f"Common career paths include: {', '.join(top_occs)}.")

    # Add helpful closing
    parts.append(
        "\n\nFor more detailed guidance, please try your question again in a moment. "
        "If you're asking about specific companies hiring or current trends, "
        "the live search may need more time to gather results."
    )

    guidance = " ".join(parts) if parts else (
        "I wasn't able to complete your request at this time. Please try again with a simpler "
        "question, or select a specific major from the map to see its AI exposure data."
    )

    return AdvisorResponse(
        status="active_reasoning",
        generated_guidance=guidance,
        route=RouteInfo(path="fallback", agents_called=[], used_search=False, latency_ms=0),
    )


@app.post("/api/v1/analyze-major", response_model=AdvisorResponse)
async def analyze_major(req: AdvisorRequest) -> AdvisorResponse:
    log.info("request | major=%r q=%r", req.major_name, req.query_context[:80])
    try:
        resp = await get_runtime().advise(req)
    except errors.AdvisorError:
        raise
    except Exception as exc:
        raise errors.classify(exc) from exc
    log.info(
        "response | path=%s agents=%s search=%s latency=%dms",
        resp.route.path, resp.route.agents_called, resp.route.used_search,
        resp.route.latency_ms,
    )
    return resp


def _sse(event: str, payload: dict) -> str:
    """Frame one SSE message.

    The payload is JSON-encoded rather than written raw, because advisor answers
    are markdown: a bare newline inside a `data:` field terminates the event and
    truncates the reply. JSON escapes them, so the client gets the text back byte
    for byte after one `JSON.parse`.
    """
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/api/v1/analyze-major/stream")
async def analyze_major_stream(req: AdvisorRequest) -> StreamingResponse:
    """Same contract as /api/v1/analyze-major, delivered as it is written.

    Total compute is unchanged; what changes is when the student sees the first
    words — from ~9s to ~1s. Errors arrive as a terminal `error` event rather than
    an HTTP status, because the status line is already sent by then.
    """
    log.info("stream request | major=%r q=%r", req.major_name, req.query_context[:80])

    async def events() -> AsyncGenerator[str, None]:
        try:
            # The same timeout that guards the blocking path; without it a stalled
            # upstream holds the connection open indefinitely.
            stream = get_runtime().advise_stream(req)
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        stream.__anext__(), timeout=settings.request_timeout_s
                    )
                except StopAsyncIteration:
                    break
                kind, payload = chunk
                yield _sse(
                    kind, {"text": payload} if kind == "token" else {"label": payload}
                )
            yield _sse("done", {})
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: B014 - timeout is explicit
            classified = (
                exc if isinstance(exc, errors.AdvisorError) else errors.classify(exc)
            )
            log.error("stream failed | code=%s", classified.error_code, exc_info=True)
            yield _sse(
                "error",
                {
                    "error": classified.detail,
                    "error_code": classified.error_code,
                    "retryable": classified.retryable,
                },
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # stop nginx/Cloud Run buffering the stream
        },
    )


@app.get("/api/v1/news", response_model=NewsFeed)
async def news_feed(family: str) -> NewsFeed:
    canon = news.canonical_family(family)
    if canon is None:
        return JSONResponse(
            status_code=422,
            content={"error": f"unknown family {family!r}", "families": news.FAMILIES},
        )
    feed = await news.get_news_runtime().get_feed(canon)
    log.info("news | family=%s items=%d fetched_at=%s", canon, len(feed.items), feed.fetched_at)
    return feed