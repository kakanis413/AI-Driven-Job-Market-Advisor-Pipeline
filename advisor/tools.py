"""Tools the data agent calls. Real lookups against the served data — no mocks.

Every tool returns a dict with an explicit `status`, so a miss is a fact the model can
report ("I don't have that major") rather than an invitation to invent one.
"""

from __future__ import annotations

import logging
from typing import Any

from advisor import data_source
from advisor.config import settings

log = logging.getLogger(__name__)


def get_major_data(major_name: str) -> dict[str, Any]:
    """Look up AI exposure, median pay, growth, and occupations for one college major.

    Args:
        major_name: Name of the college major, e.g. "Computer Science" or "Nursing".

    Returns:
        A dict with status="success" and the major's data, or status="not_found" with
        a list of close names when the major is not in the dataset.
    """
    row = data_source.find(major_name)
    if row is None:
        table = data_source.majors()
        key = major_name.lower().split()[0] if major_name.split() else ""
        near = [r["major"] for k, r in table.items() if key and key in k][:5]
        log.info("tool get_major_data: MISS for %r", major_name)
        return {
            "status": "not_found",
            "requested": major_name,
            "message": "That major is not in the dataset. Do not invent numbers for it.",
            "did_you_mean": near,
        }
    log.info("tool get_major_data: HIT for %r", major_name)
    return {"status": "success", "source": "data.json", **data_source.summarize(row)}


def compare_majors(major_a: str, major_b: str) -> dict[str, Any]:
    """Compare two college majors on AI exposure and median pay.

    Args:
        major_a: First major name.
        major_b: Second major name.

    Returns:
        A dict with both majors' data and which is more AI-exposed, or status="not_found"
        naming the major that is missing.
    """
    a, b = data_source.find(major_a), data_source.find(major_b)
    missing = [n for n, r in ((major_a, a), (major_b, b)) if r is None]
    if missing:
        log.info("tool compare_majors: MISS for %s", missing)
        return {
            "status": "not_found",
            "missing": missing,
            "message": "At least one major is not in the dataset. Do not invent its numbers.",
        }

    sa, sb = data_source.summarize(a), data_source.summarize(b)
    ea, eb = sa.get("exposure"), sb.get("exposure")
    if isinstance(ea, (int, float)) and isinstance(eb, (int, float)):
        more = sa["major"] if ea > eb else sb["major"] if eb > ea else "tied"
        delta = round(abs(ea - eb), 2)
    else:
        more, delta = "unknown", None
    log.info("tool compare_majors: %r vs %r", major_a, major_b)
    return {
        "status": "success",
        "source": "data.json",
        "major_a": sa,
        "major_b": sb,
        "more_exposed": more,
        "exposure_gap": delta,
    }


def build_bigquery_toolset() -> list[Any]:
    """Optional BigQuery grounding, off unless ADVISOR_ENABLE_BIGQUERY=true.

    Org IAM currently returns USER_PROJECT_DENIED for this project, so the service must
    run fine without it. Import is deliberately lazy: when the flag is off, the
    google-cloud-bigquery dependency is never touched.
    """
    if not settings.enable_bigquery:
        return []
    try:
        # 2.5.0: google.adk.tools.bigquery is deprecated -> use integrations.
        from google.adk.integrations.bigquery import (
            BigQueryCredentialsConfig,
            BigQueryToolset,
        )
        import google.auth

        creds, _ = google.auth.default()
        toolset = BigQueryToolset(
            credentials_config=BigQueryCredentialsConfig(credentials=creds)
        )
        log.info("BigQuery grounding ENABLED (dataset=%s)", settings.bigquery_dataset)
        return [toolset]
    except Exception as exc:  # pragma: no cover - depends on cloud IAM
        # Never let an optional grounding source take the service down.
        log.warning("BigQuery grounding requested but unavailable (%s); continuing without it", exc)
        return []
