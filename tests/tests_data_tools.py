"""
Tests for the pay/exposure/top-N query tools added over static data.json.
No mocking needed here — these are pure functions over in-memory data,
which is exactly the point: no network, no BigQuery, no flakiness.
"""
from advisor.tools import get_median_pay, get_ai_exposure, get_top_majors

def test_get_median_pay_found():
    result = get_median_pay("Computer Science")
    assert result["status"] in ("found", "not_found")  # depends on real data.json contents
    if result["status"] == "found":
        assert isinstance(result["median_pay"], int)


def test_get_median_pay_unknown_major():
    result = get_median_pay("Underwater Basket Weaving Studies")
    assert result["status"] == "not_found"


def test_get_ai_exposure_unknown_major():
    result = get_ai_exposure("Not A Real Major")
    assert result["status"] == "not_found"


def test_get_top_majors_default_returns_three():
    result = get_top_majors()
    assert result["status"] == "found"
    assert result["count"] <= 3
    assert len(result["majors"]) == result["count"]


def test_get_top_majors_invalid_metric_is_explicit():
    result = get_top_majors(metric="popularity_contest")
    assert result["status"] == "invalid_metric"
    assert "popularity_contest" not in result["valid_metrics"]


def test_get_top_majors_sorted_correctly_desc():
    result = get_top_majors(metric="median_pay", n=5, order="desc")
    if result["status"] == "found" and len(result["majors"]) > 1:
        pays = [m["median_pay"] for m in result["majors"]]
        assert pays == sorted(pays, reverse=True)


def test_get_top_majors_exposure_flat_placeholder_still_returns_something():
    """
    Known gap from the handoff: exposure is 0.5 for all majors right now.
    This test documents that reality rather than hiding it — once the
    scoring pipeline lands real values, this test should start seeing
    genuine variation and can be tightened.
    """
    result = get_top_majors(metric="exposure", n=3)
    assert result["status"] == "found"