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


# 2-digit CIP series → display family. Mirrors CIP_FAMILY in
# src/lib/normalizeMajors.ts so the advisor and the treemap bucket majors the
# same way. Rows that already carry a display family pass through untouched.
_CIP_FAMILY: dict[str, str] = {
    "01": "STEM", "03": "STEM", "04": "STEM", "11": "STEM", "14": "STEM",
    "15": "STEM", "26": "STEM", "27": "STEM", "40": "STEM", "41": "STEM",
    "52": "Business",
    "51": "Health", "31": "Health",
    "05": "Social sci", "13": "Social sci", "19": "Social sci", "22": "Social sci",
    "42": "Social sci", "43": "Social sci", "44": "Social sci", "45": "Social sci",
    "09": "Humanities", "16": "Humanities", "23": "Humanities", "24": "Humanities",
    "38": "Humanities", "39": "Humanities", "54": "Humanities",
    "50": "Arts",
    "10": "Trades", "12": "Trades", "46": "Trades", "47": "Trades",
    "48": "Trades", "49": "Trades",
    "25": "Other", "29": "Other", "30": "Other",
}


def _canonical(row: dict[str, Any]) -> dict[str, Any]:
    """Adapt a raw pipeline row to the shape the tools reason about.

    The pipeline emits `graduates` and a numeric CIP-series `family`; the tools
    (and the UI) speak `completions` and a display family. `exposure` stays None
    when the major hasn't been scored yet — never coerced to 0, which would read
    as "lowest exposure" instead of "not scored".
    """
    out = dict(row)
    if out.get("completions") is None:
        out["completions"] = row.get("graduates")
    fam = str(row.get("family") or "").strip()
    if fam in _CIP_FAMILY:
        out["family"] = _CIP_FAMILY[fam]
    exp = row.get("exposure")
    out["exposure"] = float(exp) if isinstance(exp, (int, float)) else None
    return out


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
            out[_normalize(row["major"])] = _canonical(row)
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
        # Among several real matches ("nursing" → practical vs registered), the
        # biggest program is the one a student almost certainly means.
        return max(hits, key=lambda r: r.get("completions") or 0)
    return None


def summarize(row: dict[str, Any]) -> dict[str, Any]:
    """Trim a data.json row to the fields the agent should reason about."""
    occs = row.get("occupations") or []
    out: dict[str, Any] = {
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
    # An unscored major must never be reported as a number. Say so explicitly so
    # the agent states "not scored yet" instead of implying the lowest score.
    if out["exposure"] is None:
        out["exposure_note"] = (
            "AI exposure has not been scored for this major yet — say so; do not state a number."
        )
    return out
