"""
batch/exposure_validation.py

The "how we know it worked" report for the Karpathy-style exposure rebuild
(EXPOSURE_REBUILD_PLAN.md §6). Prints, side by side:

  * the OLD rollup distribution (major_ai_scores, v1) vs the NEW direct-scored
    distribution (major_ai_scores_v2) — count, coverage, min/max/mean/median/
    stdev, and a 0-10 histogram;
  * a spot-check table for the acceptance majors (CS, Data Science, Nursing, a
    trade, an arts major);
  * an occupation cross-check of Layer-A scores against Karpathy's published
    anchor points, so anyone can see the occupation numbers land in the same
    ballpark as karpathy.ai/jobs.

Read-only. Safe to re-run. Nothing here writes to BigQuery.

    python -m batch.exposure_validation
"""

import statistics
from collections import Counter

from dotenv import load_dotenv

load_dotenv()

from google.cloud import bigquery

GCP_PROJECT = "sprinternship-sea-2026"
PROJECT_DATASET = f"{GCP_PROJECT}.majors"
bq = bigquery.Client(project=GCP_PROJECT)


def _fetch(sql: str) -> list[dict]:
    return [dict(r) for r in bq.query(sql).result()]


def _describe(scores: list[float], label: str) -> None:
    if not scores:
        print(f"{label}: no scores")
        return
    hist = dict(sorted(Counter(int(x) for x in scores).items()))
    bar = "  ".join(f"{k}:{v}" for k, v in hist.items())
    print(
        f"{label:>10}  n={len(scores):<4} "
        f"min={min(scores):<4} max={max(scores):<4} "
        f"mean={statistics.mean(scores):.2f} median={statistics.median(scores):.1f} "
        f"stdev={statistics.pstdev(scores):.2f}"
    )
    print(f"            hist  {bar}")


def distribution_before_after() -> None:
    print("=" * 72)
    print("MAJOR EXPOSURE — distribution before (rollup v1) vs after (direct v2)")
    print("=" * 72)
    v1 = [r["s"] for r in _fetch(
        f"SELECT major_exposure_score s FROM `{PROJECT_DATASET}.major_ai_scores` "
        "WHERE major_exposure_score IS NOT NULL")]
    v2 = [r["s"] for r in _fetch(
        f"SELECT major_exposure_score s FROM `{PROJECT_DATASET}.major_ai_scores_v2` "
        "WHERE scoring_status='scored'")]
    _describe(v1, "BEFORE v1")
    _describe(v2, "AFTER v2")
    print(f"\n  coverage: v1 scored {len(v1)} majors, v2 scored {len(v2)} majors")
    print(f"  ceiling:  v1 max {max(v1):.1f}  ->  v2 max {max(v2):.1f}")
    print(f"  spread:   v1 stdev {statistics.pstdev(v1):.2f}  ->  "
          f"v2 stdev {statistics.pstdev(v2):.2f}")


def spot_check_majors() -> None:
    print("\n" + "=" * 72)
    print("SPOT-CHECK MAJORS  (v1 rollup  ->  v2 direct)")
    print("=" * 72)
    rows = _fetch(f"""
        SELECT v2.major_name, v2.major_exposure_score AS v2s, v1.major_exposure_score AS v1s
        FROM `{PROJECT_DATASET}.major_ai_scores_v2` v2
        LEFT JOIN `{PROJECT_DATASET}.major_ai_scores` v1 USING (cip4_code)
        WHERE v2.scoring_status='scored'
    """)
    wanted = ["Computer Science", "Data Science", "Registered Nursing",
              "Woodworking", "Fine and Studio Arts", "Culinary"]
    for w in wanted:
        wl = w.lower()
        # Prefer an exact name, then a prefix, then any substring — so
        # "Computer Science" resolves to CS itself, not "Accounting and
        # Computer Science".
        exact = [r for r in rows if (r["major_name"] or "").lower() == wl]
        prefix = [r for r in rows if (r["major_name"] or "").lower().startswith(wl)]
        contains = [r for r in rows if wl in (r["major_name"] or "").lower()]
        m = (exact or prefix or contains or [None])[0]
        if m:
            v1 = f"{m['v1s']:.1f}" if m["v1s"] is not None else "null"
            print(f"  {m['v2s']:>4}  (was {v1:>4})   {m['major_name'][:48]}")


def occupation_cross_check() -> None:
    # Karpathy's published anchor points (karpathy.ai/jobs) for occupations we
    # also score. Not a strict equality test — a ballpark agreement check.
    print("\n" + "=" * 72)
    print("OCCUPATION CROSS-CHECK vs Karpathy anchors  (Layer A)")
    print("=" * 72)
    anchors = {
        "15-1252": ("Software Developers", "8-9"),
        "15-2051": ("Data Scientists", "8-9"),
        "23-2011": ("Paralegals", "8-9"),
        "27-1024": ("Graphic Designers", "8-9"),
        "43-9021": ("Data Entry Keyers", "10"),
        "29-1141": ("Registered Nurses", "4-5"),
        "47-2181": ("Roofers", "0-1"),
    }
    rows = {r["soc_code"]: r["s"] for r in _fetch(
        f"SELECT soc_code, occupation_exposure_score s "
        f"FROM `{PROJECT_DATASET}.occupation_ai_scores_v2` WHERE scoring_status='scored'")}
    print(f"  {'SOC':<9} {'occupation':<22} {'ours':>5}   karpathy-band")
    for soc, (title, band) in anchors.items():
        ours = rows.get(soc)
        got = f"{ours:.1f}" if ours is not None else "n/a"
        print(f"  {soc:<9} {title:<22} {got:>5}   {band}")


def acceptance_summary() -> None:
    print("\n" + "=" * 72)
    print("ACCEPTANCE (EXPOSURE_REBUILD_PLAN.md §6)")
    print("=" * 72)
    v2 = [r["s"] for r in _fetch(
        f"SELECT major_exposure_score s FROM `{PROJECT_DATASET}.major_ai_scores_v2` "
        "WHERE scoring_status='scored'")]
    total = _fetch(f"SELECT COUNT(*) n FROM `{PROJECT_DATASET}.major_ai_scores_v2`")[0]["n"]
    in_8_10 = sum(1 for x in v2 if x >= 8)
    checks = [
        ("8-10 band populated", in_8_10 > 0, f"{in_8_10} majors >= 8.0"),
        ("stdev widened from ~1.05", statistics.pstdev(v2) > 1.05,
         f"stdev now {statistics.pstdev(v2):.2f}"),
        ("ceiling above old 6.9", max(v2) > 6.9, f"max now {max(v2):.1f}"),
        ("all majors scored (goal)", len(v2) == total, f"{len(v2)}/{total} scored"),
    ]
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'CHECK'}] {name:<28} {detail}")


if __name__ == "__main__":
    distribution_before_after()
    spot_check_majors()
    occupation_cross_check()
    acceptance_summary()
