from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent_config import root_agent, MajorAnalysisSchema

app = FastAPI(title="AI-Driven Job Market Advisor Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before the real demo
    allow_methods=["*"],
    allow_headers=["*"],
)

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="college_advisor",
    session_service=session_service,
)


@app.get("/")
async def root():
    return {"status": "ok", "service": "college_advisor"}


@app.post("/api/v1/analyze-major")
async def analyze_major(data: MajorAnalysisSchema):
    session_id = f"session-{data.major_name.replace(' ', '_').lower()}"

    await session_service.create_session(
        app_name="college_advisor",
        user_id="demo",
        session_id=session_id,
    )

    prompt = f"MAJOR DATA: {data.model_dump_json()}\n\nSTUDENT QUESTION: {data.query_context}"
    content = types.Content(role="user", parts=[types.Part(text=prompt)])

    reply = ""
    async for event in runner.run_async(
        user_id="demo", session_id=session_id, new_message=content
    ):
        if event.is_final_response():
            reply = event.content.parts[0].text

    return {
        "agent_node": "college_advisor",
        "status": "active_reasoning",
        "generated_guidance": reply,
    }