# Production Readiness Review — AI Advisor Backend

**Branch:** `bq-test` @ `f9f289d`
**Date:** 2026-07-27
**Scope:** `advisor/` (FastAPI + Google ADK), `main.py`, `src/lib/advisor.ts`
**Method:** code read + live measurement against Vertex and the `majors` BigQuery
dataset. Every number below was measured on this branch, not estimated.

## Verdict

**The architecture is sound. It is not deployable as-is.**

The latency work landed and holds — common questions answer in ~1.1s to first token.
What blocks production is not design, it is three specific gaps: the slowest path is
invisible to the user, sessions leak on every request, and LLM-generated SQL runs
with no cost ceiling behind an unauthenticated endpoint.

None of the three require rearchitecting. Estimated fix: half a day.

---

## Measured latency

| Path | TTFT | Total | Status shown to user |
|---|---|---|---|
| Grounded question (no tools) | **1133ms** | 2920ms | — (none needed) |
| Comparison (local tool) | **3026ms** | 4953ms | at 1728ms |
| Warm-cache news question | ~2500ms | ~3600ms | at ~1300ms |
| **BigQuery escalation** | **13343ms** | **15124ms** | **none — silent** |
| Repeat question (cache hit) | ~8ms | ~8ms | — |

The distribution is healthy: the fast paths are genuinely fast and the expensive
paths are the ones that genuinely need to be. The problem is the last row.

---

# Blockers

> **Status: 1 and 3 are FIXED.** Blocker 2 (session leak) remains open. See
> "Fix log" at the end for what changed and how it was verified.

## BLOCKER 1 — The slowest path is the only silent one — ✅ FIXED

**Where:** `advisor/runtime.py:43`

`_TOOL_STATUS` maps tool names to the status label streamed to the client. It
contains six entries:

```python
parallel_research, news_researcher, google_search,
get_recent_news, compare_majors, get_top_majors
```

It contains **no BigQuery tools** — no `execute_sql`, no `get_table_info`, no
`list_table_ids`.

**Impact.** A warehouse question takes 15s and emits zero status events. The panel
sits on its static fallback string for 13 seconds with no indication anything is
happening. This is exactly the frozen-panel failure the status channel was built to
prevent, and the one path that most needs it is the only path that does not use it.
Measured: `statuses: []` on a 15124ms turn.

**Fix.** Six entries in the dict:

```python
"execute_sql":       "Querying the warehouse…",
"get_table_info":    "Reading the data schema…",
"list_table_ids":    "Reading the data schema…",
"get_dataset_info":  "Reading the data schema…",
"ask_data_insights": "Querying the warehouse…",
"search_catalog":    "Searching the data catalog…",
```

**Effort:** minutes. **Risk:** none.

---

## BLOCKER 2 — Sessions leak, one per request, forever — ⚠️ OPEN

**Where:** `advisor/runtime.py:182`, `advisor/runtime.py:259`, `advisor/news.py:237`

Every turn calls `create_session()` on `InMemorySessionService` with a fresh UUID.
**Nothing anywhere in `advisor/` calls `delete_session`.**

**Verified empirically:**

```
sessions retained after 50 creates: 50
```

**Impact.** Memory grows monotonically for the life of the process. Each retained
session holds its prompt, response, and tool-call events. Invisible in development
because the dev server restarts constantly; on a long-lived Cloud Run instance this
is an eventual OOM, and the instance dies mid-request when it happens.

This is a slow leak, not an immediate crash — which is why it survives testing and
surfaces in production.

**Fix.** Delete the session in a `finally` once the turn completes, in all three
locations. The session is per-request and never reused, so nothing depends on it
surviving. Note the streaming path needs the cleanup in a `finally` around the
generator so an aborted stream still releases it.

**Effort:** ~1 hour including the abort case. **Risk:** low.

---

## BLOCKER 3 — LLM-written SQL, no cost ceiling, no authentication — ✅ FIXED

**Where:** `advisor/tools.py:50` and `main.py` (absence)

> **Correction to the original severity.** This was first written as a large
> financial risk. Measuring the warehouse changed that: the whole `majors` dataset
> is **128 MB across 40 tables**, and BigQuery bills a 10 MB minimum per query — a
> real advisor query bills 10.5 MB, and scanning the *entire* dataset would cost
> well under a cent. The per-query exposure is small.
>
> The genuine exposure is **volume, not bytes**: on an unauthenticated endpoint the
> dominant cost per request is the Gemini call, not the SQL. That reframes the fix —
> the byte cap is cheap insurance against a runaway join, but **authentication is the
> control that actually protects the budget.** Both are now in place.

Two facts that are each acceptable alone and dangerous together.

**a) No byte cap on queries.**

```python
BigQueryToolConfig(write_mode=WriteMode.BLOCKED)   # read-only ✅
```

Read-only is correct. But `BigQueryToolConfig` offers `maximum_bytes_billed`
(confirmed: `Optional[int] = None`) and it is **unset**. Gemini writes arbitrary SQL
against a 40-table warehouse including `onet_task_ratings_clean`,
`wide_job_market_features`, and `occupation_ai_scores_v2`. One unfiltered join bills
for everything it scans. BigQuery charges by bytes scanned, so a single bad query is
a real invoice.

