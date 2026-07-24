"""Tools for the data agent: local lookups (fast, free) + BigQuery (flexible, dynamic SQL).

Local tools (get_major_data, compare_majors, etc.) use the in-memory data_source
for instant lookups. BigQuery toolset lets Gemini write SQL for complex queries
the local data can't answer.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import google.auth
from google.adk.integrations.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.integrations.bigquery.config import BigQueryToolConfig, WriteMode
from google.cloud import bigquery

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
@lru_cache(maxsize=128)
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


@lru_cache(maxsize=128)
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


@lru_cache(maxsize=128)
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


@lru_cache(maxsize=128)
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


@lru_cache(maxsize=32)
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


# -----------------------------------------------------------------------------
# Dynamic Real-Time Career Blending Tool
# -----------------------------------------------------------------------------
@lru_cache(maxsize=128)
def get_dynamic_top_careers(
    major_name: str,
    n: int = 3,
) -> dict[str, Any]:
    """Return the top occupations for a major using a deterministic score.

    Ranking:
    - 50% median-pay percentile
    - 30% growth percentile
    - 20% balanced AI exposure

    Exposure values from 4.0 through 8.0 receive the full AI-balance score.
    """

    major = data_source.find(major_name)
    if major is None:
        return {
            "status": "not_found",
            "major": major_name,
            "message": "The major was not found in the local dataset.",
        }

    cip = major.get("cip")
    if not cip:
        return {
            "status": "no_data",
            "major": major.get("major", major_name),
            "message": "This major does not have a CIP code for occupation matching.",
        }

    limit = max(1, min(int(n), 10))

    query = f"""
    WITH

    -- Deduplicate major-to-occupation mappings.
    crosswalk AS (
      SELECT
        cip4_code,
        soc_code,
        ARRAY_AGG(
          occupation_name IGNORE NULLS
          ORDER BY relationship_weight DESC
          LIMIT 1
        )[SAFE_OFFSET(0)] AS occupation_name,
        MAX(relationship_weight) AS relationship_weight
      FROM `{BQ_PROJECT}.{BQ_DATASET}.cip4_to_soc_crosswalk_clean`
      WHERE soc_code IS NOT NULL
      GROUP BY cip4_code, soc_code
    ),

    -- Use the latest occupation exposure result for the approved v2 run.
    exposure_scores AS (
      SELECT
        soc_code,
        occupation_title,
        occupation_exposure_score
      FROM `{BQ_PROJECT}.{BQ_DATASET}.occupation_ai_scores_v2`
      WHERE scoring_run_id = 'occupation_karpathy_v2'
        AND scoring_status = 'scored'
        AND occupation_exposure_score IS NOT NULL
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY soc_code
        ORDER BY scored_at DESC
      ) = 1
    ),

    -- Gather occupation-level metrics across all crosswalk occupations.
    occupation_metrics AS (
      SELECT
        soc.soc_code,
        COALESCE(
          exposure.occupation_title,
          occupations.occupation_title,
          oews.occupation_title
        ) AS occupation_title,
        oews.median_wage_annual,
        occupations.outlook_pct,
        occupations.employment_2024,
        exposure.occupation_exposure_score
      FROM (
        SELECT DISTINCT soc_code
        FROM crosswalk
      ) AS soc
      LEFT JOIN `{BQ_PROJECT}.{BQ_DATASET}.occupations_oews_clean` AS oews
        ON soc.soc_code = oews.soc_code
      LEFT JOIN `{BQ_PROJECT}.{BQ_DATASET}.dim_occupations` AS occupations
        ON soc.soc_code = occupations.soc_code
      LEFT JOIN exposure_scores AS exposure
        ON soc.soc_code = exposure.soc_code
    ),

    -- Normalize pay and growth globally across occupations.
    normalized_metrics AS (
      SELECT
        *,
        PERCENT_RANK() OVER (
          ORDER BY median_wage_annual
        ) AS pay_score,
        PERCENT_RANK() OVER (
          ORDER BY outlook_pct
        ) AS growth_score
      FROM occupation_metrics
      WHERE median_wage_annual IS NOT NULL
        AND outlook_pct IS NOT NULL
        AND occupation_exposure_score IS NOT NULL
    ),

    -- Restrict ranking to the 20 most relevant occupations for this major.
    relevant_candidates AS (
      SELECT
        crosswalk.cip4_code,
        crosswalk.soc_code,
        crosswalk.occupation_name,
        crosswalk.relationship_weight,
        occupations.employment_2024,
        ROW_NUMBER() OVER (
          ORDER BY
            crosswalk.relationship_weight DESC,
            occupations.employment_2024 DESC NULLS LAST,
            crosswalk.soc_code
        ) AS relevance_rank
      FROM crosswalk
      LEFT JOIN `{BQ_PROJECT}.{BQ_DATASET}.dim_occupations` AS occupations
        ON crosswalk.soc_code = occupations.soc_code
      WHERE crosswalk.cip4_code = @cip
    ),

    scored_candidates AS (
      SELECT
        candidate.soc_code,
        COALESCE(
          metrics.occupation_title,
          candidate.occupation_name
        ) AS occupation_title,
        candidate.relationship_weight,
        metrics.median_wage_annual,
        metrics.outlook_pct,
        metrics.occupation_exposure_score,
        metrics.pay_score,
        metrics.growth_score,

        CASE
          WHEN metrics.occupation_exposure_score BETWEEN 4.0 AND 8.0
            THEN 1.0
          WHEN metrics.occupation_exposure_score < 4.0
            THEN GREATEST(
              0.0,
              metrics.occupation_exposure_score / 4.0
            )
          ELSE GREATEST(
            0.0,
            (10.0 - metrics.occupation_exposure_score) / 2.0
          )
        END AS ai_balance_score

      FROM relevant_candidates AS candidate
      JOIN normalized_metrics AS metrics
        ON candidate.soc_code = metrics.soc_code
      WHERE candidate.relevance_rank <= 20
    ),

    final_scores AS (
      SELECT
        *,
        ROUND(
          100 * (
            0.50 * pay_score
            + 0.30 * growth_score
            + 0.20 * ai_balance_score
          ),
          1
        ) AS career_score
      FROM scored_candidates
    )

    SELECT
      soc_code,
      occupation_title,
      median_wage_annual,
      outlook_pct,
      occupation_exposure_score,
      ROUND(pay_score, 4) AS pay_score,
      ROUND(growth_score, 4) AS growth_score,
      ROUND(ai_balance_score, 4) AS ai_balance_score,
      career_score,
      relationship_weight
    FROM final_scores
    ORDER BY
      career_score DESC,
      relationship_weight DESC,
      soc_code
    LIMIT @limit
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("cip", "STRING", str(cip)),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )

    try:
        rows = list(
            _career_query_client()
            .query(query, job_config=job_config)
            .result()
        )
    except Exception as exc:
        log.exception(
            "Top-career query failed for major=%r cip=%r",
            major_name,
            cip,
        )
        return {
            "status": "unavailable",
            "major": major.get("major", major_name),
            "message": "Career ranking data is temporarily unavailable.",
            "error_type": type(exc).__name__,
        }

    careers = [
        {
            "rank": index,
            "soc": row["soc_code"],
            "title": row["occupation_title"],
            "median_pay": row["median_wage_annual"],
            "growth": row["outlook_pct"],
            "ai_exposure": row["occupation_exposure_score"],
            "pay_score": row["pay_score"],
            "growth_score": row["growth_score"],
            "ai_balance_score": row["ai_balance_score"],
            "career_score": row["career_score"],
        }
        for index, row in enumerate(rows, start=1)
    ]

    return {
        "status": "success" if len(careers) == limit else "partial",
        "major": major.get("major", major_name),
        "cip": cip,
        "method": {
            "median_pay_weight": 0.50,
            "growth_weight": 0.30,
            "ai_balance_weight": 0.20,
            "preferred_ai_exposure_range": [4.0, 8.0],
            "candidate_relevance_limit": 20,
        },
        "count": len(careers),
        "careers": careers,
    }


@lru_cache(maxsize=1)
def _career_query_client() -> bigquery.Client:
    return bigquery.Client(project=BQ_PROJECT)