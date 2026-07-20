"""Tools for the data agent: local lookups (fast, free) + BigQuery (flexible, dynamic SQL).

Local tools (get_major_data, compare_majors) use the in-memory data_source for instant lookups.
BigQuery toolset lets Gemini write SQL for complex queries the local data can't answer.
"""

from __future__ import annotations

import logging
from typing import Any

import google.auth
from google.adk.integrations.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.integrations.bigquery.config import BigQueryToolConfig, WriteMode

from advisor import data_source
from advisor.config import settings

log = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# BigQuery toolset (for complex/dynamic queries)
# -----------------------------------------------------------------------------
BQ_PROJECT = settings.project
BQ_DATASET = settings.bigquery_dataset

_credentials, _ = google.auth.default()
_credentials_config = BigQueryCredentialsConfig(credentials=_credentials)
_tool_config = BigQueryToolConfig(write_mode=WriteMode.BLOCKED)  # READ-ONLY

bigquery_toolset = BigQueryToolset(
    credentials_config=_credentials_config,
    bigquery_tool_config=_tool_config,
)

log.info("BigQuery toolset initialized (project=%s, dataset=%s)", BQ_PROJECT, BQ_DATASET)


# -----------------------------------------------------------------------------
# Local tools (fast, free, always available)
# -----------------------------------------------------------------------------
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
            "message": "That major is not in the local dataset. You may try BigQuery for more data.",
            "did_you_mean": near,
        }
    log.info("tool get_major_data: HIT for %r", major_name)
    return {"status": "success", "source": "local_cache", **data_source.summarize(row)}


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
            "message": "At least one major is not in the local dataset. Try BigQuery for more data.",
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
        "source": "local_cache",
        "major_a": sa,
        "major_b": sb,
        "more_exposed": more,
        "exposure_gap": delta,
    }
