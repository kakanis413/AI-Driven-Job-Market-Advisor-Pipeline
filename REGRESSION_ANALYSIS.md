# Regression Analysis — advisor backend, `main` @ `f635cb0`

Written for an agent picking this up cold. Every claim below was verified by running
code, not by reading it. Commands that produced each finding are included so you can
re-derive rather than trust.

---

## TL;DR

Two separate breakages, ~8 hours apart, both in `advisor/agents.py`.

1. **`83355ff` → carried through merge `9b4bb6c`** — a *semantic* merge conflict
   (`ImportError`, no textual conflict). **Fixed by `c1455b6`.**
2. **`c348272` "sprint 3 optimization for mac and windows"** — removed three things at
   once: `ResilientAgentTool`, the thinking-budget planner, and the `get_recent_news`
   wiring. Also rewrote the root prompt, introducing a marker-string mismatch.
   **Still broken on `main`.**

Three theories were investigated and **disproved**: a missing `dataplex` dependency,
an LLM model swap, and `CLAUDE.md` affecting runtime. See "Disproved" below — do not
re-investigate these.

---

## Verified timeline

`pytest` run at each commit in a detached worktree (`git worktree add --detach`):

| commit | author | pytest | note |
|---|---|---|---|
| `83355ff` | Tejasri Addanki | **2 errors** | break enters here |
| `e39e2f5` | Santoshi Kakani | 47 passed | clean |
| `9b4bb6c` | Tejasri Addanki | **2 errors** | merge of the two above |
| `c1455b6` | Yit E | **58 passed** | repaired it |
| `5f14a75` | Tejasri Addanki | — | last commit with planner wired |
| `c348272` | Santoshi Kakani | **breaks** | three removals |
| `f635cb0` | Santoshi Kakani | **1 error** | current `main` |

Between `5f14a75` and `c348272` sit **four consecutive "Resolved merge conflicts"
commits** by two authors on the same files. That churn is the mechanism; the specific
losses below are the result.

---

## Break 1 — semantic merge conflict (RESOLVED, do not re-fix)

`9b4bb6c` merged `83355ff` + `e39e2f5`. Git reported **no conflict**. The result did
not import:

```
ImportError: cannot import name 'bigquery_toolset' from 'advisor.tools'
```

Cause: one branch refactored the module-level `bigquery_toolset` into a lazy
`get_bigquery_toolset()`; the other branch still imported the old name. Both files
merged cleanly line-by-line. The merged import block contains **both** names — the
fingerprint of a union merge nobody wrote:

```python
from advisor.tools import (
    bigquery_toolset,        # no longer defined anywhere
    get_bigquery_toolset,    # the replacement
    ...
)
```

Note `83355ff` was **already broken before the merge** — the merge only carried it
forward. `c1455b6` fixed it. Nothing to do here; recorded so nobody re-litigates it.

**Lesson for future merges:** git merges text, not meaning. Import/definition splits
across two branches produce clean merges that fail at import. `pytest` catches this in
~1s; nothing else will.

---

## Break 2 — `c348272` (OPEN)

One commit, three removals, all in `advisor/agents.py`. Verified with:

```bash
git log --format="%h %an %ar  %s" -S "class ResilientAgentTool" -- advisor/agents.py
git log --format="%h %an %ar  %s" -S "planner=fast_planner()" -- advisor/agents.py
```

### 2a. `ResilientAgentTool` deleted → whole suite cannot collect

`tests/test_agent_resilience.py` imports it on 3 lines. **One failing import aborts
pytest collection for every test file**, which is why it presents as "everything
broke" rather than one failure.

Runtime impact beyond tests: the news specialist's failures (rate limits, transient
5xx from `google_search`) now propagate as exceptions and 5xx a request whose answer
never needed news, instead of degrading to `{"status": "unavailable"}`.

### 2b. Thinking budget unwired → measured 3–5× slower TTFT

`def fast_planner` and `planner=fast_planner()` both deleted.
`settings.thinking_level` (`config.py:83`, default `MINIMAL`) still exists with a
comment explaining it is worth ~8.2s → ~0.8s TTFT — but **nothing reads it**:

