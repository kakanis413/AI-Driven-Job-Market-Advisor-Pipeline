"""
batch/major_scoring.py  — Layer B of the Karpathy-style exposure rebuild.

Scores each MAJOR directly for AI exposure 0-10 with one Gemini call, using a
major-adapted version of the anchored Karpathy rubric (batch/karpathy_rubric.py).
Grounds each call in the major's CIP definition + its representative occupations
with their Layer-A occupation scores (occupation_ai_scores_v2) + pay/growth, and
tells the model to weigh the roles a typical graduate actually enters — NOT a
flat average. Writes to NEW versioned tables `major_ai_scores_v2` +
`major_ai_rationales_v2`.

WHY THIS EXISTS (see EXPOSURE_REBUILD_PLAN.md §4 Layer B):
This is the direct fix for the compression. The old rollup takes a plain mean
across a major's SOCs, which always regresses toward ~5 (measured: mean 5.28,
max 6.9, stdev 1.05 — no major ever reaches 8-10). Scoring the major as a unit
against an anchored rubric puts the full 0-10 range back in play. It also fixes
COVERAGE: the old rollup drops any major with <3 usable SOCs or <50% coverage
(96 majors ended up null); direct scoring can still rate those from their CIP
definition + whatever occupations they do have, so far more majors get a score.

This does NOT touch the task/rollup path or the old major_ai_scores table. It
is a parallel, versioned run. Nothing here is imported by main.py.

Run from the project root:
    python -m batch.major_scoring --limit 10     # dry run, sanity check
    python -m batch.major_scoring                 # full run (~360 majors)
    python -m batch.major_scoring --approve       # mark the run approved
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

SCORES_TABLE = f"{PROJECT_DATASET}.major_ai_scores_v2"
RATIONALES_TABLE = f"{PROJECT_DATASET}.major_ai_rationales_v2"
RUNS_TABLE = f"{PROJECT_DATASET}.ai_scoring_runs"
OCC_SCORES_V2 = f"{PROJECT_DATASET}.occupation_ai_scores_v2"

# Which occupation-scoring run to use for grounding. Layer A must be run first.
OCC_RUN_ID = "occupation_karpathy_v2"

SCORING_RUN_ID = "major_karpathy_v2"
PROMPT_VERSION = "karpathy_major_v1"
RUBRIC_VERSION = "karpathy_anchored_major_v1"

CONCURRENCY = 16
WRITE_BATCH_SIZE = 60
MAX_OCCS_PER_MAJOR = 15

bq_client = bigquery.Client(project=GCP_PROJECT)

SCORES_SCHEMA = [
    bigquery.SchemaField("cip4_code", "STRING"),
    bigquery.SchemaField("major_name", "STRING"),
    bigquery.SchemaField("major_exposure_score", "FLOAT"),
    bigquery.SchemaField("confidence_level", "STRING"),
    bigquery.SchemaField("occupations_considered", "INTEGER"),
    bigquery.SchemaField("scoring_status", "STRING"),
    bigquery.SchemaField("scoring_run_id", "STRING"),
    bigquery.SchemaField("prompt_version", "STRING"),
    bigquery.SchemaField("rubric_version", "STRING"),
    bigquery.SchemaField("model_version", "STRING"),
    bigquery.SchemaField("scored_at", "TIMESTAMP"),
]
RATIONALES_SCHEMA = [
    bigquery.SchemaField("cip4_code", "STRING"),
    bigquery.SchemaField("rationale", "STRING"),
    bigquery.SchemaField("model", "STRING"),
    bigquery.SchemaField("prompt_version", "STRING"),
    bigquery.SchemaField("scoring_run_id", "STRING"),
    bigquery.SchemaField("scored_at", "TIMESTAMP"),
]


class MajorScore(BaseModel):
    status: Literal["scored", "insufficient_data"]
    exposure: float | None
    confidence: Literal["high", "medium", "low"] | None
    rationale: str


def ensure_tables() -> None:
    bq_client.create_table(bigquery.Table(SCORES_TABLE, schema=SCORES_SCHEMA), exists_ok=True)
    bq_client.create_table(bigquery.Table(RATIONALES_TABLE, schema=RATIONALES_SCHEMA), exists_ok=True)


def get_pending_majors(limit: int | None) -> list[dict]:
    """
    Every heatmap major not yet scored for this run, with its CIP definition and
    representative occupations (Layer-A score + pay + growth + employment).

    Scores the SAME major set the frontend shows (completions > 0 AND
    include_in_heatmap), so every tile can get a number. Resumable via the
    LEFT JOIN anti-pattern against the output table.
    """
    query = f"""
    WITH majors AS (
      SELECT m.cip4_code, m.major_name, m.official_cip4_title,
             m.cip_family_code, m.median_earnings_4yr
      FROM `{PROJECT_DATASET}.dim_major_cip4_clean` m
      WHERE m.completions_bachelors > 0 AND m.include_in_heatmap
    ),
    cip_def AS (
      -- Richest available definition: prefer the cip6 program text under the
      -- cip4 group (the cip4 row itself usually just points at the cip6 code).
      SELECT cip4_code, ANY_VALUE(cip_definition HAVING MAX dl) AS cip_definition
      FROM (
        SELECT SUBSTR(cip_code, 1, 5) AS cip4_code, cip_definition,
               LENGTH(cip_definition) AS dl
        FROM `{PROJECT_DATASET}.cip_taxonomy_2020_clean`
        WHERE cip_level = 'cip6_program' AND cip_definition IS NOT NULL
      )
      GROUP BY cip4_code
    ),
    occ AS (
      SELECT
        x.cip4_code,
        STRING_AGG(
          FORMAT('%s (AI-exposure %s; pay %s; %s)',
                 x.occupation_name,
                 CASE WHEN s.occupation_exposure_score IS NULL THEN 'n/a'
                      ELSE CAST(s.occupation_exposure_score AS STRING) END,
                 CASE WHEN oews.median_wage_annual IS NULL THEN 'n/a'
                      ELSE FORMAT('$%dk', CAST(oews.median_wage_annual/1000 AS INT64)) END,
                 CASE WHEN d.outlook_pct IS NULL THEN 'growth n/a'
                      WHEN d.outlook_pct >= 7 THEN 'fast growth'
                      WHEN d.outlook_pct < 0 THEN 'declining'
                      ELSE 'average growth' END),
          '\\n  - ' ORDER BY x.relationship_weight DESC, d.employment_2024 DESC NULLS LAST) AS occ_block,
        COUNT(*) AS occ_count
      FROM (
        SELECT cip4_code, soc_code, occupation_name, relationship_weight,
               ROW_NUMBER() OVER (PARTITION BY cip4_code
                 ORDER BY relationship_weight DESC) AS rn
        FROM `{PROJECT_DATASET}.cip4_to_soc_crosswalk_clean`
        WHERE soc_code IS NOT NULL
      ) x
      LEFT JOIN `{OCC_SCORES_V2}` s
        ON x.soc_code = s.soc_code AND s.scoring_run_id = @occ_run
      LEFT JOIN `{PROJECT_DATASET}.occupations_oews_clean` oews ON x.soc_code = oews.soc_code
      LEFT JOIN `{PROJECT_DATASET}.dim_occupations` d ON x.soc_code = d.soc_code
      WHERE x.rn <= {MAX_OCCS_PER_MAJOR}
      GROUP BY x.cip4_code
    )
    SELECT
      m.cip4_code, m.major_name, m.official_cip4_title,
      cd.cip_definition, o.occ_block,
      COALESCE(o.occ_count, 0) AS occ_count,
      m.median_earnings_4yr
    FROM majors m
    LEFT JOIN cip_def cd ON m.cip4_code = cd.cip4_code
    LEFT JOIN occ o ON m.cip4_code = o.cip4_code
    LEFT JOIN `{SCORES_TABLE}` scored
      ON m.cip4_code = scored.cip4_code AND scored.scoring_run_id = @run_id
    WHERE scored.cip4_code IS NULL
    {"LIMIT @limit" if limit else ""}
    """
    params = [
        bigquery.ScalarQueryParameter("run_id", "STRING", SCORING_RUN_ID),
        bigquery.ScalarQueryParameter("occ_run", "STRING", OCC_RUN_ID),
    ]
    if limit:
        params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    return [dict(r) for r in bq_client.query(query, job_config=job_config).result()]


def build_prompt(major: dict) -> str:
    lines = [
        ANCHOR_BANDS,
        "",
        "Now rate a COLLEGE MAJOR, 0-10, on the SAME scale. Score the major by "
        "the work its graduates typically do. Weigh the occupations a typical "
        "graduate actually enters and their trajectory — do NOT take a flat "
        "average across every loosely-related occupation, and apply the strong "
        "digital-work prior (computing/data/design/analysis majors belong high).",
        "",
        f"MAJOR: {major.get('major_name') or major.get('official_cip4_title')}",
    ]
    if major.get("cip_definition"):
        lines.append(f"FIELD DEFINITION (CIP): {major['cip_definition']}")
    if major.get("occ_block"):
        lines.append("REPRESENTATIVE OCCUPATIONS GRADUATES ENTER "
                     "(with their own AI-exposure scores):\n  - " + major["occ_block"])
    else:
        lines.append("REPRESENTATIVE OCCUPATIONS: none mapped — reason from the "
                     "field definition and the anchor bands.")
    lines += [
        "",
        "Return exposure (0-10, one decimal), confidence, and a 2-3 sentence "
        "rationale a student would find useful, naming the concrete tasks AI "
        "reshapes. " + NO_JOB_LOSS_CLAUSE,
        "Only return status=\"insufficient_data\" if you truly cannot place the "
        "field on the scale; otherwise return status=\"scored\".",
    ]
    return "\n".join(lines)


def to_rows(major: dict, result: MajorScore, now: str) -> tuple[dict, dict | None]:
    scored = result.status == "scored" and result.exposure is not None
    score_row = {
        "cip4_code": major["cip4_code"],
        "major_name": major.get("major_name"),
        "major_exposure_score": round(result.exposure, 1) if scored else None,
        "confidence_level": result.confidence if scored else None,
        "occupations_considered": int(major.get("occ_count") or 0),
        "scoring_status": "scored" if scored else "insufficient_data",
        "scoring_run_id": SCORING_RUN_ID,
        "prompt_version": PROMPT_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "model_version": MODEL,
        "scored_at": now,
    }
    rationale_row = None
    if scored and result.rationale:
        rationale_row = {
            "cip4_code": major["cip4_code"],
            "rationale": result.rationale,
            "model": MODEL,
            "prompt_version": PROMPT_VERSION,
            "scoring_run_id": SCORING_RUN_ID,
            "scored_at": now,
        }
    return score_row, rationale_row


def write_batch(score_rows: list[dict], rationale_rows: list[dict]) -> None:
    if score_rows:
        bq_client.load_table_from_json(
            score_rows, SCORES_TABLE,
            job_config=bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
                schema=SCORES_SCHEMA, autodetect=False),
        ).result()
    if rationale_rows:
        bq_client.load_table_from_json(
            rationale_rows, RATIONALES_TABLE,
            job_config=bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
                schema=RATIONALES_SCHEMA, autodetect=False),
        ).result()


async def score_one(major: dict, sem: asyncio.Semaphore) -> tuple[dict, dict | None]:
    result: MajorScore = await score_json(build_prompt(major), MajorScore, sem)
    return to_rows(major, result, datetime.now(timezone.utc).isoformat())


def register_run(scored: int, failed: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "scoring_run_id": SCORING_RUN_ID,
        "run_name": "Karpathy-style direct major scoring (Layer B)",
        "model_name": MODEL, "model_version": MODEL,
        "prompt_version": PROMPT_VERSION, "rubric_version": RUBRIC_VERSION,
        "scoring_scale_min": 0, "scoring_scale_max": 10,
        "run_status": "completed", "is_approved": False,
        "task_count_submitted": scored + failed,
        "task_count_scored": scored, "task_count_failed": failed,
        "started_at": now, "completed_at": now, "approved_at": None,
        "notes": "Layer B of EXPOSURE_REBUILD_PLAN.md. Review a sample, then --approve.",
        "created_at": now,
    }
    bq_client.query(
        f"DELETE FROM `{RUNS_TABLE}` WHERE scoring_run_id = @rid",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("rid", "STRING", SCORING_RUN_ID)]),
    ).result()
    bq_client.load_table_from_json(
        [row], RUNS_TABLE,
        job_config=bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND, autodetect=False),
    ).result()


def approve_run() -> None:
    # See occupation_scoring.approve_run: approval uses run_status='approved',
    # not is_approved=TRUE, so it never collides with rollup_pipeline.sql's
    # task-level `WHERE is_approved = TRUE` production-run selector.
    bq_client.query(
        f"""UPDATE `{RUNS_TABLE}`
            SET run_status = 'approved', approved_at = CURRENT_TIMESTAMP()
            WHERE scoring_run_id = @rid""",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("rid", "STRING", SCORING_RUN_ID)]),
    ).result()
    print(f"Marked '{SCORING_RUN_ID}' approved.")


async def run_batch(limit: int | None) -> None:
    ensure_tables()
    majors = get_pending_majors(limit)
    print(f"Scoring {len(majors)} majors for run '{SCORING_RUN_ID}'...")
    if not majors:
        print("Nothing to score. Exiting.")
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    score_buf: list[dict] = []
    rat_buf: list[dict] = []
    scored = insufficient = failed = 0

    for coro in asyncio.as_completed([score_one(m, sem) for m in majors]):
        try:
            score_row, rat_row = await coro
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  WARNING: scoring failed: {str(e)[:120]}")
            continue
        score_buf.append(score_row)
        if rat_row:
            rat_buf.append(rat_row)
        if score_row["scoring_status"] == "scored":
            scored += 1
        else:
            insufficient += 1
        if len(score_buf) >= WRITE_BATCH_SIZE:
            write_batch(score_buf, rat_buf)
            print(f"  ...flushed {len(score_buf)} rows ({scored} scored so far)")
            score_buf, rat_buf = [], []
    write_batch(score_buf, rat_buf)

    register_run(scored, failed)
    print(f"Done. scored={scored}, insufficient_data={insufficient}, failed={failed}")
    print(
        f"NOTE: run '{SCORING_RUN_ID}' is NOT approved yet. Review a sample, "
        "then:  python -m batch.major_scoring --approve"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Score only this many majors (dry run).")
    parser.add_argument("--approve", action="store_true",
                        help="Mark the run approved instead of scoring.")
    args = parser.parse_args()
    if args.approve:
        approve_run()
    else:
        asyncio.run(run_batch(args.limit))
