"""
batch/occupation_scoring.py  — Layer A of the Karpathy-style exposure rebuild.

Scores each OCCUPATION (SOC) directly for AI exposure 0-10 with one Gemini call
against the anchored Karpathy rubric (batch/karpathy_rubric.py), grounded in the
occupation's title + O*NET description + representative tasks (+ pay/growth when
available). Writes to a NEW, versioned table `occupation_ai_scores_v2`.

WHY THIS EXISTS (see EXPOSURE_REBUILD_PLAN.md §4 Layer A):
The old path scores 17k tasks and averages task -> occupation -> SOC -> major.
Three nested means regress everything toward ~5, so no major can ever reach the
real 8-10 band. Karpathy's method scores the *displayed unit as a whole* against
an anchored rubric, and the full spread survives. This file does that at the
occupation grain: it fixes the occupation numbers (roofer ~1, software dev ~9,
data-entry ~10) and becomes the grounding Layer B (major_scoring.py) reads.

This does NOT touch or delete the task-level path. It is a parallel, versioned
run written to its own table. Nothing here is imported by main.py or registered
as a tool on root_agent.

Run from the project root:
    python -m batch.occupation_scoring --limit 10     # dry run, sanity check
    python -m batch.occupation_scoring                 # full run (~868 SOCs)
    python -m batch.occupation_scoring --approve       # mark the run approved
"""

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

from google.cloud import bigquery
from pydantic import BaseModel

from batch._gemini_scoring import MODEL, score_json
from batch.karpathy_rubric import ANCHOR_BANDS, NO_JOB_LOSS_CLAUSE

GCP_PROJECT = "sprinternship-sea-2026"
BQ_DATASET = "majors"
PROJECT_DATASET = f"{GCP_PROJECT}.{BQ_DATASET}"

OUTPUT_TABLE = f"{PROJECT_DATASET}.occupation_ai_scores_v2"
RUNS_TABLE = f"{PROJECT_DATASET}.ai_scoring_runs"

# Versioning — a brand new run id so this never collides with the approved
# task-level run (`task_ai_run_v1`) that the old rollup still reads.
SCORING_RUN_ID = "occupation_karpathy_v2"
PROMPT_VERSION = "karpathy_occ_v1"
RUBRIC_VERSION = "karpathy_anchored_v1"

CONCURRENCY = 16
WRITE_BATCH_SIZE = 100
MAX_TASKS_PER_OCC = 8

bq_client = bigquery.Client(project=GCP_PROJECT)

# Explicit output schema — never let autodetect guess types on a fresh table.
OUTPUT_SCHEMA = [
    bigquery.SchemaField("soc_code", "STRING"),
    bigquery.SchemaField("occupation_title", "STRING"),
    bigquery.SchemaField("occupation_exposure_score", "FLOAT"),
    bigquery.SchemaField("confidence_level", "STRING"),
    bigquery.SchemaField("score_rationale", "STRING"),
    bigquery.SchemaField("scoring_status", "STRING"),
    bigquery.SchemaField("scoring_run_id", "STRING"),
    bigquery.SchemaField("prompt_version", "STRING"),
    bigquery.SchemaField("rubric_version", "STRING"),
    bigquery.SchemaField("model_version", "STRING"),
    bigquery.SchemaField("scored_at", "TIMESTAMP"),
]


class OccupationScore(BaseModel):
    status: Literal["scored", "insufficient_data"]
    exposure: float | None
    confidence: Literal["high", "medium", "low"] | None
    rationale: str


def ensure_output_table() -> None:
    """Create occupation_ai_scores_v2 if it doesn't exist (idempotent)."""
    table = bigquery.Table(OUTPUT_TABLE, schema=OUTPUT_SCHEMA)
    bq_client.create_table(table, exists_ok=True)