```bash
grep -rn "thinking_level\|ThinkingConfig" advisor/ main.py   # only config.py:83
```

Measured on `main` (2 runs, same grounded question, cache bypassed):

```
run1: TTFT=4858ms  total=6124ms
run2: TTFT=2833ms  total=4283ms
```

Against **~1.0s TTFT** measured on the same question with the planner wired. This is
the single largest latency regression in the repo.

Present at `83355ff`, `e39e2f5`, `9b4bb6c`, `c1455b6`, `5f14a75`; gone at `c348272`.

### 2c. `get_recent_news` unattached

Removed from the imports, from `root_agent.tools`, and from the instructions. The
function still exists in `advisor/tools.py` — it reads the prewarmed, disk-persisted,
background-refreshed per-family news cache in ~0ms. Without it wired, every recency
question falls through to `parallel_research` → live `google_search` at **~7s**.

Measured previously: general recency question ~10.4s → ~3.6s total when
`get_recent_news` was attached.

### 2d. Root prompt rewritten — introduced defects

`ROOT_AGENT_INSTRUCTIONS` went from ~50 lines to ~12. Shorter is a genuine prefill
win, but four things broke:

1. **Marker string mismatch (worst).** Prompt rule 2 says
   `'PRE-LOADED TOP MAJORS DATA'`; `runtime.py:140` injects
   `PRE-LOADED TOP AI EXPOSURE DATA`. The rule that tells the model *"use it, call no
   tools"* — the main tool-avoidance rule — **can never match**.
2. **Rule 1 forbids "BigQuery tools" that are not attached.** No BigQuery tool is in
   `root_agent.tools`; `agents.py` still imports `BQ_DATASET`/`BQ_PROJECT` unused.
3. **Anti-fabrication guardrail deleted.** The old `WHEN A TOOL DEGRADES` block
   ("Never invent numbers, headlines, or dates") is gone with no replacement, while
   `ResilientAgentTool` still hands the model `{"status": "unavailable"}` payloads.
4. **`get_dynamic_top_careers` routing block deleted** (preserve order, don't
   manufacture a Top 3).

Also `f"""` → `"""`, so `settings.project` / `settings.bigquery_dataset` are no longer
interpolated — irrelevant while BigQuery is detached, a trap when it returns.

Rule 3 ("AT MOST ONE tool call total") is a good latency guard but too absolute if
BigQuery returns: SQL legitimately needs `get_table_info` then `execute_sql`.

---

## Disproved — do not re-investigate

| theory | verdict | evidence |
|---|---|---|
| Missing `dataplex` in `requirements.txt` | **False** | `google-cloud-dataplex>=2.0` present at *every* commit in range (added long before by `4722b3b`). Blocking `google.cloud.dataplex` via `sys.meta_path` still imports `BigQueryToolset` — it is not load-bearing; it only backs the uncalled `search_catalog` tool. |
| LLM model was swapped | **False** | `ADVISOR_MODEL` default is `gemini-3.5-flash` at every commit in the range. `git log -S` finds no other model id in history. |
| `CLAUDE.md` raised latency | **False** | Nothing at runtime reads it. `git log -S "gemini" -- Specifications_MD_Files/CLAUDE.md` → zero commits; it never named a model. |

`c1455b6` (the commit most suspected) touched **neither `advisor/agents.py` nor
`requirements.txt`**, and took the suite from 2 errors → 58 passed.

---

## Current state of the working tree

`main` @ `f635cb0` plus **uncommitted** changes. Nothing has been committed.

**Applied (suite: 61 passed, 2 skipped; `tsc --noEmit` clean):**

- `advisor/agents.py` — `ResilientAgentTool` restored + wired to `news_tool`;
  "strictly factual" line restored to `NEWS_INSTRUCTION` (its test asserts it).
