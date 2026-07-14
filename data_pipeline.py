"""
GCS + BigQuery ingestion pipeline.
Not wired into Sprint 1 — the advisor endpoint receives major data
directly in the request body from the frontend's static data.json.
This file becomes active in Sprint 2 when data.json is generated
from BigQuery on a schedule.
"""

def load_to_gcs(*args, **kwargs):
    raise NotImplementedError("Sprint 2 task — not needed for Sprint 1 milestone.")


def sync_to_bigquery(*args, **kwargs):
    raise NotImplementedError("Sprint 2 task — not needed for Sprint 1 milestone.")