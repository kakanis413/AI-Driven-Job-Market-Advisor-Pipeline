"""Tools for the data agent: local lookups (fast, free) + BigQuery (flexible, dynamic SQL).

Local tools (get_major_data, compare_majors, etc.) use the in-memory data_source
for instant lookups. BigQuery toolset lets Gemini write SQL for complex queries
the local data can't answer.
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


def get_median_pay(major_name: str) -> dict:
    """Look up median pay for a specific major.

    Returns an explicit status so a miss is a fact the model reports,
    not an invitation to invent a number.
    """
    major = data_source.find(major_name)
    if major is None:
        return {"status": "not_found", "major_name": major_name}

    pay = major.get("median_pay")
    if pay is None:
        return {"status": "no_data", "major_name": major_name}

    return {
        "status": "found",
        "major_name": major.get("major", major_name),
        "median_pay": pay,
    }


def get_ai_exposure(major_name: str) -> dict:
    """Look up the AI exposure score for a specific major."""
    major = data_source.find(major_name)
    if major is None:
        return {"status": "not_found", "major_name": major_name}

    exposure = major.get("exposure")
    if exposure is None:
        return {"status": "no_data", "major_name": major_name}

    return {
        "status": "found",
        "major_name": major.get("major", major_name),
        "exposure": exposure,
    }


def get_top_majors(metric: str = "median_pay", n: int = 3, order: str = "desc") -> dict:
    """Return the top N majors ranked by a given metric.

    Args:
        metric: one of "median_pay", "exposure", "graduates", "versatility"
        n: how many to return (default 3, matching the "top 3" ask)
        order: "desc" (highest first) or "asc" (lowest first)

    Returns explicit status + the ranked list.
    """
    valid_metrics = {"median_pay", "exposure", "graduates", "versatility"}
    if metric not in valid_metrics:
        return {"status": "invalid_metric", "metric": metric, "valid_metrics": sorted(valid_metrics)}

    table = data_source.majors()
    majors = list(table.values())

    # Only rank majors that actually have a non-null value for this metric
    ranked = [m for m in majors if m.get(metric) is not None]
    if not ranked:
        return {"status": "no_data", "metric": metric}

    ranked.sort(key=lambda m: m[metric], reverse=(order == "desc"))
    top_n = ranked[:n]

    return {
        "status": "found",
        "metric": metric,
        "order": order,
        "count": len(top_n),
        "majors": [
            {"major_name": m.get("major") or m.get("major_name"), metric: m.get(metric)}
            for m in top_n
        ],
    }