def get_pending_occupations(limit: int | None) -> list[dict]:
    """
    Every crosswalk SOC not already scored for this run, with its grounding:
    O*NET base description, pay, growth, and up to N representative tasks.

    Resumable by construction (LEFT JOIN anti-pattern against the output table),
    mirroring task_scoring.py — a crashed run picks up where it left off.
    """
    query = f"""
    WITH crosswalk_socs AS (
      SELECT DISTINCT soc_code
      FROM `{PROJECT_DATASET}.cip4_to_soc_crosswalk_clean`
      WHERE soc_code IS NOT NULL
    ),
    base_occ AS (
      -- one description row per SOC (the O*NET base occupation)
      SELECT soc_code, ANY_VALUE(occupation_title) AS occupation_title,
             ANY_VALUE(occupation_description) AS occupation_description
      FROM `{PROJECT_DATASET}.onet_occupations_clean`
      WHERE is_base_occupation AND occupation_description IS NOT NULL
      GROUP BY soc_code
    ),
    top_tasks AS (
      SELECT soc_code,
             STRING_AGG(task_text, ' | ' ORDER BY rn) AS tasks
      FROM (
        SELECT soc_code, task_text,
               ROW_NUMBER() OVER (PARTITION BY soc_code ORDER BY
                 incumbents_responding DESC NULLS LAST, task_id) AS rn
        FROM `{PROJECT_DATASET}.onet_tasks_clean`
        WHERE task_text IS NOT NULL
      )
      WHERE rn <= {MAX_TASKS_PER_OCC}
      GROUP BY soc_code
    )
    SELECT
      cs.soc_code,
      COALESCE(bo.occupation_title, occ.occupation_title, oews.occupation_title) AS occupation_title,
      bo.occupation_description,
      tt.tasks,
      occ.employment_2024,
      occ.outlook_pct,
      occ.outlook_description,
      occ.entry_education,
      oews.median_wage_annual
    FROM crosswalk_socs cs
    LEFT JOIN base_occ bo ON cs.soc_code = bo.soc_code
    LEFT JOIN top_tasks tt ON cs.soc_code = tt.soc_code
    LEFT JOIN `{PROJECT_DATASET}.dim_occupations` occ ON cs.soc_code = occ.soc_code
    LEFT JOIN `{PROJECT_DATASET}.occupations_oews_clean` oews ON cs.soc_code = oews.soc_code
    LEFT JOIN `{OUTPUT_TABLE}` scored
      ON cs.soc_code = scored.soc_code AND scored.scoring_run_id = @run_id
    WHERE scored.soc_code IS NULL
    {"LIMIT @limit" if limit else ""}
    """
    params = [bigquery.ScalarQueryParameter("run_id", "STRING", SCORING_RUN_ID)]
    if limit:
        params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    return [dict(r) for r in bq_client.query(query, job_config=job_config).result()]


def build_prompt(occ: dict) -> str:
    """Assemble the grounded, anchored scoring prompt for one occupation."""
    lines = [ANCHOR_BANDS, "", "Score this ONE occupation:", ""]
    lines.append(f"OCCUPATION: {occ.get('occupation_title') or 'Unknown'}")
    if occ.get("occupation_description"):
        lines.append(f"DESCRIPTION: {occ['occupation_description']}")
    if occ.get("tasks"):
        lines.append(f"REPRESENTATIVE TASKS: {occ['tasks']}")
    if occ.get("entry_education"):
        lines.append(f"TYPICAL ENTRY EDUCATION: {occ['entry_education']}")
    if occ.get("median_wage_annual"):
        lines.append(f"MEDIAN ANNUAL WAGE: ${int(occ['median_wage_annual']):,}")
    if occ.get("outlook_description"):
        lines.append(f"BLS OUTLOOK: {occ['outlook_description']}")
    lines += [
        "",
        "Rate how much AI is likely to reshape the MIX OF TASKS of this "
        "occupation, 0-10 (one decimal), anchored to the bands above. "
        + NO_JOB_LOSS_CLAUSE,
        "If the description and tasks are missing or unusable, return "
        'status="insufficient_data" with exposure=null and say why in the '
        "rationale. Otherwise return status=\"scored\". Keep the rationale to "
        "1-2 sentences grounded only in the supplied description/tasks.",
    ]
    return "\n".join(lines)


def to_row(occ: dict, result: OccupationScore, now: str) -> dict:
    scored = result.status == "scored" and result.exposure is not None
    return {
        "soc_code": occ["soc_code"],
        "occupation_title": occ.get("occupation_title"),
        "occupation_exposure_score": round(result.exposure, 1) if scored else None,
        "confidence_level": result.confidence if scored else None,
        "score_rationale": result.rationale if scored else None,
        "scoring_status": "scored" if scored else "insufficient_data",
        "scoring_run_id": SCORING_RUN_ID,
        "prompt_version": PROMPT_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "model_version": MODEL,
        "scored_at": now,
    }


