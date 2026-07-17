"""
batch/_manual_plumbing_check.py

ONE-OFF, MANUAL script -- not part of the permanent pipeline. Delete this
file once Vertex AI access is sorted and the real dry run works.

Purpose: verify everything in task_scoring.py EXCEPT the actual Gemini
call -- the BigQuery query logic, the Python bigquery.Client() connection,
and (most importantly) the insert_rows_json() write path, which has never
actually been exercised yet.

SAFETY: writes fake rows under scoring_run_id = "test_plumbing_run", NEVER
"task_ai_run_v1" -- this cannot pollute real production data. Clean up
afterward with the DELETE query printed at the end of this script.

Run:
    python -m batch._manual_plumbing_check
"""

from datetime import datetime, timezone

from batch.task_scoring import (
    PROJECT_DATASET,
    bq_client,
    get_pending_requests,
    write_scores,
)

TEST_RUN_ID = "test_plumbing_run"


def main():
    print(f"Using dataset: {PROJECT_DATASET}\n")

    # ------------------------------------------------------------------
    # 1. Test the real query logic against real data (no Gemini needed)
    # ------------------------------------------------------------------
    print("Step 1: fetching 3 real pending requests for task_ai_run_v1...")
    requests = get_pending_requests("task_ai_run_v1", limit=3)

    if not requests:
        print("FAIL: got zero requests back. Either task_ai_run_v1 has no "
              "rows, or everything under it is already scored. Stopping.")
        return

    print(f"OK: got {len(requests)} requests back.")
    for r in requests:
        print(f"  - task_id={r['task_id']}  onet_soc_code={r['onet_soc_code']}")

    # ------------------------------------------------------------------
    # 2. Fabricate fake scores (standing in for what Gemini would return)
    #    and test the actual insert path -- this has never run before now
    # ------------------------------------------------------------------
    print(f"\nStep 2: writing {len(requests)} FAKE test rows under "
          f"scoring_run_id='{TEST_RUN_ID}' (never touches real data)...")

    now = datetime.now(timezone.utc).isoformat()
    fake_rows = [
        {
            "scoring_run_id": TEST_RUN_ID,
            "onet_soc_code": r["onet_soc_code"],
            "task_id": r["task_id"],
            "ai_exposure_score": 5.0,
            "confidence_level": "medium",
            "score_rationale": "PLUMBING TEST ROW -- not a real score.",
            "scoring_status": "scored",
            "model_name": "TEST",
            "model_version": "TEST",
            "prompt_version": r["prompt_version"],
            "rubric_version": r["rubric_version"],
            "scored_at": now,
            "created_at": now,
        }
        for r in requests
    ]

    try:
        write_scores(fake_rows)
        print("OK: insert_rows_json succeeded with no errors.")
    except Exception as e:
        print(f"FAIL: write_scores raised an exception: {e}")
        return

    # ------------------------------------------------------------------
    # 3. Read the fake rows back to confirm they actually landed correctly
    # ------------------------------------------------------------------
    print("\nStep 3: reading the fake rows back to confirm shape...")
    verify_query = f"""
        SELECT task_id, onet_soc_code, ai_exposure_score, scoring_status
        FROM `{PROJECT_DATASET}.task_ai_scores`
        WHERE scoring_run_id = @test_run_id
    """
    from google.cloud import bigquery
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("test_run_id", "STRING", TEST_RUN_ID)
        ]
    )
    rows = list(bq_client.query(verify_query, job_config=job_config).result())
    print(f"OK: found {len(rows)} rows written back.")
    for row in rows:
        print(f"  - {dict(row.items())}")

    print("\n" + "=" * 60)
    print("Plumbing check complete. Everything except the Gemini call")
    print("itself is verified working.")
    print("=" * 60)
    print("\nIMPORTANT -- clean up the fake test rows with:\n")
    print(f"  DELETE FROM `{PROJECT_DATASET}.task_ai_scores`")
    print(f"  WHERE scoring_run_id = '{TEST_RUN_ID}';")


if __name__ == "__main__":
    main()