- `advisor/news.py` — four fixes:
  - `published` is `None` when unknown (was stamping `datetime.now()`, making every
    card read as published-today);
  - unmatched items **dropped** instead of receiving an arbitrary `chunks[idx % len]`
    URL (hard rule 1, `schemas.py:177` — a wrong link is worse than none);
  - favicon keyed on the *cited* domain, not `urlparse(url)` (every grounding URI is a
    `vertexaisearch` redirect, so every card got Google's favicon);
  - `_meta` / `_enrich` / `_enrich_all` restored → real `og:image` per article
    (~2 of 3 items resolve one) and `article:published_time` backfill.
  - Re-extraction now passes the **grounded domain list** to the model and requires
    `source_domain` to be one of them. Without this, strict matching dropped
    everything and every feed came back empty (`web.domain` is always `None` from
    Vertex; the domain lives in `web.title`).
- `advisor/config.py` — `news_fetch_timeout_s` (default 120s). News fetches measure
  **25–41s**; they were sharing `request_timeout_s` (30s, sized for a chat turn), so
  any fetch competing with the 8-family prewarm burst 503'd the tab.
- `src/components/NewsCard.tsx` — favicons removed from both call sites; `Lead` band
  shows the real `og:image`, falling back to a drawn publisher plate (initials +
  source name, neutral ink — deliberately not the exposure/pay ramps, which carry
  meaning elsewhere).

**Verified after these changes:** all 8 families return 3 items, real date spread, real
publisher domains, zero timeouts.

---

## Open work, highest value first

1. **Restore the thinking budget.** Recover `fast_planner` and pass
   `planner=fast_planner()` on `root_agent`:
   ```bash
   git show 5f14a75:advisor/agents.py | grep -n -A12 "def fast_planner"
   ```
   Expected: TTFT ~2.8–4.9s → ~1.0s. Biggest single win available.
2. **Fix the prompt marker string** — `'PRE-LOADED TOP MAJORS DATA'` →
   `'PRE-LOADED TOP AI EXPOSURE DATA'`. One string; restores the main tool-avoidance rule.
3. **Re-attach `get_recent_news`** to `root_agent.tools` + a routing line in the prompt.
   Recency questions ~10.4s → ~3.6s.
4. **Restore the anti-fabrication block** to the prompt (3 lines).
5. **Decide on BigQuery.** Currently detached while the prompt and docs still describe
   it. Either attach `get_bigquery_toolset()` or strip the references — the ambiguity
   has already cost multiple rounds of confusion.
6. **Session leak** (`PRODUCTION_READINESS.md` Blocker 2) — still open. `create_session`
   at `runtime.py` ×2 and `news.py` ×1; no `delete_session` anywhere. Verified: 50
   creates → 50 retained.

---

## Environment gotchas that cost time

- **zsh eats git refs.** `git show "$c:advisor/agents.py"` silently mangles to an
  absolute path — `:a` and `:r` are zsh history modifiers. Build the ref first:
  ```bash
  ref="${c}:advisor/agents.py"; git show "$ref"
  ```
  Symptom: `fatal: ambiguous argument '<abs-path>dvisor/agents.py'`, or grep counts
  that are silently 0.
- **Stale uvicorn holds :8000.** `pkill -f uvicorn` often misses it; use
  `lsof -nP -iTCP:8000 -sTCP:LISTEN` then `kill -9`. A failed bind cancels the news
  prewarm tasks mid-run ("Root node news_researcher was cancelled").
- **Vite binds IPv6 only.** `http://localhost:5173` works; `http://127.0.0.1:5173`
  is refused. The reverse of this mismatch is what stalls the app on Windows — hence
  `127.0.0.1` in `.env.example` for `VITE_AGENT_URL`.
- **One bad import aborts the entire suite.** A green/red signal here is all-or-nothing;
  always read the collection error before assuming broad breakage.
- **News prewarm is slow and concurrent.** 8 families × 25–41s at
  `PREWARM_CONCURRENCY=4`; a request during prewarm waits on the family lock. Give any
  end-to-end news check ~2 minutes after boot.
- **Frontend has no JS test runner.** "Tests pass" means `pytest` + `npx tsc --noEmit`.
