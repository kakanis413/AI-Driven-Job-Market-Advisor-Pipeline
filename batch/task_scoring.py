"""
batch/task_scoring.py

Offline batch job — scores every staged O*NET task in
`task_ai_scoring_requests_v1` for AI exposure (0-10) and writes results
into `task_ai_scores`.

This is the one step in the exposure pipeline that genuinely needs an LLM:
judging how much current generative AI can assist with a specific task,
against a written rubric. Every step *after* this (task -> O*NET occupation
-> SOC -> major) is pure arithmetic and should be done in SQL, not here.

Run manually from the project root:
    python -m batch.task_scoring --limit 10      # dry run, sanity-check output
    python -m batch.task_scoring                  # full run, all pending requests
    python -m batch.task_scoring --run-id task_ai_run_v1

NOT imported by main.py. NOT registered as a tool on root_agent.
Nothing in the live chat path can trigger this file.

Column names for task_ai_scoring_requests_v1 were verified against the
real schema on 2026-07-16: scoring_run_id, onet_soc_code, task_id,
occupation_title, task_text, scoring_prompt, model_version, prompt_version,
rubric_version, created_at. This table has NO status column -- "pending"
is defined entirely by scoring_run_id + not already present in
task_ai_scores (see get_pending_requests below). scoring_prompt is a
fully pre-built prompt per task, so no separate rubric fetch happens here.

task_ai_scores and ai_scoring_rubrics column names are still unverified --
check those before running:
    bq show --schema --format=prettyjson <project>:<dataset>.task_ai_scores
    bq show --schema --format=prettyjson <project>:<dataset>.ai_scoring_rubrics
"""

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from google.adk import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.cloud import bigquery
from google.genai import types
from pydantic import BaseModel

# Matches the GCP_PROJECT / BQ_DATASET convention used in data_pipeline.py
GCP_PROJECT = "sprinternship-sea-2026"
BQ_DATASET = "majors"
PROJECT_DATASET = f"{GCP_PROJECT}.{BQ_DATASET}"

# How many requests to score concurrently. Gemini calls are the bottleneck
# for 17,618 rows — raise this once you've confirmed quota/rate limits, but
# don't set it so high you get throttled mid-run.
CONCURRENCY = 8

# How many scored rows to buffer before flushing to BigQuery. Streaming
# inserts one row at a time for 17,618 rows is slow and racks up API calls;
# batching keeps this efficient.
WRITE_BATCH_SIZE = 200


class TaskScoreResult(BaseModel):
    status: Literal["scored", "insufficient_data"]
    task_id: str
    onet_soc_code: str
    exposure_score: float | None
    confidence: Literal["high", "medium", "low"] | None
    rationale: str
    limitations: str


task_scoring_agent = Agent(
    name="task_exposure_scorer",
    model="gemini-3.5-flash",
    description=(
        "Scores a single O*NET work task for how much current generative "
        "AI can assist with or accelerate it, against a fixed rubric."
    ),
    instruction="""
You are a specialized AI-exposure task scorer.

You receive ONE O*NET task to evaluate, via a fully-prepared scoring
prompt that includes the occupation, the task, and scoring instructions.

Rules:
1. Score ONLY the task you are given. Do not evaluate the whole occupation.
2. Use ONLY the rubric and task description provided. Never invent facts
   about the task, occupation, or industry that weren't supplied.
3. The score measures how much current generative AI can assist with or
   accelerate the TASK -- it is NOT a prediction of job loss or whether
   the occupation will disappear. Never frame it that way.
4. Score from 0 (no current generative AI assistance is plausible) to 10
   (generative AI can substantially perform this task today), following
   the rubric's band definitions exactly.
5. Set confidence to "low" if the task description is vague, ambiguous,
   or you are extrapolating beyond what the rubric directly covers.
6. If the task description or rubric is missing/unusable, return
   status="insufficient_data" with exposure_score=null and explain why
   in "limitations".
7. Round exposure_score to one decimal place.
8. Keep "rationale" to 1-2 sentences grounded only in the supplied task
   description and rubric -- no generic career advice, no speculation.

Return:
- status
- task_id
- onet_soc_code
- exposure_score
- confidence
- rationale
- limitations
""",
    output_schema=TaskScoreResult,
    generate_content_config={"temperature": 0},
)

bq_client = bigquery.Client()


def get_pending_requests(run_id: str, limit: int | None) -> list[dict]:
    """All not-yet-scored requests for a given scoring run."""
    query = f"""
        SELECT
            req.task_id,
            req.onet_soc_code,
            req.occupation_title,
            req.scoring_prompt,
            req.prompt_version,
            req.rubric_version,
            req.scoring_run_id
        FROM `{PROJECT_DATASET}.task_ai_scoring_requests_v1` AS req
        LEFT JOIN `{PROJECT_DATASET}.task_ai_scores` AS scored
            ON req.task_id = scored.task_id
            AND req.onet_soc_code = scored.onet_soc_code
            AND req.scoring_run_id = scored.scoring_run_id
        WHERE req.scoring_run_id = @run_id
            AND scored.task_id IS NULL
        {"LIMIT @limit" if limit else ""}
    """
    query_params = [bigquery.ScalarQueryParameter("run_id", "STRING", run_id)]
    if limit:
        query_params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))

    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    return [dict(row) for row in bq_client.query(query, job_config=job_config).result()]