`max_query_result_rows` defaults to 50, which caps what comes *back* — it does not
cap what gets *scanned*. Those are different things and only the second costs money.

**b) The endpoint is open.**

`main.py` has no `Depends`, no API key, no `Authorization` check, no rate limiting.
Every request costs a Gemini call and potentially a BigQuery scan. Anyone who finds
the URL can spend your budget in a loop.

**Impact.** Uncapped spend reachable by anyone. This is the one finding here with a
direct financial blast radius.

**Fix.**
1. Set `maximum_bytes_billed` on the toolset — pick a ceiling that comfortably covers
   a legitimate query and hard-fails a runaway one.
2. Put authentication in front of the endpoint. This depends on how you front Cloud
   Run (IAP, an API gateway, a shared key) so it is a decision, not a patch — but
   the service must not be publicly reachable while BigQuery is attached.
3. Add rate limiting per client.

**Effort:** the byte cap is minutes; auth depends on your infrastructure choice.
**Risk of not fixing:** financial.

---

# High priority (will break or cost, but not blockers)

### CORS defaults to localhost only

`advisor/config.py` defaults `cors_origins` to a list of `localhost:517x` ports.
**`ADVISOR_CORS_ORIGINS` must be set in production** or every browser request fails
CORS. This is a deployment prerequisite, not a code bug — but it fails 100% of real
traffic if missed.

### Dependencies are unpinned

```
fastapi>=0.115    google-adk>=2.0    pydantic>=2.12    google-cloud-bigquery>=3.25
```

All `>=`, no upper bounds and no lockfile. A rebuild can pull `google-adk` 3.x and
break the agent wiring with no source change. Builds are not reproducible: the image
you test is not guaranteed to be the image you ship. Pin them, or commit a lockfile.

### Caches are per-instance

Both `RESPONSE_CACHE` (24h, in-process) and the news feed cache live in instance
memory. With autoscaling, hit rate divides by instance count and every scale-up
serves cold. The 24h cache does much less work at 5 instances than at 1. Not wrong,
but do not expect the measured ~8ms cache-hit number to hold under load.

### News cache cold-starts on every deploy

`advisor/.news_cache.json` is excluded by `.dockerignore`, so each new revision boots
with an empty news cache and the first request per family pays a full live fetch.
The stale-while-revalidate design handles this correctly, but the first users after
each deploy get the slow path.

---

# Hygiene

- **`dist/` and `advisor/.news_cache.json` are tracked in git.** Build output and a
  rotating data file in version control cause needless diff churn and merge
  conflicts. The working tree already showed untracked `dist/assets/*` at session
  start, which is the symptom.
- **The container runs as root.** No `USER` directive in the Dockerfile. Standard
  hardening, low urgency.
- **`agent_config.py` is dead code** — unimported, and raises `ModuleNotFoundError`
  if imported (it imports a root-level `tools.py` that does not exist). It describes
  a `data_agent` + BigQuery architecture that is not what runs. Delete it or mark it
  clearly; it has already caused one round of confusion about whether BigQuery works.

---

# What is genuinely good

Worth stating plainly, because the core is well built and several of these are
things that are commonly gotten wrong.

### Streaming is done correctly

Three subtle things, all right:

- **`RunConfig(streaming_mode=StreamingMode.SSE)` is set.** Without it ADK yields one
  complete message per agent turn and "streaming" delivers the whole answer at the
  end — TTFT would equal total latency. This is the difference between real streaming
  and the appearance of it.
- **Sub-agent text is filtered by `event.author`.** The news specialist emits its own
  text events; forwarding them would dump raw research bullets into the chat before
  the actual answer.
- **Partial and final events are deduped.** ADK's final event repeats the full text
  the partials already delivered. Without the guard the answer renders twice.

### Cache correctness

Key construction is shared by the blocking and streaming paths, so they cannot drift
apart. Hits return a **deep copy** before marking `route.path = "cache_hit"` —
mutating the stored object would corrupt the cached entry's timing metadata on first
read. TTL and LRU eviction are both enforced under an `asyncio.Lock`.

### Timeouts are layered correctly

30s default (down from 90s), applied per-chunk on the streaming path via
`asyncio.wait_for(stream.__anext__(), ...)` so a stalled upstream cannot hold a
connection open forever, plus retry with exponential backoff on the blocking path.
Per-chunk rather than whole-turn is the right choice for a stream.

### Flat tool architecture

Local lookups attach directly to `root_agent` with no `AgentTool` wrapper, so a data
question costs one LLM hop instead of three. BigQuery is attached the same way rather
than behind a `data_agent`. This is the single biggest structural reason the fast
paths are fast.

### Cheap sources before expensive ones

`get_recent_news` reads the prewarmed, background-refreshed, disk-persisted feed
(~0ms) and live web search is reserved for questions the cache genuinely cannot
answer. This is the same escalation discipline applied to data: `data.json` first,
BigQuery only for what it cannot hold.

