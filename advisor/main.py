# advisor/main.py

import logging
from dotenv import load_dotenv

load_dotenv()

from advisor.config import apply_vertex_env
apply_vertex_env()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from advisor.runtime import get_runtime
from advisor.schemas import AdvisorRequest

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="AI Job Market Advisor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow Vite frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MajorQueryRequest(BaseModel):
    """The full body the frontend POSTs. Every field the React app sends is
    accepted here and forwarded to the advisor — including the national data
    block and the optional university-personalization layer. `major`/`query`/
    `message` are kept only as legacy aliases for older callers."""

    model_config = ConfigDict(extra="ignore")

    # Identity + question (with legacy aliases).
    major_name: str | None = None
    major: str | None = None
    cip: str | None = None
    query_context: str | None = None
    query: str | None = None
    message: str | None = None

    # National data block (so the advisor is grounded, not stuck in general mode).
    exposure: float | None = None
    median_pay: int | None = None
    growth: str | None = None
    occupations: list[dict] = Field(default_factory=list)

    # University-personalization layer — forwarded verbatim so schemas.py can
    # decide whether to run the domain-scoped program search.
    university: str | None = None
    university_domain: str | None = None
    intended_major: str | None = None


def _build_advisor_request(request: MajorQueryRequest) -> AdvisorRequest:
    """Helper to convert API incoming Pydantic payload into AdvisorRequest domain schema."""
    target_major = request.major_name or request.major or None
    user_query = (
        request.query_context
        or request.query
        or request.message
        or (
            f"What does AI exposure mean for {target_major}?"
            if target_major
            else "Which majors are most exposed to AI?"
        )
    )

    return AdvisorRequest(
        query_context=user_query,
        major_name=target_major,
        cip=request.cip,
        exposure=request.exposure,
        median_pay=request.median_pay,
        growth=request.growth,
        occupations=request.occupations,
        university=request.university,
        university_domain=request.university_domain,
        intended_major=request.intended_major,
    )


@app.post("/api/v1/analyze-major")
@app.post("/api/advise")
async def analyze_major(request: MajorQueryRequest):
    target_major = request.major_name or request.major or None
    try:
        runtime = get_runtime()
        advisor_req = _build_advisor_request(request)

        response = await runtime.advise(advisor_req)
        guidance_text = response.generated_guidance
        route_used = getattr(response, "route", "live_pipeline")

    except Exception as exc:
        display_major = target_major or "your major"
        logger.error(
            f"Error processing major query for '{display_major}': {exc}",
            exc_info=True,
        )
        route_used = "fallback_handler"
        guidance_text = (
            f"I couldn’t retrieve grounded guidance for {display_major} right now. "
            "I don’t want to replace verified data with a generic or estimated answer. "
            "Please try again later."
        )

    return {
        "status": "success",
        "major": target_major,
        "generated_guidance": guidance_text,
        "guidance": guidance_text,
        "response": guidance_text,
        "message": guidance_text,
        "route": route_used,
    }


@app.post("/api/v1/analyze-major-stream")
async def analyze_major_stream(request: MajorQueryRequest):
    runtime = get_runtime()
    advisor_req = _build_advisor_request(request)

    async def event_generator():
        try:
            async for chunk in runtime.advise_stream(advisor_req):
                # Clean up newlines inside SSE data payloads
                sanitized_chunk = chunk.replace("\n", "\\n")
                yield f"data: {sanitized_chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error(f"Error in streaming endpoint: {exc}", exc_info=True)
            yield "data: [ERROR]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disables proxy buffering (e.g. Nginx) for immediate delivery
        },
    )