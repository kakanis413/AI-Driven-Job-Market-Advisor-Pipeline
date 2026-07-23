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

    # --- data file for local lookups ---
    # The SAME file the browser renders. Grounding the advisor on the exact data
    # the user is looking at is the invariant in HANDOFF.md — a separate copy
    # under advisor/data/ silently drifted (flat 5.0 + seeded demo rows) and made
    # the chat contradict the tiles. One file, one truth. Override per-deployment
    # (or in tests) with ADVISOR_DATA_FILE.
    data_file: Path = Path(
        os.getenv("ADVISOR_DATA_FILE", str(REPO_ROOT / "public" / "data.json"))
    )

    # --- reliability ---
    request_timeout_s: float = _env_float("ADVISOR_TIMEOUT_S", 90.0)
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