### Graceful degradation

`ResilientAgentTool` converts a failing news specialist into
`{"status": "unavailable"}` rather than an exception, and the root instruction tells
the model to answer from verified data and say news could not be checked. A flaky
`google_search` degrades the answer instead of 5xx-ing the request.

### Honest data handling

`median_pay` and `growth` are nullable end to end, with a validator treating `0` as
unknown so the advisor never reports a $0 median as fact. Tool misses return explicit
`status: "not_found"` with near-matches rather than an empty result the model might
fill in. The grounding block tells the model what it may not claim.

### Secrets hygiene

Authentication is ADC only — no credentials in code or config. `.env` is untracked
and holds only non-secret project identifiers. `.dockerignore` is thorough and
correctly excludes `.env`, `.venv`, `node_modules`, `dist`, and tests, so nothing
sensitive is baked into the image.

### One served app

`advisor/main.py` is now a re-export of the root `main.py`, so `uvicorn main:app` and
`uvicorn advisor.main:app` are the same process. This previously was not true and
cost the team a full round of work on a streaming endpoint that no running server
ever loaded.

### Test suite is green and meaningful

47 passing, 2 skipped (live tests, gated behind `RUN_LIVE=1`). The mocked suite fakes
only the LLM boundary — validation, the response contract, status codes, SSE framing,
and error handling are all exercised for real.

---

# Recommended order

1. **Blocker 3a** — set `maximum_bytes_billed`. Minutes, removes the financial risk.
2. **Blocker 1** — BigQuery status labels. Minutes, fixes the worst user-facing issue.
3. **Blocker 2** — session cleanup. ~1 hour, prevents the slow OOM.
4. **CORS + dependency pinning.** Deployment prerequisites.
5. **Blocker 3b** — authentication. Depends on infrastructure; decide before public exposure.

Items 1–3 are contained code changes with tests already in place around them. Item 5
is the one that needs a decision rather than a patch.

---

# Fix log

## Blocker 1 — BigQuery status labels ✅

Added all ten BigQuery tool names to `_TOOL_STATUS` (`advisor/runtime.py`), split
across two labels so schema discovery and the query itself read as distinct waits.

**Verified end-to-end** through the real browser client against the running backend:

| | before | after |
|---|---|---|
| Status events on a warehouse turn | **0** | **3** (at 1.6s, 4.5s, 6.8s) |

The wait is unchanged in length — it is a live SQL path and that is its real cost —
but it is now narrated from 1.6s instead of showing nothing for the duration.

## Blocker 3a — BigQuery byte ceiling ✅

`maximum_bytes_billed` is now set from `settings.bigquery_max_bytes_billed`
(`ADVISOR_BQ_MAX_BYTES_BILLED`, default **256 MB**). Sized against the measured
128 MB dataset: 2x headroom for a self-join, still a hard stop on anything absurd.

**Verified against real BigQuery:**

```
legitimate query under cap : OK, 5 rows, billed 10.5 MB
runaway with a 1KB cap     : blocked — "Query exceeded limit for bytes billed"
```

BigQuery kills the job rather than billing it.

## Blocker 3b — Authentication and rate limiting ✅

Added an HTTP middleware to `main.py`. **Both controls are off unless configured**,
so local dev and the current deployment are byte-for-byte unchanged until switched on.

- `ADVISOR_API_KEY` — when set, requests must send `X-API-Key`. Compared with
  `secrets.compare_digest`, because a plain `!=` leaks the key one character at a time.
- `ADVISOR_RATE_LIMIT_PER_MIN` — sliding window per client, `0` disables. Returns 429
  with `Retry-After`.
- `/` and `/healthz` stay open — Cloud Run's health probe cannot present a key, and
  locking it out downs the service.
- The frontend sends the key via `VITE_ADVISOR_API_KEY` when set.

**Middleware ordering matters and is deliberate:** CORS is registered *after* the
guard so it wraps it. Starlette runs the most recently added middleware outermost, so
this ordering means a 401 or 429 still carries `Access-Control-Allow-Origin` and
reaches the browser as the status it actually is, rather than as an opaque CORS
failure that hides the reason. There is a test pinning this.

### Two honest limits on 3b

- **The frontend key is public.** Anything in a Vite bundle ships to the browser and
  is readable in devtools. It stops casual abuse of a money-spending endpoint; it is
  not a secret. Real auth (IAP, a gateway, signed sessions) still belongs in front of
  Cloud Run — this is the floor, not the ceiling.
- **The rate limiter is in-process.** The effective limit is the configured value
  times the instance count, and it resets on deploy. A real limiter belongs at the edge.

## Test coverage

`tests/test_access_control.py` — 11 tests: BigQuery labels present and distinct, byte
cap set and within a sane band, toolset read-only, key rejected/accepted, health probe
open, CORS headers survive a 401, rate limit trips with `Retry-After`, and the
unconfigured path still returns 200.

**Suite: 58 passed, 2 skipped. TypeScript: clean.**

## Still open

**Blocker 2 (session leak)** and the high-priority items — CORS origins, dependency
pinning, per-instance caches — are unchanged.
