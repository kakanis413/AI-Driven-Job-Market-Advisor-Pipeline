"""
batch/rationale_agent.py

Offline batch job — writes a short, grounded explanation for each major's
AI exposure score, using only the rolled-up scores and task-level
rationales that already exist. Writes results into `major_ai_rationales`.

This agent NEVER computes or adjusts a score. It only explains one that
the SQL rollup (rollup_pipeline.sql) already produced. Run this only
after major_ai_scores has been (re)built from an approved scoring run.

Run manually from the project root:
    python -m batch.rationale_agent --limit 10     # dry run, sanity-check
    python -m batch.rationale_agent                 # full run

NOT imported by main.py. NOT registered as a tool on root_agent.
Nothing in the live chat path can trigger this file.

IMPORTANT: column/table names are inferred from the BigQuery handoff doc
and rollup_pipeline.sql's output shape, not a verified schema dump.
Verify against the real tables before running, same as task_scoring.py.
"""

import argparse
import asyncio
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
CONCURRENCY = 8
WRITE_BATCH_SIZE = 100

MIN_WORDS = 40
MAX_WORDS = 80


class MajorRationaleResult(BaseModel):
    status: Literal["written", "insufficient_data"]
    cip4_code: str
    rationale: str
    limitations: str


rationale_agent = Agent(
    name="major_rationale_writer",
    model="gemini-3.5-flash",
    description=(
        "Writes a short, grounded explanation of why a college major has "
        "the AI exposure score it does, using only supplied evidence."
    ),
    instruction="""
You are a specialized explanation writer for an AI-exposure dashboard
aimed at college students.

You receive, for ONE major: its name, its final exposure score (0-10,
already computed -- you never calculate or adjust it), a list of its
top related occupations with their own exposure scores, and a handful
of task-level rationales that were used as supporting evidence.

Rules:
1. Use ONLY the supplied facts. Never invent occupations, tasks, scores,
   wages, or growth figures that were not given to you.
2. Never recompute, question, or adjust the exposure score you were
   given -- your only job is to explain it in plain language.
3. Reference at least one specific occupation from the supplied list by
   name. Do not give generic career advice.
4. Exposure measures how much current generative AI can assist with or
   accelerate the WORK in this major's related occupations. It does NOT
   mean these jobs will disappear. Make this distinction clear, briefly,
   without being repetitive about it.
5. Write 2-3 sentences, 40-80 words total. Conversational but precise --
   this is read by a student deciding on a major, not a technical report.
6. If the supplied evidence is too thin to say anything specific and
   grounded (e.g. no related occupations were supplied), return
   status="insufficient_data" and explain why in "limitations".

Return:
- status
- cip4_code
- rationale
- limitations
""",
    output_schema=MajorRationaleResult,
    generate_content_config={"temperature": 0.2},
)

bq_client = bigquery.Client()


def get_majors_needing_rationale(limit: int | None) -> list[dict]:
    """Majors with a published score that don't have a rationale yet."""
    query = f"""
        SELECT
            m.cip4_code,
            m.major_exposure_score,
            d.major_title
        FROM `{PROJECT_DATASET}.major_ai_scores` AS m
        JOIN `{PROJECT_DATASET}.dim_major_cip4_clean` AS d
            ON m.cip4_code = d.cip4_code
        LEFT JOIN `{PROJECT_DATASET}.major_ai_rationales` AS r
            ON m.cip4_code = r.cip4_code
        WHERE r.cip4_code IS NULL
        {"LIMIT @limit" if limit else ""}
    """
    query_params = []
    if limit:
        query_params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    return [dict(row) for row in bq_client.query(query, job_config=job_config).result()]


