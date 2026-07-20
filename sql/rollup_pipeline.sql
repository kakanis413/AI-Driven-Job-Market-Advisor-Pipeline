-- rollup_pipeline.sql
--
-- WHY THIS FILE EXISTS:
-- task_scoring.py produces exactly one number per (task, O*NET occupation)
-- pair -- but nothing downstream ever reads a task-level score directly.
-- The treemap needs one number per MAJOR. The hover card needs one number
-- per OCCUPATION. This file is the bridge between those two worlds: three
-- separate averaging steps, each collapsing one level of the hierarchy:
--
--   task_ai_scores  -->  onet_occupation_ai_scores  -->  soc_ai_scores  -->  major_ai_scores
--   (17,618 rows,           (one row per O*NET           (one row per      (one row per
--    one per task)           occupation)                  SOC code)         CIP4 major)
--
-- WHY THREE STEPS AND NOT ONE:
-- each arrow above is a genuinely different one-to-many relationship with
-- its own weighting rule (see methodology doc):
--   - task -> O*NET occupation: importance-WEIGHTED (some tasks matter
--     more to a job than others)
--   - O*NET occupation -> SOC: equal-weighted (no real reason to prefer
--     one O*NET variant of a SOC over another)
--   - SOC -> major: equal-weighted (the crosswalk has no real employment-
--     share data, so equal weight is the honest choice, not a shortcut)
-- Collapsing these into one query would silently blend three different
-- weighting rules into one, which is exactly the kind of distortion the
-- methodology doc's per-level rules exist to prevent.
--
-- WHY THIS IS SQL AND NOT AN AGENT:
-- every number here already exists (produced by the LLM scoring agent
-- upstream) -- this file only ever averages, excludes missing values, and
-- renormalizes. No judgment is being made anywhere in this file. That's a
-- deliberate choice: deterministic, auditable, free to re-run, versus an
-- LLM re-deriving the same arithmetic on every run at a cost and with no
-- guarantee of reproducing the exact same result twice.
--
-- IMPORTANT: column/table names below are inferred from the BigQuery
-- handoff doc's descriptions, not a verified schema dump. Check these
-- against the real tables before running:
--   bq show --schema --format=prettyjson <project>:<dataset>.onet_task_ratings_clean
--   bq show --schema --format=prettyjson <project>:<dataset>.soc_onet_mapping_clean
--   bq show --schema --format=prettyjson <project>:<dataset>.cip4_to_soc_crosswalk_clean
--   bq show --schema --format=prettyjson <project>:<dataset>.ai_scoring_runs
-- (task_ai_scores column names below ARE verified, as of 2026-07-16.)
--
-- Project/dataset is sprinternship-sea-2026.majors throughout this file.

-- Every downstream step needs to know WHICH scoring run counts as
-- production truth. Pulling this once into a variable means all three
-- rollups automatically stay in sync with whatever run is currently
-- approved -- change what's approved in ai_scoring_runs, rerun this file,
-- and every table below recomputes against the new run with zero edits.
DECLARE approved_run_id STRING;
SET approved_run_id = (
  SELECT scoring_run_id
  FROM `sprinternship-sea-2026.majors.ai_scoring_runs`
  WHERE is_approved = TRUE
  ORDER BY approved_at DESC
  LIMIT 1
);

