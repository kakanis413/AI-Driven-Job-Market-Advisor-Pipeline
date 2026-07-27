"""Single source of truth for model, project, and feature flags.

Secrets are never read from here - auth is ADC only (GOOGLE_APPLICATION_CREDENTIALS /
`gcloud auth application-default login`). This module only reads non-secret config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, resolved from the environment at import time."""

    model: str = os.getenv("ADVISOR_MODEL", "gemini-3.5-flash")
    app_name: str = "college_advisor"

    # --- Vertex / ADC ---
    use_vertex: bool = _env_bool("GOOGLE_GENAI_USE_VERTEXAI", True)
    project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "sprinternship-sea-2026")
    # Defaulting location to 'global' for Gemini 3.5 & Search Grounding compatibility
    location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

    # --- BigQuery ---
    bigquery_dataset: str = os.getenv("BQ_DATASET", "majors")
    # Hard ceiling on bytes billed per query. Gemini writes this SQL, so the ceiling
    # is what stops a malformed or pathological join from running away — BigQuery
    # kills the job rather than billing for it.
    #
    # 256 MB is deliberate, not arbitrary: the whole `majors` dataset measures 128 MB
    # across 40 tables (largest: onet_work_context_complete_fixed at 57 MB). No
    # legitimate query can need more than the dataset itself, and 2x leaves room for
    # a self-join that reads the same table twice. Raise it only if the warehouse
    # grows; a query that hits this ceiling is a bug, not a big question.
    bigquery_max_bytes_billed: int = int(
        os.getenv("ADVISOR_BQ_MAX_BYTES_BILLED", str(256 * 1024 * 1024))
    )

    # --- data file for local lookups ---
    # The SAME file the browser renders. Grounding the advisor on the exact data
    # the user is looking at is the invariant in HANDOFF.md — a separate copy
    # under advisor/data/ silently drifted (flat 5.0 + seeded demo rows) and made
    # the chat contradict the tiles. One file, one truth. Override per-deployment
    # (or in tests) with ADVISOR_DATA_FILE.
    data_file: Path = Path(
        os.getenv("ADVISOR_DATA_FILE", str(REPO_ROOT / "public" / "data.json"))
    )

    # --- latency ---
    # The single largest lever on time-to-first-token. Gemini 3.x thinks before it
    # writes, and that thinking lands entirely in front of the first token:
    # measured on this prompt, default thinking = 8.2s TTFT / 8.9s total, versus
    # MINIMAL = 0.8s / 2.4s. The root agent's job is to read a grounding block it
    # was handed, pick at most one tool, and write three paragraphs — none of which
    # needs an extended reasoning budget. Raise to "LOW"/"STANDARD" via
    # ADVISOR_THINKING_LEVEL if answer quality regresses on harder questions.
    thinking_level: str = os.getenv("ADVISOR_THINKING_LEVEL", "MINIMAL")

    # --- reliability ---
    # 30s, not 90s: with max_retries=2 and exponential backoff a stuck request at
    # 90s hangs ~4.5 min before the client sees anything. At 30s the worst case is
    # ~95s, and p95 for a real answer is ~10s — so 30s only ever cuts off hangs.
    request_timeout_s: float = _env_float("ADVISOR_TIMEOUT_S", 30.0)
    max_retries: int = int(os.getenv("ADVISOR_MAX_RETRIES", "2"))
    retry_base_delay_s: float = _env_float("ADVISOR_RETRY_BASE_DELAY_S", 0.5)

    # --- news feed cache (GET /api/v1/news) ---
    news_ttl_s: float = _env_float("ADVISOR_NEWS_TTL_S", 6 * 3600.0)

    # --- web ---
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list(
            "ADVISOR_CORS_ORIGINS",
            [
                "http://localhost:5173", "http://127.0.0.1:5173",
                "http://localhost:5174", "http://127.0.0.1:5174",
                "http://localhost:5175", "http://127.0.0.1:5175",
                "http://localhost:5176", "http://127.0.0.1:5176",
                "http://localhost:5177", "http://127.0.0.1:5177",
                "http://localhost:5178", "http://127.0.0.1:5178",
                "http://localhost:4173",
            ],
        )
    )
    log_level: str = os.getenv("ADVISOR_LOG_LEVEL", "INFO")

    # --- access control ---
    # Both OFF by default so local dev and the existing frontend are unchanged.
    # Set them in any deployment the public internet can reach: every advisor request
    # spends a Gemini call (and sometimes a BigQuery scan), so an open endpoint is an
    # open budget. Neither replaces putting real auth in front of Cloud Run — they are
    # the floor, not the ceiling.
    #
    # Shared key: when set, requests must send `X-API-Key: <key>`.
    api_key: str = os.getenv("ADVISOR_API_KEY", "")
    # Requests per client per minute; 0 disables. In-process, so the effective limit
    # is this times the instance count — a real limiter belongs at the edge.
    rate_limit_per_min: int = int(os.getenv("ADVISOR_RATE_LIMIT_PER_MIN", "0"))


settings = Settings()


def apply_vertex_env() -> None:
    """Push Vertex settings into the env vars google-genai reads.

    Called at startup so the ADK client picks up project/location even when the process
    was launched without a .env file.
    """
    # Force environmental variables so google-genai & ADK override defaults cleanly
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true" if settings.use_vertex else "false"
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.project
    os.environ["GOOGLE_CLOUD_LOCATION"] = settings.location