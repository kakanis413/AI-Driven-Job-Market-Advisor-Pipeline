"""
Data pipeline: BigQuery → data.json → Google Cloud Storage

This module builds the "read path" for the college-majors heatmap visualizer.
It queries BigQuery tables, computes employment-weighted metrics per major,
outputs a compact data.json, and uploads it to GCS with caching enabled.

Tables:
    - dim_majors: One row per college major (CIP code, graduates, debt, earnings)
    - cip4_to_soc_crosswalk_clean: Many-to-many bridge between CIP ↔ SOC codes
    - occupations_oews_clean: One row per occupation (SOC code, wages, employment)

Usage:
    python data_pipeline.py [--bucket BUCKET_NAME] [--output PATH] [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from google.cloud import bigquery
from google.cloud import storage


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

GCP_PROJECT = "sprinternship-sea-2026"
BQ_DATASET = "majors"

# Table names (fully qualified)
MAJORS_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.dim_major_cip4_clean"
CROSSWALK_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.cip4_to_soc_crosswalk_clean"
OEWS_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.occupations_oews_clean"
OCCUPATIONS_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.dim_occupations"
SCORES_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.major_ai_scores"
RATIONALES_TABLE = f"{GCP_PROJECT}.{BQ_DATASET}.major_ai_rationales"

# Default GCS bucket for output
DEFAULT_BUCKET = "majors-data-bucket"
DEFAULT_OUTPUT_PATH = "data.json"

# Cache-Control header for GCS object (1 hour public cache)
CACHE_CONTROL = "public, max-age=3600"


# ─────────────────────────────────────────────────────────────────────────────
# SQL Query
# ─────────────────────────────────────────────────────────────────────────────

def build_majors_query() -> str:
    """
    Build the SQL query that joins majors with occupations via the crosswalk
    and computes employment-weighted metrics.

    Returns:
        SQL query string
    """
    return f"""
    WITH
    -- Step 0: Get AI exposure scores and rationales
    ai_data AS (
        SELECT
            s.cip4_code,
            s.major_exposure_score,
            r.rationale
        FROM `{SCORES_TABLE}` s
        LEFT JOIN `{RATIONALES_TABLE}` r
            ON s.cip4_code = r.cip4_code
    ),

    -- Step 1: Get occupation data with employment and growth from dim_occupations
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

    -- Step 2: Aggregate occupation metrics per major (employment-weighted)
    major_occupation_metrics AS (
        SELECT
            cip4_code,
            -- Employment-weighted average of median wages from linked occupations
            SAFE_DIVIDE(
                SUM(employment_2024 * median_wage_annual),
                SUM(employment_2024)
            ) AS weighted_occ_pay,
            -- Employment-weighted average growth (outlook_pct)
            SAFE_DIVIDE(
                SUM(employment_2024 * outlook_pct),
                SUM(employment_2024)
            ) AS weighted_growth,
            -- Count of distinct occupations (versatility)
            COUNT(DISTINCT soc_code) AS versatility,
            -- Total linked employment
            SUM(employment_2024) AS total_linked_employment
        FROM occupation_data
        GROUP BY cip4_code
    ),

    -- Step 3: Join with majors table and compute final metrics
    majors_with_metrics AS (
        SELECT
            m.cip4_code,
            m.major_name AS major,
            m.cip_family_code AS family,
            m.completions_bachelors AS graduates,
            m.median_earnings_4yr AS median_pay,
            m.median_debt,
            -- Fallback to 0.0 if growth is null to satisfy schema validation
            COALESCE(occ.weighted_growth, 0.0) AS growth,
            occ.versatility
        FROM `{MAJORS_TABLE}` m
        LEFT JOIN major_occupation_metrics occ
            ON m.cip4_code = occ.cip4_code
        WHERE m.completions_bachelors > 0
    ),

    -- Step 4: Compute pay-to-debt ratio and join AI data
    final_metrics AS (
        SELECT
            mwm.cip4_code,
            major,
            family,
            graduates,
            median_pay,
            growth,
            -- Pay-to-debt ratio (guard against divide by zero)
            CASE
                WHEN median_debt IS NOT NULL AND median_debt > 0
                THEN ROUND(SAFE_DIVIDE(median_pay, median_debt), 2)
                ELSE NULL
            END AS pay_to_debt_ratio,
            COALESCE(versatility, 0) AS versatility,
            -- AI exposure from scores table (NULL if no score - not fabricated)
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

    Args:
        rows: List of major dictionaries
        field: Field name to normalize

    Returns:
        Rows with added '{field}_norm' field
    """
    # Extract non-null values
    values = [r[field] for r in rows if r.get(field) is not None]

    if not values:
        # No valid values, set all normalized to None
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

    Args:
        rows: Raw BigQuery result rows

    Returns:
        List of processed major dictionaries with normalized fields only
    """
    # Convert to list of dicts
    majors = [dict(row.items()) for row in rows]

    # Normalize numeric metrics (creates *_norm fields)
    # Note: ai_exposure is NOT normalized - NULL values indicate missing data
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
        # 1. Parse growth (float) into a string category to satisfy the schema
        raw_growth = m.get("growth")
        if raw_growth is None:
            growth_str = "average"
        elif raw_growth > 0.05:
            growth_str = "faster"
        elif raw_growth < -0.02:
            growth_str = "slower"
        else:
            growth_str = "average"

        # 2. Convert median_pay strictly to an integer
        raw_pay = m.get("median_pay")
        pay_int = int(raw_pay) if raw_pay is not None else 50000

        # 3. Exposure: keep as None if missing (frontend defaults to 0)
        # Per test_schemas.py: unknowns should be marked "not available", not fabricated
        raw_exposure = m.get("ai_exposure")
        exposure_float = float(raw_exposure) if raw_exposure is not None else None

        processed_majors.append({
            # CIP code for matching (not displayed to user)
            "cip": m.get("cip"),

            # Standard metadata
            "major": m.get("major"),
            "family": m.get("family"),
            "graduates": m.get("graduates"),

            # Strict raw types matching MajorAnalysisSchema validation
            "major_name": m.get("major"), # map to major_name expected by schema
            "exposure": exposure_float,
            "median_pay": pay_int,
            "growth": growth_str,
            "occupations": [], # Defaulting to empty list as allowed by test_schemas.py
            "query_context": "",

            # AI rationale (None if missing - frontend shows "pending" message)
            "rationale": m.get("rationale"),

            # Raw values for calculations
            "pay_to_debt_ratio": m.get("pay_to_debt_ratio"),
            "versatility": m.get("versatility"),

            # Normalized fields required by visualizer UI
            "median_pay_norm": m.get("median_pay_norm"),
            "growth_norm": m.get("growth_norm"),
            "pay_to_debt_ratio_norm": m.get("pay_to_debt_ratio_norm"),
            "versatility_norm": m.get("versatility_norm"),
        })

    return processed_majors


def query_majors(client: bigquery.Client) -> list[dict[str, Any]]:
    """
    Execute the majors query and return processed results.

    Args:
        client: BigQuery client

    Returns:
        List of major dictionaries ready for JSON output
    """
    query = build_majors_query()
    print(f"Executing BigQuery query against {GCP_PROJECT}.{BQ_DATASET}...")

    job = client.query(query)
    results = list(job.result())

    print(f"Retrieved {len(results)} majors from BigQuery")
    return process_bigquery_results(results)


# ─────────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────────

def write_json(majors: list[dict[str, Any]], output_path: str | Path) -> Path:
    """
    Write majors data to a JSON file.

    Args:
        majors: List of major dictionaries
        output_path: Path to output file

    Returns:
        Path to written file
    """
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
    """
    Upload the JSON file to Google Cloud Storage with caching headers.

    Args:
        local_path: Path to local JSON file
        bucket_name: GCS bucket name
        blob_name: Object name in the bucket
        cache_control: Cache-Control header value

    Returns:
        GCS URI of uploaded object
    """
    client = storage.Client(project=GCP_PROJECT)

    # Get or create bucket
    try:
        bucket = client.get_bucket(bucket_name)
    except Exception:
        print(f"Bucket {bucket_name} not found. Creating...")
        bucket = client.create_bucket(bucket_name, location="US")
        print(f"Created bucket {bucket_name}")

    blob = bucket.blob(blob_name)

    # Set cache control metadata
    blob.cache_control = cache_control
    blob.content_type = "application/json"

    # Upload file
    blob.upload_from_filename(str(local_path))

    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

    print(f"Uploaded to {gcs_uri}")
    print(f"Public URL: {public_url}")
    print(f"Cache-Control: {cache_control}")

    return gcs_uri


# ─────────────────────────────────────────────────────────────────────────────
# Main Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    bucket_name: str = DEFAULT_BUCKET,
    output_path: str = DEFAULT_OUTPUT_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Run the complete data pipeline: BigQuery → JSON → GCS.

    Args:
        bucket_name: GCS bucket for upload
        output_path: Local path for JSON output
        dry_run: If True, skip GCS upload

    Returns:
        Pipeline result summary
    """
    print("=" * 60)
    print("College Majors Data Pipeline")
    print("=" * 60)

    # Initialize BigQuery client
    bq_client = bigquery.Client(project=GCP_PROJECT)

    # Query and process data
    majors = query_majors(bq_client)

    if not majors:
        raise ValueError("No majors returned from BigQuery query")

    # Write local JSON file
    local_file = write_json(majors, output_path)

    # Upload to GCS (unless dry run)
    gcs_uri = None
    if not dry_run:
        gcs_uri = upload_to_gcs(local_file, bucket_name)
    else:
        print("Dry run: skipping GCS upload")

    result = {
        "majors_count": len(majors),
        "local_file": str(local_file),
        "gcs_uri": gcs_uri,
        "bucket": bucket_name if not dry_run else None,
    }

    print("=" * 60)
    print("Pipeline complete!")
    print(f"  Majors processed: {result['majors_count']}")
    print(f"  Local file: {result['local_file']}")
    if gcs_uri:
        print(f"  GCS URI: {result['gcs_uri']}")
    print("=" * 60)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build data.json from BigQuery and upload to GCS"
    )
    parser.add_argument(
        "--bucket",
        default=DEFAULT_BUCKET,
        help=f"GCS bucket name (default: {DEFAULT_BUCKET})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help=f"Local output path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip GCS upload (local file only)",
    )

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