-- ============================================================
-- STEP 1: onet_occupation_ai_scores
-- INPUT:  task_ai_scores (one row per scored task)
-- OUTPUT: one row per O*NET occupation
-- METHOD: importance-weighted average of that occupation's task scores
-- ============================================================
CREATE OR REPLACE TABLE `sprinternship-sea-2026.majors.onet_occupation_ai_scores` AS
WITH eligible_tasks AS (
  -- "Eligible" = every filter here exists to keep a task's score OUT of
  -- the average unless we can actually trust it. Getting any one of
  -- these wrong means either polluting scores with bad data, or silently
  -- dropping data that should have counted.
  SELECT
    s.onet_soc_code,
    s.task_id,
    s.ai_exposure_score,
    r.importance AS importance
  FROM `sprinternship-sea-2026.majors.task_ai_scores` AS s
  JOIN `sprinternship-sea-2026.majors.onet_task_ratings_clean` AS r
    ON s.task_id = r.task_id
   AND s.onet_soc_code = r.onet_soc_code
  JOIN `sprinternship-sea-2026.majors.soc_onet_mapping_clean` AS m
    ON s.onet_soc_code = m.onet_soc_code
  WHERE m.include_in_ai_scoring = TRUE
    -- only the run marked "approved" counts as production truth --
    -- prevents an in-progress or rejected run from silently leaking in
    AND s.scoring_run_id = approved_run_id
    -- only tasks the agent actually scored -- excludes insufficient_data
    -- rows (see task_scoring.py), which have ai_exposure_score = NULL
    -- anyway but this makes the intent explicit rather than implicit
    AND s.scoring_status = 'scored'
    -- O*NET flags some importance ratings as unreliable for this exact
    -- purpose -- respecting that flag is a direct methodology requirement,
    -- not an assumption
    AND r.importance_recommend_suppress IS NOT TRUE
    AND r.importance IS NOT NULL
    AND s.ai_exposure_score IS NOT NULL
),
total_tasks AS (
  -- denominator for coverage: how many scoreable tasks this occupation
  -- *could* have used, vs. how many actually got included above. Without
  -- this, an occupation with only 2 out of 40 tasks scored would produce
  -- a confident-looking average with no way to tell it's built on
  -- almost nothing.
  SELECT onet_soc_code, COUNT(*) AS total_task_count
  FROM `sprinternship-sea-2026.majors.task_scoring_input_clean`
  GROUP BY onet_soc_code
)
SELECT
  e.onet_soc_code,
  -- this is the "exclude missing, renormalize the rest" rule in one line:
  -- SUM(score*importance)/SUM(importance) only ever sums over rows that
  -- survived the WHERE filter above, so excluded tasks don't just get a
  -- weight of zero -- they're not in the denominator at all, which is
  -- what "renormalize" actually means here
  ROUND(SUM(e.ai_exposure_score * e.importance) / SUM(e.importance), 1) AS occupation_exposure_score,
  COUNT(*) AS tasks_used,
  ANY_VALUE(t.total_task_count) AS tasks_total,
  SAFE_DIVIDE(COUNT(*), ANY_VALUE(t.total_task_count)) AS task_coverage_pct,
  approved_run_id AS scoring_run_id
FROM eligible_tasks AS e
LEFT JOIN total_tasks AS t ON e.onet_soc_code = t.onet_soc_code
GROUP BY e.onet_soc_code
-- publish only occupations meeting the coverage threshold from the
-- methodology doc (>=50% of scoreable tasks actually scored) -- an
-- occupation that fails this simply won't have a row here at all, which
-- is what lets downstream steps treat "missing" as "unavailable" rather
-- than accidentally treating it as zero exposure
HAVING task_coverage_pct >= 0.50;


-- ============================================================
-- STEP 2: soc_ai_scores
-- INPUT:  onet_occupation_ai_scores (one row per O*NET occupation, from Step 1)
-- OUTPUT: one row per SOC code
-- METHOD: plain equal-weight average across that SOC's O*NET occupations
--
-- Why equal-weight and not importance-weighted like Step 1: importance
-- ratings only exist at the task level (O*NET rates how important a task
-- is to a job). There's no equivalent "how important is this O*NET
-- variant to the SOC" number to weight by -- so equal weight isn't a
-- shortcut, it's the only honest option given what data actually exists.
-- ============================================================
CREATE OR REPLACE TABLE `sprinternship-sea-2026.majors.soc_ai_scores` AS
SELECT
  m.soc_code,
  -- AVG() ignores NULLs automatically -- this IS the "exclude missing,
  -- renormalize" rule for this step. An O*NET occupation with no Step-1
  -- row (failed coverage, or genuinely unscored) contributes nothing to
  -- either the numerator or the count AVG() divides by.
  ROUND(AVG(o.occupation_exposure_score), 1) AS soc_exposure_score,
  -- same fix as Step 3: count by real score presence, not matched-row
  -- presence. Less likely to bite here since Step 1's output already
  -- passed a coverage gate, but keeping the counting logic consistent
  -- across steps rather than relying on that being permanently true.
  COUNT(o.occupation_exposure_score) AS onet_occupations_used,
  COUNT(m.onet_soc_code) AS onet_occupations_total,
  SAFE_DIVIDE(COUNT(o.occupation_exposure_score), COUNT(m.onet_soc_code)) AS onet_coverage_pct
