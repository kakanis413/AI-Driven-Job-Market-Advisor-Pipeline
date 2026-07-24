# AI exposure — why it's low, and a Karpathy + Gemini rebuild

## 1. What we have today (as built)

The exposure score is computed **bottom-up** in four steps:

1. `batch/task_scoring.py` — Gemini scores each of ~17,618 O*NET **tasks** 0–10 against a rubric that asks *"how much can current generative AI assist with / accelerate this single task today."* (temperature 0, structured output — this part is solid engineering.)
2. `sql/rollup_pipeline.sql` averages upward:
   - task → O*NET occupation (importance-weighted mean)
   - O*NET occupation → SOC (equal-weight mean)
   - SOC → CIP4 major (equal-weight mean)
3. `data_pipeline.py` reads `major_ai_scores.major_exposure_score` (+ `major_ai_rationales`) into `public/data.json`.
4. The frontend colors tiles by that number.

The null-handling, coverage gates (≥50%, ≥3 SOCs), and approved-run gating are all **correct and worth keeping** — missing data stays missing, never zero.

## 2. Why most majors score low (measured, not guessed)

Current `data.json` (264 scored majors): **min 1.7 · max 6.9 · mean 5.28 · median 5.5 · stdev 1.05.** Histogram: 4→30, 5→65, 6→131, 7→17. Nothing reaches 8, 9, or 10. CS = 6.8.

Two compounding causes:

**a) Triple averaging compresses the distribution.** Three nested mean steps each regress toward the center. A major maps to many occupations/SOCs; averaging a 9 against a pile of 4s and 5s always lands near the middle. The result is a ceiling around 6.9 and a stdev of ~1 — it is mathematically impossible for any major to reach the 8–10 band, no matter how AI-exposed it truly is.

**b) The task rubric is conservative by construction.** "How much can gen AI *assist this task today*" is present-tense and task-scoped. Karpathy's rubric asks the opposite: *"how much will AI reshape this whole occupation"* (direct + indirect effects), with a strong prior that **fundamentally digital work = 7+** and an explicit "steep trajectory, high ceiling" framing. The present-tense task framing systematically produces lower numbers.

**c) Equal-weight SOC→major** dilutes a major's signature occupations with peripheral catch-all SOCs (a known artifact the SQL comments already flag).

## 3. How Karpathy built his (karpathy.ai/jobs, github.com/karpathy/jobs)

- Unit = **occupation** (342 BLS OOH occupations). Tile area = employment; color = a chosen metric.
- **LLM-powered coloring:** he scores *the displayed unit directly* — one LLM call per occupation, fed a rich BLS occupation description, against a heavily **anchored** rubric (0–1 roofer/diver … 4–5 nurse/police … 6–7 teacher/accountant … 8–9 software dev/designer/paralegal … 10 data-entry/telemarketer). Output: `{"exposure": 0-10, "rationale": "..."}`.
- **No aggregation.** Because each unit is scored as a whole, the full 0–10 spread survives.
- Same caveat we already enforce: a high score means the work is reshaped, not that the job disappears.

The full scoring prompt is reproduced on his page and in the repo — use it as the calibration reference.

## 4. The combination we want (Karpathy method + Gemini)

Keep majors as the display unit, but stop averaging up from tasks. Score the unit directly, Karpathy-style, with Gemini — in two layers:

### Layer A — Re-score occupations, Karpathy-style (Gemini)
Add a scoring path that scores each **occupation** (SOC / O*NET, ~hundreds–1k units) with one Gemini call, using Karpathy's occupation-level anchored rubric adapted to our data, fed a rich occupation description (O*NET/BLS summary + top tasks). Return `{exposure, rationale, confidence}`. This:
- fixes the occupation numbers with real spread (roofer ~1, software dev ~9, data-entry ~10),
- powers the occupation-level UI (HashTable rows, detail-card occupation bars),
- becomes the grounding for Layer B.

Version it as a new `scoring_run_id` + `prompt_version` + `rubric_version`; keep temperature 0 and the approved-run gate. This does **not** delete the task-level path — it's a parallel, occupation-grain run that becomes the new production truth once approved.

