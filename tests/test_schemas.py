import pytest
from pydantic import ValidationError
from agent_config import MajorAnalysisSchema, OccupationInfo


def test_valid_schema_accepts_full_payload():
    data = MajorAnalysisSchema(
        major_name="Computer Science", exposure=8.4, median_pay=125831,
        growth="faster", occupations=[OccupationInfo(soc="15-1252", title="Software Developers", exposure=9.0)],
        query_context="Is this risky?",
    )
    assert data.exposure == 8.4


def test_missing_required_field_raises():
    with pytest.raises(ValidationError):
        MajorAnalysisSchema(major_name="History")  # missing exposure, median_pay, etc.


def test_exposure_wrong_type_raises():
    with pytest.raises(ValidationError):
        MajorAnalysisSchema(
            major_name="Art", exposure="very high",  # should be float, not string
            median_pay=50000, growth="average", occupations=[], query_context="?",
        )


def test_empty_occupations_list_is_valid():
    """occupations is a required list but an empty list should still be valid."""
    data = MajorAnalysisSchema(
        major_name="Undeclared", exposure=5.0, median_pay=50000,
        growth="average", occupations=[], query_context="What should I know?",
    )
    assert data.occupations == []


def test_null_growth_currently_fails_validation():
    """
    KNOWN MISMATCH: growth is currently a required str in agent_config.py,
    but the real data.json has growth: null for every major. Until the
    schema is loosened to `str | None`, every real request will 422 here.
    This test documents that gap rather than hiding it — if it starts
    failing (i.e. null growth becomes valid), update/remove this test.
    """
    with pytest.raises(ValidationError):
        MajorAnalysisSchema(
            major_name="Biology", exposure=5.8, median_pay=75024,
            growth=None, occupations=[], query_context="Career outlook?",
        )