def write_rows(rows: list[dict]) -> None:
    if not rows:
        return
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=OUTPUT_SCHEMA,
        autodetect=False,
    )
    bq_client.load_table_from_json(rows, OUTPUT_TABLE, job_config=job_config).result()


async def score_one(occ: dict, sem: asyncio.Semaphore) -> dict:
    result: OccupationScore = await score_json(build_prompt(occ), OccupationScore, sem)
    return to_row(occ, result, datetime.now(timezone.utc).isoformat())


def register_run(scored: int, failed: int) -> None:
    """Record this scoring run in ai_scoring_runs (not approved yet)."""
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "scoring_run_id": SCORING_RUN_ID,
        "run_name": "Karpathy-style occupation scoring (Layer A)",
        "model_name": MODEL,
        "model_version": MODEL,
        "prompt_version": PROMPT_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "scoring_scale_min": 0,
        "scoring_scale_max": 10,
        "run_status": "completed",
        "is_approved": False,
        "task_count_submitted": scored + failed,
        "task_count_scored": scored,
        "task_count_failed": failed,
        "started_at": now,
        "completed_at": now,
        "approved_at": None,
        "notes": "Layer A of EXPOSURE_REBUILD_PLAN.md. Review a sample, then --approve.",
        "created_at": now,
    }
    # Replace any prior registration of this run id, then append the fresh row.
    bq_client.query(
        f"DELETE FROM `{RUNS_TABLE}` WHERE scoring_run_id = @rid",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("rid", "STRING", SCORING_RUN_ID)]),
    ).result()
    bq_client.load_table_from_json(
        [row], RUNS_TABLE,
        job_config=bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            autodetect=False,
        ),
    ).result()


def approve_run() -> None:
    # Approval is marked with run_status='approved', NOT is_approved=TRUE, on
    # purpose: rollup_pipeline.sql selects its TASK-level production run with
    # `WHERE is_approved = TRUE ORDER BY approved_at DESC`. Setting is_approved
    # here would make that SQL grab this occupation-level run (which has no
    # task_ai_scores rows) and silently empty the old rollup. Keeping the two
    # approval signals separate lets both paths coexist untouched.
    bq_client.query(
        f"""UPDATE `{RUNS_TABLE}`
            SET run_status = 'approved', approved_at = CURRENT_TIMESTAMP()
            WHERE scoring_run_id = @rid""",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("rid", "STRING", SCORING_RUN_ID)]),
    ).result()
    print(f"Marked '{SCORING_RUN_ID}' approved.")


async def run_batch(limit: int | None) -> None:
    ensure_output_table()
    occs = get_pending_occupations(limit)
    print(f"Scoring {len(occs)} occupations for run '{SCORING_RUN_ID}'...")
    if not occs:
        print("Nothing to score. Exiting.")
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    buffer: list[dict] = []
    scored = insufficient = failed = 0

    for coro in asyncio.as_completed([score_one(o, sem) for o in occs]):
        try:
            row = await coro
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  WARNING: scoring failed: {str(e)[:120]}")
            continue
        buffer.append(row)
        if row["scoring_status"] == "scored":
            scored += 1
        else:
            insufficient += 1
        if len(buffer) >= WRITE_BATCH_SIZE:
            write_rows(buffer)
            print(f"  ...flushed {len(buffer)} rows ({scored} scored so far)")
            buffer = []
    write_rows(buffer)

    register_run(scored, failed)
    print(f"Done. scored={scored}, insufficient_data={insufficient}, failed={failed}")
    print(
        f"NOTE: run '{SCORING_RUN_ID}' is NOT approved yet. Review a sample, "
        "then:  python -m batch.occupation_scoring --approve"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Score only this many occupations (dry run).")
    parser.add_argument("--approve", action="store_true",
                        help="Mark the run approved instead of scoring.")
    args = parser.parse_args()
    if args.approve:
        approve_run()
    else:
        asyncio.run(run_batch(args.limit))
