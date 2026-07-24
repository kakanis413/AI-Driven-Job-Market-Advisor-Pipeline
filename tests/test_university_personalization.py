"""University personalization: additive, non-blocking.

Covers the contract (schema accepts the three optional fields and still rejects
the same invalid inputs), the grounding block (UNIVERSITY CONTEXT + explicit
national-estimate note, with a not-found → national-only instruction), the cache
key (national requests keep the exact same key; a school folds in), and that a
compare-mode request reaches the agent with the domain-scoped routing instruction.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from advisor import runtime as rt
from advisor.runtime import _normalize_text
from advisor.schemas import AdvisorRequest, RouteInfo

WA = dict(
    university="University of Washington-Seattle Campus",
    university_domain="washington.edu",
    intended_major="Computer science",
)


# ---------------------------------------------------------------- schema

def test_schema_accepts_university_fields():
    r = AdvisorRequest(major_name="Computer science", query_context="How do I succeed?", **WA)
    assert r.university == "University of Washington-Seattle Campus"
    assert r.university_domain == "washington.edu"
    assert r.intended_major == "Computer science"
    assert r.is_university_compare is True


def test_is_compare_requires_both_name_and_domain():
    # name only, or domain only → not compare (national path)
    assert AdvisorRequest(major_name="X", query_context="?", university="Foo").is_university_compare is False
    assert AdvisorRequest(major_name="X", query_context="?", university_domain="foo.edu").is_university_compare is False
    assert AdvisorRequest(major_name="X", query_context="?").is_university_compare is False


def test_university_fields_do_not_relax_existing_validation():
    # exposure is still bounded 0-10 even with a school attached
    with pytest.raises(ValidationError):
        AdvisorRequest(major_name="X", exposure=42, query_context="?", **WA)
    # a blank question is still rejected
    with pytest.raises(ValidationError):
        AdvisorRequest(query_context="   ", **WA)


# ---------------------------------------------------------------- grounding block

def test_national_grounding_block_unchanged_without_school():
    r = AdvisorRequest(major_name="Computer science", exposure=9.0, median_pay=99000, query_context="?")
    block = r.grounding_block()
    assert "UNIVERSITY CONTEXT" not in block
    assert block.endswith("not available") or "occupations this major feeds into" in block


def test_compare_grounding_block_adds_context_and_national_note():
    r = AdvisorRequest(major_name="Computer science", exposure=9.0, median_pay=99000, query_context="?", **WA)
    block = r.grounding_block()
    assert "UNIVERSITY CONTEXT" in block
    assert "washington.edu" in block
    assert "site:washington.edu" in block
    # numbers are explicitly framed as national, and not-found degrades to national
    assert "NATIONAL" in block
    assert "national data only" in block.lower()
    assert "never invent" in block.lower()
    # the national portion is still present, unchanged
    assert "VERIFIED DATA FOR THIS MAJOR" in block


def test_compare_context_works_in_general_mode_too():
    r = AdvisorRequest(query_context="How do I succeed here?", **WA)
    block = r.grounding_block()
    assert "GENERAL MODE" in block
    assert "UNIVERSITY CONTEXT" in block


# ---------------------------------------------------------------- cache key

def _advise_and_capture(monkeypatch, req: AdvisorRequest) -> tuple[str, str]:
    """Run advise() with the LLM boundary faked; return (cache_key, prompt)."""
    rt.RESPONSE_CACHE.clear()
    captured: dict[str, str] = {}

    async def _fake_run(self, prompt):  # noqa: ANN001
        captured["prompt"] = prompt
        return "national answer", RouteInfo()

    monkeypatch.setattr(rt.AdvisorRuntime, "_run_with_retry", _fake_run)
    runtime = rt.AdvisorRuntime()
    asyncio.run(runtime.advise(req))
    key = next(iter(rt.RESPONSE_CACHE))
    return key, captured["prompt"]


def test_national_cache_key_is_exactly_today(monkeypatch):
    req = AdvisorRequest(major_name="Computer science", query_context="Is this risky?")
    key, _ = _advise_and_capture(monkeypatch, req)
    expected = f"{_normalize_text('Computer science')}:{_normalize_text('Is this risky?')}"
    assert key == expected  # no school suffix appended


def test_compare_cache_key_folds_in_school(monkeypatch):
    req = AdvisorRequest(major_name="Computer science", query_context="How do I succeed?", **WA)
    key, prompt = _advise_and_capture(monkeypatch, req)
    national = f"{_normalize_text('Computer science')}:{_normalize_text('How do I succeed?')}"
    assert key.startswith(national + ":")
    assert "washington" in key
    # the routing instruction (domain-scoped search + national note) reached the agent
    assert "site:washington.edu" in prompt
    assert "NATIONAL" in prompt


# ---------------------------------------------------------------- endpoint

def test_endpoint_accepts_university_fields(client, mock_agent_response):
    payload = {
        "major_name": "Computer Science",
        "exposure": 8.4,
        "median_pay": 125831,
        "growth": "faster",
        "occupations": [{"soc": "15-1252", "title": "Software Developers", "exposure": 9.0}],
        "query_context": "How do I succeed here?",
        **WA,
    }
    resp = client.post("/api/v1/analyze-major", json=payload)
    assert resp.status_code == 200
    assert resp.json()["generated_guidance"] == mock_agent_response