def write_scores(results: list[dict]) -> None:
    """Bulk-writes a batch of scored rows into task_ai_scores."""
    if not results:
        return
    table_ref = f"{PROJECT_DATASET}.task_ai_scores"
    errors = bq_client.insert_rows_json(table_ref, results)
    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")


async def score_one(
    runner: Runner,
    session_service: InMemorySessionService,
    request: dict,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    async with semaphore:
        session_id = f"task_{uuid4().hex}"
        await session_service.create_session(
            app_name="task_scoring_batch",
            user_id="batch_job",
            session_id=session_id,
        )

        # scoring_prompt is pre-built per task (occupation + task + scoring
        # instructions) by whoever staged task_ai_scoring_requests_v1 -- we
        # add the task_id up front so it comes back to us in the response
        # for matching, since the stored prompt text doesn't include it.
        prompt = f"TASK ID: {request['task_id']}\n\n{request['scoring_prompt']}"
        content = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])

        response_text = None
        async for event in runner.run_async(
            user_id="batch_job", session_id=session_id, new_message=content
        ):
            if event.is_final_response() and event.content:
                response_text = "".join(
                    part.text for part in event.content.parts if part.text
                )

        if not response_text:
            print(f"WARNING: no response for task {request['task_id']}, skipping")
            return None

        result = TaskScoreResult.model_validate_json(response_text)
        now = datetime.now(timezone.utc).isoformat()

        if result.status == "insufficient_data":
            print(f"Marking {request['task_id']} insufficient_data (won't retry)")
            return {
                "scoring_run_id": request["scoring_run_id"],
                "onet_soc_code": result.onet_soc_code,
                "task_id": result.task_id,
                "ai_exposure_score": None,
                "confidence_level": None,
                "score_rationale": None,
                "scoring_status": "insufficient_data",
                "error_message": result.limitations,
                "model_name": "gemini-3.5-flash",
                "model_version": "gemini-3.5-flash",
                "prompt_version": request["prompt_version"],
                "rubric_version": request["rubric_version"],
                "scored_at": now,
                "created_at": now,
            }

        return {
            "scoring_run_id": request["scoring_run_id"],
            "onet_soc_code": result.onet_soc_code,
            "task_id": result.task_id,
            "ai_exposure_score": result.exposure_score,
            "confidence_level": result.confidence,
            "score_rationale": result.rationale,
            "scoring_status": "scored",
            "model_name": "gemini-3.5-flash",
            "model_version": "gemini-3.5-flash",
            "prompt_version": request["prompt_version"],
            "rubric_version": request["rubric_version"],
            "scored_at": now,
            "created_at": now,
        }


async def run_batch(run_id: str, limit: int | None):
    session_service = InMemorySessionService()
    runner = Runner(
        agent=task_scoring_agent,
        app_name="task_scoring_batch",
        session_service=session_service,
    )

    requests = get_pending_requests(run_id, limit)
    print(f"Scoring {len(requests)} pending tasks for run '{run_id}'...")

    if not requests:
        print("Nothing to score. Exiting.")
        return

    semaphore = asyncio.Semaphore(CONCURRENCY)
    buffer: list[dict] = []
    scored_count = 0
    insufficient_count = 0
    no_response_count = 0

    tasks = [
        score_one(runner, session_service, req, semaphore)
        for req in requests
    ]

    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result is None:
            no_response_count += 1
            continue

        buffer.append(result)
        if result["scoring_status"] == "insufficient_data":
            insufficient_count += 1
        else:
            scored_count += 1

        if len(buffer) >= WRITE_BATCH_SIZE:
            write_scores(buffer)
            print(f"  ...flushed {len(buffer)} rows ({scored_count} scored so far)")
            buffer = []

    write_scores(buffer)  # flush remainder

    print(
        f"Batch run complete. Scored: {scored_count}, "
        f"insufficient_data: {insufficient_count}, no response: {no_response_count}"
    )
    print(
        "NOTE: this run is NOT yet 'approved'. Review a sample of scores/"
        "rationales, then approve it with:\n"
        "  UPDATE `sprinternship-sea-2026.majors.ai_scoring_runs`\n"
        "  SET is_approved = TRUE, approved_at = CURRENT_TIMESTAMP(),\n"
        "      run_status = 'completed'\n"
        f"  WHERE scoring_run_id = '{run_id}';\n"
        "before rollup_pipeline.sql or the rationale agent uses it."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-id",
        default="task_ai_run_v1",
        help="scoring_run_id to process (default: task_ai_run_v1)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only score this many tasks -- use for a dry run before the full batch.",
    )
    args = parser.parse_args()
    asyncio.run(run_batch(args.run_id, args.limit))