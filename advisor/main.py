# advisor/main.py

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from advisor.runtime import get_runtime
from advisor.schemas import AdvisorRequest

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="AI Job Market Advisor API")

# Enable CORS for local dev / Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Flexible request model matching any key names sent by the frontend
class MajorQueryRequest(BaseModel):
    major: str | None = Field(default="")
    major_name: str | None = Field(default="")
    query: str | None = Field(default="")
    query_context: str | None = Field(default="")
    message: str | None = Field(default="")


@app.post("/api/v1/analyze-major")
@app.post("/api/advise")
async def analyze_major(request: MajorQueryRequest):
    # Fall back across any potential payload key sent by React
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
        # Print full python exception traceback in terminal for local debugging
        logger.error(
            f"Error processing major query for '{target_major}': {exc}",
            exc_info=True,
        )
        route_used = "fallback_handler"

        # Structured Markdown fallback response for seamless UI rendering
    guidance_text = (
        f"I couldn’t retrieve grounded guidance for {target_major} right now. "
        "I don’t want to replace verified data with a generic or estimated answer. "
        "Please try again later."
    )

    # Return pure string values across top keys so frontend receives clean text
    return {
        "status": "success",
        "major": target_major,
        "guidance": guidance_text,
        "response": guidance_text,
        "message": guidance_text,
        "route": route_used,
    }