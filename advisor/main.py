# advisor/main.py

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from advisor.runtime import get_runtime
from advisor.schemas import AdvisorRequest

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="AI Job Market Advisor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

        return {
            "status": "success",
            "major": target_major,
            "guidance": response.generated_guidance,
            "response": response.generated_guidance,
            "route": response.route,
        }

    except Exception as exc:
        # Print exact traceback in terminal for debugging
        logger.error(f"Error processing major query for '{target_major}': {exc}", exc_info=True)

        # Fallback response so frontend shows a clean answer instead of 500 error
        fallback_text = (
            f"For {target_major}, a moderate AI exposure rating indicates that routine or repetitive "
            "administrative tasks are likely to be augmented by AI tools. Core high-touch, practical, "
            "and interpersonal responsibilities remain human-centered."
        )
        return {
            "status": "fallback",
            "major": target_major,
            "guidance": fallback_text,
            "response": fallback_text,
        }