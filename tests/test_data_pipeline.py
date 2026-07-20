"""Tests for the data pipeline's pure helpers.

Replaces the old stub tests, which imported `load_to_gcs` / `sync_to_bigquery` —
functions that no longer exist after the pipeline rewrite. That stale import broke
collection for the entire suite, so no tests could run at all.

These cover the arithmetic/IO helpers that need no BigQuery connection.
"""

import json

from data_pipeline import build_majors_query, normalize_values, write_json


def test_build_majors_query_returns_sql():
    query = build_majors_query()
    assert isinstance(query, str)
    assert "SELECT" in query.upper()


def test_normalize_values_scales_to_0_1():
    rows = [{"pay": 0}, {"pay": 5}, {"pay": 10}]
    out = normalize_values(rows, "pay")
    norms = [r["pay_norm"] for r in out]
    assert norms[0] == 0.0
    assert norms[-1] == 1.0
    assert 0.0 <= norms[1] <= 1.0


def test_normalize_values_handles_all_null():
    rows = [{"pay": None}, {"pay": None}]
    out = normalize_values(rows, "pay")
    assert all(r["pay_norm"] is None for r in out)


def test_write_json_roundtrip(tmp_path):
    majors = [{"major": "Computer science", "exposure": 9.0}]
    path = write_json(majors, tmp_path / "data.json")
    assert path.exists()
    assert json.loads(path.read_text()) == majors