### Layer B — Score each major directly (Gemini), no roll-up collapse
For each of the ~360 majors, one Gemini call that rates the major 0–10 using a **major-adapted** version of Karpathy's anchored rubric. Ground it in: the major's name + CIP description, and its representative occupations with their Layer-A scores (and pay/growth). Prompt it to weigh the occupations a typical graduate actually enters, not a flat average, and to apply the digital-work prior. Return `{exposure, rationale}` → write `major_exposure_score` + the rationale (satisfies the app's "every score ships a rationale" rule). 360 calls is trivial cost.

This is the direct fix for the compression: each major is scored as a unit, so the 0–10 range is available again.

### If the team prefers to stay bottom-up (fallback)
If Layer B (direct major scoring) is rejected, at least change the roll-up to preserve spread:
- SOC→major: employment/relevance-weighted, not equal-weight.
- Use a **spread-preserving aggregate** instead of the mean — e.g. an employment-weighted mean of the top-K representative occupations, or a high percentile (p75) of the major's occupation scores, since a graduate can pursue the most-exposed roles. A plain mean will always regress to ~5.
Direct major scoring (Layer B) is still the recommended primary — a weighted mean helps but still compresses.

## 5. Guardrails (keep these — they're already right)
- Missing ≠ 0: unscored majors/occupations stay null; coverage/threshold gates remain.
- Temperature 0, structured JSON output, one rationale per score.
- Approved-run gating: score → review a sample → mark run approved → roll up / publish.
- Exposure ≠ job loss framing in every rationale and the pinned caveat.
- Tokens/data contract unchanged: `data.json` still emits `exposure` (0–10, one decimal or null) + `rationale`.

## 6. Validation — how we know it worked
After re-scoring, the distribution must **widen**, and it should broadly agree with Karpathy where units overlap:
- Stdev rises from ~1.0 toward ~2+; the 8–10 band becomes populated (CS/DS/SWE-feeding majors ~8–9; trades, nursing, physical majors ~2–4).
- Spot-check: CS ≈ 8–9 (was 6.8), Nursing ≈ 3–4, Data/Computer majors top the list, hands-on trades at the bottom.
- Cross-check overlapping SOCs against Karpathy's published occupation scores (his repo ships them) — they should be in the same ballpark.
- Sanity histogram + mean/median/stdev printout before and after, committed to the PR.

---

## Claude Code build prompt

Rebuild AI-exposure scoring to follow Karpathy's method (karpathy.ai/jobs, github.com/karpathy/jobs) using Gemini, because the current bottom-up task-averaging pipeline compresses every major into 2–7 (max 6.9, stdev 1.0) and can never reach the real 8–10 band. Do NOT remove the existing task-scoring path or the null/coverage/approved-run discipline — add a new, versioned scoring path alongside it.

Context to read first: `batch/task_scoring.py`, `batch/exposure_calc.py`, `sql/rollup_pipeline.sql`, `data_pipeline.py`, and the exposure section of `CLAUDE.md`. The current numbers: `public/data.json` exposure is mean 5.28 / max 6.9 / stdev 1.05 — the compression is the bug.

1. Occupation scoring (Karpathy-style, Gemini). Add `batch/occupation_scoring.py`: for each occupation (SOC/O*NET), one Gemini call (temperature 0, structured `{exposure: 0-10, rationale, confidence}`) using Karpathy's occupation-level anchored rubric — reproduce his anchor bands (0–1 physical/hands-on … 8–9 fully-digital knowledge work … 10 routine data entry) and his "fundamentally digital work → 7+, steep trajectory" prior. Feed each call a rich occupation description (O*NET summary + top tasks + title). Write to a new `occupation_ai_scores_v2` table under a new `scoring_run_id` + `prompt_version` + `rubric_version`. Keep the approved-run gate.

2. Major scoring (direct, Gemini — the compression fix). Add `batch/major_scoring.py`: for each of the ~360 majors, one Gemini call rating the major 0–10 with a major-adapted version of the same anchored rubric, grounded in the major's CIP description + its representative occupations and their Layer-1 scores (+ pay/growth). Instruct it to weigh the occupations a typical graduate enters (not a flat average) and apply the digital-work prior. Output `{exposure, rationale}`; write `major_exposure_score` + rationale to the majors scores/rationale tables `data_pipeline.py` reads. This replaces the roll-up as the source of the headline number.

3. Wiring + fallback. Point `data_pipeline.py` at the new major scores (keep null→None, no fabrication). Keep `sql/rollup_pipeline.sql` available as a cross-check; if the team rejects direct major scoring, instead change SOC→major to employment-weighted and use a p75 (or top-K weighted mean) aggregate rather than the mean — but direct scoring is the primary path.

4. Guardrails (unchanged): temperature 0, structured output, one rationale per score, missing≠0, coverage/approved-run gates, exposure≠job-loss framing in every rationale. Data contract in `data.json` unchanged (`exposure` 0–10 one-decimal-or-null + `rationale`).

5. Validation (commit the evidence). Add a small script/report that prints the exposure histogram + mean/median/stdev before vs after, and a spot-check table (CS, Data Science, Nursing, a trade, an arts major). Acceptance: stdev rises toward ~2+, the 8–10 band is populated, CS lands ~8–9, hands-on trades ~2–4, and overlapping SOCs are in the same ballpark as Karpathy's published occupation scores. Keep `pytest` green and the typecheck clean.
