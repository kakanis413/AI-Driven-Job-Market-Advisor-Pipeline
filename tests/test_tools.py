"""The real lookup tools — no mock, no CS-for-everything bug."""

from __future__ import annotations

from advisor import data_source
from advisor.tools import compare_majors, get_major_data


def test_data_source_loads_fixture():
    table = data_source.majors()
    assert len(table) >= 10
    assert data_source.find("Computer science") is not None


def test_find_is_case_and_punctuation_insensitive():
    a = data_source.find("computer science")
    b = data_source.find("Computer Science")
    assert a is not None and b is not None
    assert a["major"] == b["major"]


def test_get_major_data_hit_returns_real_numbers():
    out = get_major_data("Computer science")
    assert out["status"] == "success"
    # The in-memory tool cache (DYNAMIC_TOP_CAREERS_SPEC §3) renamed the source;
    # what matters is that a hit declares where the numbers came from.
    assert out["source"] == "local_cache"
    assert out["major"].lower().startswith("computer")
    assert isinstance(out["exposure"], (int, float))
    assert out["occupations"]  # real occupations, not empty


def test_get_major_data_miss_does_not_invent():
    out = get_major_data("Underwater Basket Weaving")
    assert out["status"] == "not_found"
    # The point is that a miss is reported as a fact, not filled in. Assert the
    # behaviour, not the phrasing — matching exact wording is what made this test
    # fail on a copy edit that changed nothing about what the tool does.
    msg = out["message"].lower()
    assert "not in the" in msg and "dataset" in msg
    assert "exposure" not in out  # no fabricated number
    # A miss must not send the model after a data source that no longer exists.
    assert "bigquery" not in msg


def test_get_major_data_is_not_hardcoded_cs():
    # The old mock returned Computer Science for every input. Guard against regression.
    bio = get_major_data("Biology")
    cs = get_major_data("Computer science")
    assert bio["status"] == "success" and cs["status"] == "success"
    assert bio["major"] != cs["major"]
    assert bio["exposure"] != cs["exposure"]


def test_compare_majors_ranks_by_exposure():
    out = compare_majors("Computer science", "Biology")
    assert out["status"] == "success"
    assert out["more_exposed"].lower().startswith("computer")
    assert out["exposure_gap"] > 0


def test_compare_majors_missing_flags_it():
    out = compare_majors("Computer science", "Nonexistent Major")
    assert out["status"] == "not_found"
    assert "Nonexistent Major" in out["missing"]