FROM `sprinternship-sea-2026.majors.soc_onet_mapping_clean` AS m
-- LEFT JOIN, not INNER JOIN, is deliberate: we want every O*NET occupation
-- that's SUPPOSED to map to this SOC to show up in the denominator
-- (onet_occupations_total), even the ones that didn't make it into Step 1
LEFT JOIN `sprinternship-sea-2026.majors.onet_occupation_ai_scores` AS o
  ON m.onet_soc_code = o.onet_soc_code
WHERE m.include_in_ai_scoring = TRUE
GROUP BY m.soc_code;


-- ============================================================
-- STEP 3: major_ai_scores
-- INPUT:  soc_ai_scores (one row per SOC code, from Step 2)
-- OUTPUT: one row per CIP4 major -- this is the number the treemap
--         tile color actually reads
-- METHOD: equal-weight average across that major's related SOCs, via the
--         canonical crosswalk (never joining a major straight to
--         anything else -- the crosswalk is the only trusted CIP<->SOC path)
--
-- IMPORTANT: this anchors on dim_major_cip4_clean, NOT the crosswalk
-- table directly. cip4_to_soc_crosswalk_clean was found (2026-07-17) to
-- still contain cip4_codes that don't exist in the canonical 392-major
-- table -- leftover/junk codes from before the major-cleanup process
-- documented in the handoff doc. Starting from the crosswalk would
-- publish exposure scores for majors that don't actually exist.
-- ============================================================
CREATE OR REPLACE TABLE `sprinternship-sea-2026.majors.major_ai_scores` AS
SELECT
  d.cip4_code,
  ROUND(AVG(s.soc_exposure_score), 1) AS major_exposure_score,
  -- COUNT(s.soc_exposure_score), not COUNT(s.soc_code) -- a SOC can match
  -- a row in soc_ai_scores but still carry a NULL score (found 2026-07-17:
  -- soc_ai_scores has no coverage gate of its own, so it always emits a
  -- row per eligible SOC even when nothing usable existed underneath).
  -- Counting by soc_code alone would call that SOC "used" and inflate
  -- coverage_pct even though it contributed nothing to the average.
  COUNT(s.soc_exposure_score) AS socs_used,
  COUNT(x.soc_code) AS socs_total,
  SAFE_DIVIDE(COUNT(s.soc_exposure_score), COUNT(x.soc_code)) AS soc_coverage_pct,
  approved_run_id AS scoring_run_id
-- start from the canonical majors table, not the crosswalk -- this is
-- what guarantees every row in the output corresponds to a real major
FROM `sprinternship-sea-2026.majors.dim_major_cip4_clean` AS d
JOIN `sprinternship-sea-2026.majors.cip4_to_soc_crosswalk_clean` AS x
  ON d.cip4_code = x.cip4_code
-- same LEFT JOIN logic as Step 2: every SOC the crosswalk says belongs to
-- this major counts toward the coverage denominator, whether or not it
-- made it through Steps 1-2
LEFT JOIN `sprinternship-sea-2026.majors.soc_ai_scores` AS s
  ON x.soc_code = s.soc_code
GROUP BY d.cip4_code
-- Two independent requirements, both must pass:
-- 1. >=50% coverage (methodology doc) -- protects against publishing a
--    score built on a small FRACTION of a major's real occupations
-- 2. >=3 SOCs actually used (added 2026-07-17, evidence-based) -- protects
--    against publishing a score built on a small ABSOLUTE COUNT, even at
--    100% coverage. Found via real data: several 1-2 SOC majors (e.g.
--    "Data Processing", 1/1) outranked Computer Science (13/13) in
--    exposure score, and cross-checking against the broad SOC-category
--    averages (Computer/Mathematical genuinely scores highest, ~6.86
--    avg across 716 tasks) confirmed those top rankings were sample-size
--    noise, not a real signal -- a single occupation's score has nothing
--    to average against, so it can land anywhere.
HAVING soc_coverage_pct >= 0.50
   AND socs_used >= 3;

-- Majors that fail the coverage threshold, or have no crosswalk rows at
-- all (the 21 majors flagged in the handoff doc), simply won't appear in
-- major_ai_scores. That is intentional: the frontend/agent should treat a
-- missing row here as "exposure unavailable", never as zero -- this is
-- the same rule enforced at every step above, just visible here as an
-- absence rather than a filter.