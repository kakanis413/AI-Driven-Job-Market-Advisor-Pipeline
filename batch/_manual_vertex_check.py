"""
batch/_manual_vertex_check.py

ONE-OFF, MANUAL script -- not part of the permanent pipeline. Delete once
the real dry run (python -m batch.task_scoring --limit 10) works.

Purpose: verify Vertex AI access works AT ALL, completely isolated from
BigQuery -- if this fails, the problem is IAM/region/env config, not
anything in the scoring pipeline itself.

Run:
    python -m batch._manual_vertex_check
"""

import asyncio
import os
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from google.adk import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

print("Checking required env vars...")
for var in ["GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"]:
    val = os.environ.get(var)
    print(f"  {var} = {val!r}" + ("  <-- MISSING" if not val else ""))

test_agent = Agent(
    name="vertex_connectivity_check",
    model="gemini-3.5-flash",
    description="Minimal agent used only to verify Vertex AI connectivity.",
    instruction="Reply with exactly: CONNECTION OK",
)


async def main():
    session_service = InMemorySessionService()
    runner = Runner(
        agent=test_agent, app_name="vertex_check", session_service=session_service
    )
    session_id = f"check_{uuid4().hex}"
    await session_service.create_session(
        app_name="vertex_check", user_id="test_user", session_id=session_id
    )

    content = types.Content(role="user", parts=[types.Part.from_text(text="ping")])

    print("\nSending a test prompt to Gemini via Vertex AI...")
    response_text = None
    async for event in runner.run_async(
        user_id="test_user", session_id=session_id, new_message=content
    ):
        if event.is_final_response() and event.content:
            response_text = "".join(part.text for part in event.content.parts if part.text)

    if response_text:
        print(f"\nSUCCESS -- got a response back:\n{response_text}")
    else:
        print("\nFAIL -- no response came back at all (check the traceback above, if any).")


if __name__ == "__main__":
    asyncio.run(main())