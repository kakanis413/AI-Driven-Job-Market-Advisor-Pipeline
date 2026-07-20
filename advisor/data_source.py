"""In-memory lookup over the same data.json the browser renders.

Grounding on the exact file the user is looking at means the UI and the advisor can never
disagree, and costs zero per request. Loaded once, lazily; a refresh needs a restart
(or `reload()`), which is the documented tradeoff.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from advisor.config import settings

log = logging.getLogger(__name__)

_MAJORS: dict[str, dict[str, Any]] | None = None


def _normalize(name: str) -> str:
    return " ".join(name.lower().replace("-", " ").replace(",", " ").split())


def _load(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        log.warning("data file not found at %s; major lookup will be empty", path)
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read data file %s: %s", path, exc)
        return {}
    if not isinstance(raw, list):
        log.warning("data file %s is not a list of majors", path)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in raw:
        if isinstance(row, dict) and isinstance(row.get("major"), str):
            out[_normalize(row["major"])] = row
    log.info("loaded %d majors from %s", len(out), path)
    return out


def majors() -> dict[str, dict[str, Any]]:
    global _MAJORS
    if _MAJORS is None:
        _MAJORS = _load(settings.data_file)
    return _MAJORS


def reload() -> int:
    global _MAJORS
    _MAJORS = _load(settings.data_file)
    return len(_MAJORS)


def find(major_name: str) -> dict[str, Any] | None:
    """Exact match, then substring — tolerant of the model paraphrasing a major name."""
    table = majors()
    if not table:
        return None
    key = _normalize(major_name)
    if key in table:
        return table[key]
    hits = [v for k, v in table.items() if key in k or k in key]
    if hits:
        # Prefer the closest by length so "Nursing" doesn't match a 60-char cousin first.
        return min(hits, key=lambda r: len(r.get("major", "")))
    return None


def summarize(row: dict[str, Any]) -> dict[str, Any]:
    """Trim a data.json row to the fields the agent should reason about."""
    occs = row.get("occupations") or []
    return {
        "major": row.get("major"),
        "cip": row.get("cip"),
        "family": row.get("family"),
        "exposure": row.get("exposure"),
        "median_pay": row.get("median_pay"),
        "growth": row.get("growth") or "not available",
        "completions": row.get("completions"),
        "occupations": [
            {"title": o.get("title"), "exposure": o.get("exposure")}
            for o in occs[:10]
            if isinstance(o, dict)
        ],
    }
