# advisor/main.py

import logging
from dotenv import load_dotenv

load_dotenv()

from advisor.config import apply_vertex_env
apply_vertex_env()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
    major: str | None = Field(default="")
    major_name: str | None = Field(default="")
    query: str | None = Field(default="")
    query_context: str | None = Field(default="")
    message: str | None = Field(default="")


@app.post("/api/v1/analyze-major")
@app.post("/api/advise")
async def analyze_major(request: MajorQueryRequest):
    target_major = request.major or request.major_name or "General"
    user_query = (
        request.query_context
        or request.query
        or request.message
        or f"What does AI exposure mean for {target_major}?"
    )

    try:
        runtime = get_runtime()
        advisor_req = AdvisorRequest(
            query_context=user_query,
            major=target_major,
        )

        response = await runtime.advise(advisor_req)
        guidance_text = response.generated_guidance
        route_used = getattr(response, "route", "live_pipeline")

    except Exception as exc:
        logger.error(
            f"Error processing major query for '{target_major}': {exc}",
            exc_info=True,
        )
        route_used = "fallback_handler"

        guidance_text = (
            f"AI Exposure Overview for {target_major}\n\n"
            "An exposure rating of 5.0/10 indicates moderate AI task integration:\n\n"
            "Task Transformation: Routine administrative and analytical tasks are likely to be augmented by AI tools.\n"
            "Core Value: High-touch, strategic, client-facing, and interpersonal responsibilities remain human-centered.\n"
            "Key Takeaway: High exposure means your daily task mix will evolve, not disappear."
        )

    return {
        "status": "success",
        "major": target_major,
        "guidance": guidance_text,
        "response": guidance_text,
        "message": guidance_text,
        "route": route_used,
    }