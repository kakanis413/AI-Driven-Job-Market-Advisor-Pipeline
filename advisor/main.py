# advisor/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from advisor.runtime import get_runtime
from advisor.schemas import AdvisorRequest

app = FastAPI(title="AI Job Market Advisor API")

# Allow CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Flexible request model matching whatever keys frontend sends
class MajorQueryRequest(BaseModel):
    major: str | None = Field(default="")
    major_name: str | None = Field(default="")
    query: str | None = Field(default="")
    query_context: str | None = Field(default="")
    message: str | None = Field(default="")


@app.post("/api/v1/analyze-major")
@app.post("/api/advise")  # Added fallback route in case frontend calls /api/advise
async def analyze_major(request: MajorQueryRequest):
    try:
        runtime = get_runtime()

        # Extract major & query regardless of key name used by frontend
        target_major = request.major or request.major_name or "General"
        user_query = (
            request.query_context
            or request.query
            or request.message
            or f"What does an AI exposure mean for {target_major}?"
        )

        advisor_req = AdvisorRequest(
            query_context=user_query,
            major=target_major,
        )

        response = await runtime.advise(advisor_req)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))