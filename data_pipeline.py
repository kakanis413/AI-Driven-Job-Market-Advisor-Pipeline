"""
Data pipeline: BigQuery → data.json → Google Cloud Storage

Filters out low-sample/niche majors lacking salary data to ensure high-impact,
accurate statistics on the client frontend.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from google.cloud import bigquery
from google.cloud import storage

# ─────────────────────────────────────────────────────────────────────────────
# Configuration & Thresholds (Option 1 Applied)
# ─────────────────────────────────────────────────────────────────────────────

GCP_PROJECT = "sprinternship-sea-2026"
BQ_DATASET = "majors"

# Data Quality Thresholds
MIN_GRADUATES_THRESHOLD = 500  # Excludes micro-majors with trivial graduate counts (< 500)
REQUIRE_SALARY_DATA = True     # Excludes rows where median pay is missing ('—')

MAJORS_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.dim_major_cip4_clean"
CROSSWALK_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.cip4_to_soc_crosswalk_clean"
OEWS_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.occupations_oews_clean"
OCCUPATIONS_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.dim_occupations"

SCORES_V2_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.major_ai_scores_v2"
RATIONALES_V2_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.major_ai_rationales_v2"
SCORES_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.major_ai_scores"
RATIONALES_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.major_ai_rationales"
RUNS_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.ai_scoring_runs"

MAJOR_SCORING_RUN_ID = "major_karpathy_v2"

DEFAULT_BUCKET = "majors-data-bucket"
DEFAULT_OUTPUT_PATH = "data.json"
CACHE_CONTROL = "public, max-age=3600"


# ─────────────────────────────────────────────────────────────────────────────
# SQL Query
# ─────────────────────────────────────────────────────────────────────────────

def build_majors_query(min_graduates: int = MIN_GRADUATES_THRESHOLD, require_salary: bool = REQUIRE_SALARY_DATA) -> str:
    """
    Build the SQL query with data quality thresholds to filter out niche majors.
    """
    salary_clause = "AND m.median_earnings_4yr IS NOT NULL" if require_salary else ""

    return f"""
    WITH
    approved_major_run AS (
        SELECT scoring_run_id
        FROM `{RUNS_TABLE}`
        WHERE scoring_run_id = '{MAJOR_SCORING_RUN_ID}'
          AND run_status = 'approved'
    ),
    scores_v2 AS (
        SELECT v2.cip4_code, v2.major_exposure_score
        FROM `{SCORES_V2_TABLE}` v2
        JOIN approved_major_run a ON v2.scoring_run_id = a.scoring_run_id
        WHERE v2.scoring_status = 'scored'
    ),
    rationales_v2 AS (
        SELECT rv2.cip4_code, rv2.rationale
        FROM `{RATIONALES_V2_TABLE}` rv2
        JOIN approved_major_run a ON rv2.scoring_run_id = a.scoring_run_id
    ),
    ai_data AS (
        SELECT
            COALESCE(v2.cip4_code, s.cip4_code) AS cip4_code,
            COALESCE(v2.major_exposure_score, s.major_exposure_score) AS major_exposure_score,
            COALESCE(rv2.rationale, r.rationale) AS rationale
        FROM scores_v2 v2
        FULL OUTER JOIN `{SCORES_TABLE}` s
            ON v2.cip4_code = s.cip4_code
        LEFT JOIN rationales_v2 rv2
            ON COALESCE(v2.cip4_code, s.cip4_code) = rv2.cip4_code
        LEFT JOIN `{RATIONALES_TABLE}` r
            ON COALESCE(v2.cip4_code, s.cip4_code) = r.cip4_code
    ),

    occupation_data AS (
        SELECT
            cw.cip4_code,
            cw.soc_code,
            occ.employment_2024,
            occ.outlook_pct,
            oews.median_wage_annual
        FROM `{CROSSWALK_TABLE}` cw
        LEFT JOIN `{OCCUPATIONS_TABLE}` occ
            ON cw.soc_code = occ.soc_code
        LEFT JOIN `{OEWS_TABLE}` oews
            ON cw.soc_code = oews.soc_code
        WHERE occ.employment_2024 IS NOT NULL
          AND occ.employment_2024 > 0
    ),

    major_occupation_metrics AS (
        SELECT
            cip4_code,
            SAFE_DIVIDE(
                SUM(employment_2024 * median_wage_annual),
                SUM(employment_2024)
            ) AS weighted_occ_pay,
            SAFE_DIVIDE(
                SUM(employment_2024 * outlook_pct),
                SUM(employment_2024)
            ) AS weighted_growth,
            COUNT(DISTINCT soc_code) AS versatility,
            SUM(employment_2024) AS total_linked_employment
        FROM occupation_data
        GROUP BY cip4_code
    ),

    majors_with_metrics AS (
        SELECT
            m.cip4_code,
            m.major_name AS major,
            m.cip_family_code AS family,
            m.completions_bachelors AS graduates,
            m.median_earnings_4yr AS median_pay,
            m.median_debt,
            COALESCE(occ.weighted_growth, 0.0) AS growth,
            occ.versatility
        FROM `{MAJORS_TABLE}` m
        LEFT JOIN major_occupation_metrics occ
            ON m.cip4_code = occ.cip4_code
        WHERE m.completions_bachelors >= {min_graduates}
          {salary_clause}
          AND m.include_in_heatmap
    ),

    final_metrics AS (
        SELECT
            mwm.cip4_code,
            major,
            family,
            graduates,
            median_pay,
            growth,
            CASE
                WHEN median_debt IS NOT NULL AND median_debt > 0
                THEN ROUND(SAFE_DIVIDE(median_pay, median_debt), 2)
                ELSE NULL
            END AS pay_to_debt_ratio,
            COALESCE(versatility, 0) AS versatility,
            ai.major_exposure_score AS ai_exposure,
            ai.rationale
        FROM majors_with_metrics mwm
        LEFT JOIN ai_data ai
            ON mwm.cip4_code = ai.cip4_code
    )

    SELECT
        cip4_code AS cip,
        major,
        family,
        graduates,
        median_pay,
        growth,
        pay_to_debt_ratio,
        versatility,
        ai_exposure,
        rationale
    FROM final_metrics
    ORDER BY graduates DESC
    """


# ─────────────────────────────────────────────────────────────────────────────
# Data Processing
# ─────────────────────────────────────────────────────────────────────────────

def normalize_values(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    """
    Add a normalized (0-1) version of a numeric field across all rows.
    """
    values = [r[field] for r in rows if r.get(field) is not None]

    if not values:
        for row in rows:
            row[f"{field}_norm"] = None
        return rows

    min_val = min(values)
    max_val = max(values)
    range_val = max_val - min_val

    for row in rows:
        val = row.get(field)
        if val is None or range_val == 0:
            row[f"{field}_norm"] = None
        else:
            row[f"{field}_norm"] = round((val - min_val) / range_val, 4)

    return rows


def process_bigquery_results(rows: list[bigquery.Row]) -> list[dict[str, Any]]:
    """
    Convert BigQuery rows to dictionaries, normalize metrics, and output
    only the fields needed for the frontend.
    """
    majors = [dict(row.items()) for row in rows]

    metrics_to_normalize = [
        "median_pay",
        "growth",
        "pay_to_debt_ratio",
        "versatility",
    ]

    for metric in metrics_to_normalize:
        majors = normalize_values(majors, metric)

    processed_majors = []
    for m in majors:
        raw_growth = m.get("growth")
        if raw_growth is None:
            growth_str = "average"
        elif raw_growth > 0.05:
            growth_str = "faster"
        elif raw_growth < -0.02:
            growth_str = "slower"
        else:
            growth_str = "average"

        raw_pay = m.get("median_pay")
        pay_int = int(raw_pay) if raw_pay is not None else None

        raw_exposure = m.get("ai_exposure")
        exposure_float = float(raw_exposure) if raw_exposure is not None else None

        processed_majors.append({
            "cip": m.get("cip"),
            "major": m.get("major"),
            "family": m.get("family"),
            "graduates": m.get("graduates"),
            "major_name": m.get("major"),
            "exposure": exposure_float,
            "median_pay": pay_int,
            "growth": growth_str,
            "occupations": [],
            "query_context": "",
            "rationale": m.get("rationale"),
            "pay_to_debt_ratio": m.get("pay_to_debt_ratio"),
            "versatility": m.get("versatility"),
            "median_pay_norm": m.get("median_pay_norm"),
            "growth_norm": m.get("growth_norm"),
            "pay_to_debt_ratio_norm": m.get("pay_to_debt_ratio_norm"),
            "versatility_norm": m.get("versatility_norm"),
        })

    return processed_majors


def query_majors(client: bigquery.Client) -> list[dict[str, Any]]:
    """
    Execute the majors query and return processed results.
    """
    query = build_majors_query()
    print(f"Executing BigQuery query against {GCP_PROJECT}.{BQ_DATASET}...")

    job = client.query(query)
    results = list(job.result())

    print(f"Retrieved {len(results)} high-impact majors from BigQuery")
    return process_bigquery_results(results)


# ─────────────────────────────────────────────────────────────────────────────
# Output & Execution
# ─────────────────────────────────────────────────────────────────────────────

def write_json(majors: list[dict[str, Any]], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(majors, f, indent=2, ensure_ascii=False)

    size_kb = output_path.stat().st_size / 1024
    print(f"Wrote {len(majors)} majors to {output_path} ({size_kb:.1f} KB)")
    return output_path


def upload_to_gcs(
    local_path: Path,
    bucket_name: str,
    blob_name: str = "data.json",
    cache_control: str = CACHE_CONTROL,
) -> str:
    client = storage.Client(project=GCP_PROJECT)

    try:
        bucket = client.get_bucket(bucket_name)
    except Exception:
        print(f"Bucket {bucket_name} not found. Creating...")
        bucket = client.create_bucket(bucket_name, location="US")

    blob = bucket.blob(blob_name)
    blob.cache_control = cache_control
    blob.content_type = "application/json"
    blob.upload_from_filename(str(local_path))

    return f"gs://{bucket_name}/{blob_name}"


def run_pipeline(
    bucket_name: str = DEFAULT_BUCKET,
    output_path: str = DEFAULT_OUTPUT_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    print("=" * 60)
    print("College Majors Data Pipeline (Quality Filtered)")
    print("=" * 60)

    bq_client = bigquery.Client(project=GCP_PROJECT)
    majors = query_majors(bq_client)

    if not majors:
        raise ValueError("No majors returned from BigQuery query")

    local_file = write_json(majors, output_path)

    gcs_uri = None
    if not dry_run:
        gcs_uri = upload_to_gcs(local_file, bucket_name)
    else:
        print("Dry run: skipping GCS upload")

    return {
        "majors_count": len(majors),
        "local_file": str(local_file),
        "gcs_uri": gcs_uri,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Build filtered data.json from BigQuery and upload to GCS"
    )
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    try:
        run_pipeline(
            bucket_name=args.bucket,
            output_path=args.output,
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"Pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()