def get_supporting_evidence(cip4_code: str) -> dict:
    """Top related occupations + a few task-level rationales, for grounding."""
    occ_query = f"""
        SELECT
            oo.title AS occupation_title,
            s.occupation_exposure_score
        FROM `{PROJECT_DATASET}.cip4_to_soc_crosswalk_clean` AS x
        JOIN `{PROJECT_DATASET}.soc_onet_mapping_clean` AS m
            ON x.soc_code = m.soc_code
        JOIN `{PROJECT_DATASET}.onet_occupation_ai_scores` AS s
            ON m.onet_soc_code = s.onet_soc_code
        JOIN `{PROJECT_DATASET}.onet_occupations_clean` AS oo
            ON s.onet_soc_code = oo.onet_soc_code
        WHERE x.cip4_code = @cip4_code
        ORDER BY s.occupation_exposure_score DESC
        LIMIT 5
    """
    task_query = f"""
        SELECT s.score_rationale
        FROM `{PROJECT_DATASET}.cip4_to_soc_crosswalk_clean` AS x
        JOIN `{PROJECT_DATASET}.soc_onet_mapping_clean` AS m
            ON x.soc_code = m.soc_code
        JOIN `{PROJECT_DATASET}.task_ai_scores` AS s
            ON m.onet_soc_code = s.onet_soc_code
        WHERE x.cip4_code = @cip4_code
            AND s.scoring_status = 'scored'
        ORDER BY s.ai_exposure_score DESC
        LIMIT 3
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("cip4_code", "STRING", cip4_code)]
    )
    occupations = [dict(r) for r in bq_client.query(occ_query, job_config=job_config).result()]
    task_rationales = [
        r.score_rationale for r in bq_client.query(task_query, job_config=job_config).result()
    ]
    return {"occupations": occupations, "task_rationales": task_rationales}


def write_rationales(results: list[dict]) -> None:
    if not results:
        return
    table_ref = f"{PROJECT_DATASET}.major_ai_rationales"
    errors = bq_client.insert_rows_json(table_ref, results)
    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")


async def write_one(
    runner: Runner,
    session_service: InMemorySessionService,
    major: dict,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    async with semaphore:
        evidence = get_supporting_evidence(major["cip4_code"])

        if not evidence["occupations"]:
            print(f"Skipped {major['cip4_code']}: no related occupations found")
            return None

        session_id = f"rationale_{uuid4().hex}"
        await session_service.create_session(
            app_name="rationale_batch", user_id="batch_job", session_id=session_id
        )

        occ_lines = "\n".join(
            f"- {o['occupation_title']}: exposure {o['occupation_exposure_score']}"
            for o in evidence["occupations"]
        )
        task_lines = "\n".join(f"- {t}" for t in evidence["task_rationales"])

        prompt = (
            f"MAJOR: {major['major_title']} (CIP4 {major['cip4_code']})\n"
            f"MAJOR EXPOSURE SCORE: {major['major_exposure_score']}\n\n"
            f"TOP RELATED OCCUPATIONS:\n{occ_lines}\n\n"
            f"SUPPORTING TASK-LEVEL EVIDENCE:\n{task_lines}"
        )
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
            print(f"WARNING: no response for {major['cip4_code']}, skipping")
            return None

        result = MajorRationaleResult.model_validate_json(response_text)

        if result.status == "insufficient_data":
            print(f"Skipped {major['cip4_code']}: insufficient_data")
            return None

        word_count = len(result.rationale.split())
        if not (MIN_WORDS <= word_count <= MAX_WORDS):
            print(
                f"NOTE: {major['cip4_code']} rationale is {word_count} words "
                f"(target {MIN_WORDS}-{MAX_WORDS}) -- writing anyway, review later"
            )

        return {
            "cip4_code": result.cip4_code,
            "rationale": result.rationale,
            "model": "gemini-3.5-flash",
            "prompt_version": "rationale_prompt_v1",
        }


async def run_batch(limit: int | None):
    session_service = InMemorySessionService()
    runner = Runner(
        agent=rationale_agent, app_name="rationale_batch", session_service=session_service
    )

    majors = get_majors_needing_rationale(limit)
    print(f"Writing rationales for {len(majors)} majors...")

    if not majors:
        print("Nothing to write. Exiting.")
        return

    semaphore = asyncio.Semaphore(CONCURRENCY)
    tasks = [write_one(runner, session_service, m, semaphore) for m in majors]

    buffer: list[dict] = []
    written, skipped = 0, 0

    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result is None:
            skipped += 1
            continue
        buffer.append(result)
        written += 1
        if len(buffer) >= WRITE_BATCH_SIZE:
            write_rationales(buffer)
            print(f"  ...flushed {len(buffer)} rows ({written} written so far)")
            buffer = []

    write_rationales(buffer)
    print(f"Batch run complete. Written: {written}, skipped: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run_batch(args.limit))