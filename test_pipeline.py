import pytest
from fastapi.testclient import TestClient

from main import app
from tools import get_major_data


client = TestClient(app)


def test_root():
    resp = client.get("/")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.skip(reason="Gemini credentials are not configured yet")
def test_analyze_major():
    payload = {
        "major_name": "Computer Science",
        "exposure": 9.0,
        "median_pay": 99000,
        "growth": "faster",
        "occupations": [
            {
                "soc": "15-1252",
                "title": "Software developers",
                "exposure": 9.0,
            }
        ],
        "query_context": "Is this major too risky because of AI?",
    }

    resp = client.post("/api/v1/analyze-major", json=payload)

    assert resp.status_code == 200

    body = resp.json()
    assert body["agent_node"] == "college_advisor"
    assert len(body["generated_guidance"]) > 0


@pytest.mark.skip(reason="Gemini credentials are not configured yet")
def test_analyze_major_different_query_gives_different_response():
    base_payload = {
        "major_name": "History",
        "exposure": 3.0,
        "median_pay": 55000,
        "growth": "slower",
        "occupations": [
            {
                "soc": "25-4013",
                "title": "Museum technicians",
                "exposure": 2.0,
            }
        ],
    }

    resp1 = client.post(
        "/api/v1/analyze-major",
        json={
            **base_payload,
            "query_context": "Should I switch majors?",
        },
    )

    resp2 = client.post(
        "/api/v1/analyze-major",
        json={
            **base_payload,
            "query_context": "What jobs can I get?",
        },
    )

    assert resp1.json()["generated_guidance"] != (
        resp2.json()["generated_guidance"]
    )


def test_get_major_data():
    result = get_major_data("Computer Science")

    assert result["status"] == "success"
    assert result["major_name"] == "Computer Science"
    assert result["exposure"] == 9.0
    assert result["median_pay"] == 99000
    assert len(result["occupations"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Data Pipeline Tests
# ─────────────────────────────────────────────────────────────────────────────

from data_pipeline import normalize_values, process_bigquery_results, build_majors_query


def test_normalize_values_basic():
    """Test that values are normalized to 0-1 range."""
    rows = [
        {"median_pay": 50000},
        {"median_pay": 100000},
        {"median_pay": 75000},
    ]
    result = normalize_values(rows, "median_pay")

    assert result[0]["median_pay_norm"] == 0.0  # min
    assert result[1]["median_pay_norm"] == 1.0  # max
    assert result[2]["median_pay_norm"] == 0.5  # midpoint


def test_normalize_values_handles_none():
    """Test that None values are preserved during normalization."""
    rows = [
        {"growth": None},
        {"growth": 10.0},
        {"growth": 20.0},
    ]
    result = normalize_values(rows, "growth")

    assert result[0]["growth_norm"] is None
    assert result[1]["growth_norm"] == 0.0
    assert result[2]["growth_norm"] == 1.0


def test_normalize_values_all_same():
    """Test normalization when all values are identical."""
    rows = [
        {"versatility": 5},
        {"versatility": 5},
    ]
    result = normalize_values(rows, "versatility")

    # When range is 0, normalized values should be None
    assert result[0]["versatility_norm"] is None
    assert result[1]["versatility_norm"] is None


def test_normalize_values_empty_list():
    """Test normalization with empty input."""
    result = normalize_values([], "median_pay")
    assert result == []


class MockBigQueryRow:
    """Mock BigQuery row for testing."""

    def __init__(self, data: dict):
        self._data = data

    def items(self):
        return self._data.items()


def test_process_bigquery_results():
    """Test processing of BigQuery results."""
    mock_rows = [
        MockBigQueryRow({
            "cip": "1107",
            "major": "Computer Science",
            "family": "11",
            "graduates": 35000,
            "median_pay": 100000,
            "median_debt": 20000,
            "growth": None,
            "pay_to_debt_ratio": 5.0,
            "versatility": 10,
            "ai_exposure": None,
        }),
        MockBigQueryRow({
            "cip": "5202",
            "major": "Business Administration",
            "family": "52",
            "graduates": 50000,
            "median_pay": 80000,
            "median_debt": 25000,
            "growth": None,
            "pay_to_debt_ratio": 3.2,
            "versatility": 20,
            "ai_exposure": None,
        }),
    ]

    result = process_bigquery_results(mock_rows)

    assert len(result) == 2
    assert result[0]["cip"] == "1107"
    assert result[0]["major"] == "Computer Science"
    # Check normalized fields exist
    assert "median_pay_norm" in result[0]
    assert "versatility_norm" in result[0]


def test_process_bigquery_results_preserves_cip_as_string():
    """Test that CIP codes with leading zeros are preserved."""
    mock_rows = [
        MockBigQueryRow({
            "cip": "0100",  # Leading zero
            "major": "Agriculture",
            "family": "01",
            "graduates": 10000,
            "median_pay": 50000,
            "median_debt": 15000,
            "growth": None,
            "pay_to_debt_ratio": 3.3,
            "versatility": 5,
            "ai_exposure": None,
        }),
    ]

    result = process_bigquery_results(mock_rows)
    assert result[0]["cip"] == "0100"  # Leading zero preserved


def test_build_majors_query_returns_sql():
    """Test that SQL query is properly constructed."""
    query = build_majors_query()

    # Check that query contains expected table references
    assert "dim_majors" in query
    assert "cip4_to_soc_crosswalk_clean" in query
    assert "occupations_oews_clean" in query

    # Check for employment-weighted calculation
    assert "total_employment" in query
    assert "SAFE_DIVIDE" in query

    # Check for expected output fields
    assert "versatility" in query
    assert "pay_to_debt_ratio" in query
    assert "ai_exposure" in query


@pytest.mark.skip(reason="Requires BigQuery credentials")
def test_full_pipeline_integration():
    """Integration test for the full pipeline (requires GCP auth)."""
    from data_pipeline import run_pipeline

    result = run_pipeline(dry_run=True, output_path="test_output.json")
    assert result["majors_count"] > 0
    assert result["local_file"] == "test_output.json"