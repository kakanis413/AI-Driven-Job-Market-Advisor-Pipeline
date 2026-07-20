"""Single source of truth for model, project, and feature flags.

Secrets are never read from here — auth is ADC only (GOOGLE_APPLICATION_CREDENTIALS /
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
    location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

    # --- routing / reliability ---
    # Primary path is multi-agent; the single agent is the safety net.
    enable_multi_agent: bool = _env_bool("ADVISOR_ENABLE_MULTI_AGENT", True)
    enable_fallback: bool = _env_bool("ADVISOR_ENABLE_FALLBACK", True)
    request_timeout_s: float = _env_float("ADVISOR_TIMEOUT_S", 90.0)
    max_retries: int = int(os.getenv("ADVISOR_MAX_RETRIES", "2"))
    retry_base_delay_s: float = _env_float("ADVISOR_RETRY_BASE_DELAY_S", 0.5)

    # --- optional grounding sources ---
    # BigQuery is OFF by default: org IAM returns USER_PROJECT_DENIED for this project.
    # See WEBSITE_INTEGRATION.md for the roles needed to turn it on.
    enable_bigquery: bool = _env_bool("ADVISOR_ENABLE_BIGQUERY", False)
    enable_news: bool = _env_bool("ADVISOR_ENABLE_NEWS", True)
    bigquery_dataset: str = os.getenv("ADVISOR_BQ_DATASET", "major_visualizer")

    # --- web ---
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list(
            "ADVISOR_CORS_ORIGINS",
            ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"],
        )
    )
    # Rich Major[] data (cip/exposure/occupations) for the in-memory lookup tool.
    # public/data.json currently holds the *normalized* pipeline output (no occupations),
    # so we default to the committed rich snapshot; override with ADVISOR_DATA_FILE once
    # the pipeline emits rich data to public/. Primary grounding is request-passed either way.
    data_file: Path = Path(
        os.getenv("ADVISOR_DATA_FILE", str(REPO_ROOT / "advisor" / "data" / "majors.json"))
    )
    log_level: str = os.getenv("ADVISOR_LOG_LEVEL", "INFO")


settings = Settings()


def apply_vertex_env() -> None:
    """Push Vertex settings into the env vars google-genai reads.

    Called at startup so the ADK client picks up project/location even when the process
    was launched without a .env file.
    """
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE" if settings.use_vertex else "FALSE")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.project)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.location)
