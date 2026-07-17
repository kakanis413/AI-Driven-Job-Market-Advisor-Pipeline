"""Contract validation for the advisor request/response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from advisor.schemas import AdvisorRequest, OccupationInfo


def test_full_payload_ok():
    req = AdvisorRequest(
        major_name="Computer science", exposure=9.0, median_pay=99000, growth="faster",
        occupations=[OccupationInfo(soc="15-1252", title="Software developers", exposure=9.0)],
        query_context="Is this risky?",
    )
    assert req.exposure == 9.0
    assert req.occupations[0].title == "Software developers"


def test_growth_is_optional():
    # The real data.json has growth=null for every major — must not 422.
    req = AdvisorRequest(major_name="Nursing", query_context="Tell me about this")
    assert req.growth is None


def test_median_pay_optional_and_zero_becomes_unknown():
    # Frontend coerces null -> 0; we treat 0 as "unknown", never as a real $0 salary.
    req = AdvisorRequest(major_name="Art", median_pay=0, query_context="?")
    assert req.median_pay is None


def test_growth_placeholder_strings_normalize_to_none():
    for placeholder in ["not available", "N/A", "unknown", ""]:
        req = AdvisorRequest(major_name="X", growth=placeholder, query_context="?")
        assert req.growth is None, placeholder


def test_missing_question_raises():
    with pytest.raises(ValidationError):
        AdvisorRequest(major_name="History")  # no query_context


def test_blank_question_raises():
    with pytest.raises(ValidationError):
        AdvisorRequest(major_name="History", query_context="   ")


def test_exposure_out_of_range_raises():
    with pytest.raises(ValidationError):
        AdvisorRequest(major_name="X", exposure=42, query_context="?")


def test_grounding_block_marks_unknowns():
    req = AdvisorRequest(major_name="Mystery", query_context="?")
    block = req.grounding_block()
    assert "not available" in block
    assert "Mystery" in block
    # never fabricate a $0 or 0/10
    assert "$0" not in block


def test_grounding_block_includes_occupations():
    req = AdvisorRequest(
        major_name="Computer science", exposure=9.0, median_pay=99000,
        occupations=[OccupationInfo(title="Software developers", exposure=9.0)],
        query_context="?",
    )
    block = req.grounding_block()
    assert "Software developers" in block
    assert "$99,000" in block
    assert "9.0/10" in block
