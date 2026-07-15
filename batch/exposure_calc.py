"""
batch/exposure_calc.py

Offline batch job — computes AI exposure scores for every major and writes
them into the major_summary table (the cache).

Run manually from the project root:
    python -m batch.exposure_calc

NOT imported by main.py. NOT registered as a tool on root_agent.
Nothing in the live chat path can trigger this file.
"""

import asyncio
import json
import os
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from google.adk import Agent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.cloud import bigquery
from google.genai import types
from pydantic import BaseModel


class ExposureResult(BaseModel):
    status: Literal["success", "insufficient_data"]
    major_name: str
    exposure_score: float | None
    calculation_method: str
    occupations_used: list[str]
    occupations_excluded: list[str]
    top_contributors: list[str]
    explanation: str
    limitations: str


major_exposure_agent = Agent(
    name="major_exposure_analyst",
    model="gemini-3.5-flash",
    description=(
        "Analyzes occupation-level AI exposure data and produces "
        "an overall AI exposure assessment for a college major."
    ),
    instruction="""
You are a specialized AI exposure analyst.

You receive structured data for one college major. The data may contain:
- major_name
- related occupations
- SOC codes
- an AI exposure score from 0 to 10 for each occupation
- optional employment or relevance weights

Your task is to produce an overall major-level AI exposure assessment.

Rules:
1. Use only the supplied data.
2. Never invent occupations, exposure values, weights, employment data,
   pay, or growth values.
3. Apply the same calculation method consistently across majors.
4. If valid weights are supplied, use them when deriving the score.
5. If no weights are supplied, use the arithmetic mean of the valid
   occupation exposure scores.
6. Ignore occupations with missing exposure values and report which
   occupations were excluded.
7. Round the final score to one decimal place.
8. If no valid occupation exposure values are supplied, return
   status="insufficient_data".
9. AI exposure describes how transformable work may be through AI.
   It does not automatically mean that jobs will disappear.

When computing exposure_score, write and execute Python code to do the
arithmetic exactly (mean or weighted mean, rounding, exclusions) —
do not compute it by reasoning alone.

Return:
- status
- major_name
- exposure_score
- calculation_method
- occupations_used
- occupations_excluded
- top_contributors
- explanation
- limitations
""",
    code_executor=BuiltInCodeExecutor(),
    output_schema=ExposureResult,
    generate_content_config={"temperature": 0},
)

bq_client = bigquery.Client()

PROJECT_DATASET = os.environ["PROJECT_DATASET"]


def get_majors_to_process() -> list[str]:
    """Every major we need to (re)compute an exposure score for."""
    query = f"SELECT DISTINCT major_name FROM `{PROJECT_DATASET}.dim_major`"
    return [row.major_name for row in bq_client.query(query).result()]


def get_occupation_data(major_name: str) -> dict:
    """Raw occupation-level exposure data for one major."""
    query = f"""
        SELECT soc, title, exposure, employment_weight
        FROM `{PROJECT_DATASET}.fact_exposure`
        WHERE major_name = @major_name
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("major_name", "STRING", major_name)
        ]
    )
    rows = bq_client.query(query, job_config=job_config).result()
    return {
        "major_name": major_name,
        "occupations": [dict(r) for r in rows],
    }


def write_result(result: dict) -> None:
    """Writes the computed score into the summary table (the cache)."""
    query = f"""
        UPDATE `{PROJECT_DATASET}.major_summary`
        SET exposure_score = @score,
            calculation_method = @method
        WHERE major_name = @major_name
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("score", "FLOAT64", result["exposure_score"]),
            bigquery.ScalarQueryParameter("method", "STRING", result["calculation_method"]),
            bigquery.ScalarQueryParameter("major_name", "STRING", result["major_name"]),
        ]
    )
    bq_client.query(query, job_config=job_config).result()



async def run_batch():
    session_service = InMemorySessionService()
    runner = Runner(
        agent=major_exposure_agent,
        app_name="exposure_batch",
        session_service=session_service,
    )

    majors = get_majors_to_process()
    print(f"Processing {len(majors)} majors...")

    for major_name in majors:
        data = get_occupation_data(major_name)

        if not data["occupations"]:
            print(f"Skipped {major_name}: no occupation data found")
            continue

        session_id = f"batch_{uuid4().hex}"
        await session_service.create_session(
            app_name="exposure_batch",
            user_id="batch_job",
            session_id=session_id,
        )

        message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=json.dumps(data))],
        )
        response_text = None

        async for event in runner.run_async(
            user_id="batch_job",
            session_id=session_id,
            new_message=message,
        ):
            if event.is_final_response() and event.content:
                response_text = "".join(
                    part.text for part in event.content.parts if part.text
                )

        if not response_text:
            raise RuntimeError(
                f"Agent returned no final response for {major_name}"
            )

        result = ExposureResult.model_validate_json(response_text)

        if result.status == "success":
            write_result(result.model_dump())
            print(f"Wrote {major_name}: exposure_score={result.exposure_score}")
        else:
            print(f"Skipped {major_name}: insufficient_data")

    print("Batch run complete.")


if __name__ == "__main__":
    asyncio.run(run_batch())
