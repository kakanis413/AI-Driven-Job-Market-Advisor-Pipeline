# ADR-001: Minimize AI Advisor Latency

**Status:** Accepted — Option B implemented 2026-07-24
**Date:** 2026-07-24
**Deciders:** Yit
**Scope:** `advisor/` (FastAPI + Google ADK backend) and `src/lib/advisor.ts` (frontend client)

> **Amended after implementation.** Two premises in the original Context were
> wrong, and the biggest cause of latency was not on the list at all. See
> [Post-implementation findings](#post-implementation-findings).

## Context

The advisor chat feels slow ("latency is crazy") and occasionally shows a wrong
message ("confusing sometimes"). A code read of the live backend found the cause
is **structural, not a missing cache**:

1. **No streaming to the client.** `runtime.py` already implements a working
   `advise_stream()` that yields tokens as they generate — but no endpoint uses
   it. The frontend does a blocking `fetch` to `/api/v1/analyze-major`, which
   calls `runtime.advise()`. The student sees nothing until the *entire* agent
   chain finishes, then the whole reply appears at once.

2. **Serial chain of up to 5 LLM round-trips per turn:**
   `root_agent (LLM)` → `data_tool` → `data_agent (LLM)` → BigQuery (SQL gen +
   query) → root → `news_tool` → `news_agent (LLM)` → `google_search` → root →
   `root_agent (final LLM)`. Each Gemini call is 1–4s, BigQuery cold 2–5s,
   google_search 2–4s — all sequential → 10–30s total.

3. **News fires proactively.** Root instructions say "use news_researcher
   proactively — don't wait for the student to ask," bolting an agent hop +
   google_search onto most turns.

4. **Redundant data hop.** The frontend already POSTs `exposure`, `median_pay`,
   `growth`, `occupations` in the grounding block, yet the model often still
   calls `data_tool` → `data_agent` → sub-tool = two extra LLM calls for data
   already in the prompt. `AgentTool` nesting doubles the calls for every data
   question.

5. **Tail latency from timeout math.** `request_timeout_s=90`, `max_retries=2`,
   exponential backoff → a stuck request can hang ~4+ minutes before failing.

6. **Bug (the "confusing" part).** In `main.py` the fallback
   `guidance_text = (...)` is mis-indented to function-body level, **outside**
   the `except`, so it overwrites the real answer with
   "I couldn't retrieve grounded guidance… please try again later" on **every**
   request — success or failure.

### On caching (the friends' suggestion)

Response caching **already exists** (`RESPONSE_CACHE`, exact-match on normalized
`major:query`, 24h TTL, 500-entry LRU). It is correct and worth keeping, but it
is **not the bottleneck**: chat is free-form, so the exact-match hit rate is low,
and a cache does nothing for the first (uncached) turn — which is exactly the
turn that feels slow. Adding "more caching" is premature. The high-leverage work
is streaming + cutting hops. Cache work is deferred to a later, optional phase.

## Decision

Reduce latency in two tiers, in order:

- **Tier 1 — Perceived latency (ship first, low risk):** fix the `main.py` bug,
  make news opt-in, lower the timeout, and **wire an SSE streaming endpoint to
  the existing `advise_stream()`**. This drops time-to-first-token from
  ~10–30s to ~1–2s with near-zero architectural change.
- **Tier 2 — Actual latency (durable win):** flatten the local data lookups
  directly onto `root_agent` (remove the `data_agent` `AgentTool` layer) so
  simple data questions cost one LLM call instead of three, and reserve
  BigQuery + news for queries that genuinely need them.

**Do NOT** add semantic/embedding caching now. Revisit only if Tier 1+2 leave
p50 above target.

## Options Considered

### Option A: Add more caching (friends' suggestion)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Med (semantic cache = embeddings + vector store) |
| Cost | New infra + per-query embedding call |
| Latency impact | **Low** — helps only repeat queries; first turn unchanged |
| Team familiarity | Low |

**Pros:** Helps hot, repeated queries.
**Cons:** Doesn't touch the slow first turn; free-form chat has low hit rate;
you already have exact-match caching; adds infra for marginal gain.

### Option B: Stream + prune hops (recommended)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low–Med (streaming endpoint already 90% written) |
| Cost | None (reuses existing code + model) |
| Latency impact | **High** — TTFT ~1–2s; fewer round-trips per turn |
| Team familiarity | High (your own code) |

**Pros:** Attacks the actual cause; reuses `advise_stream`; fixes the bug;
massive perceived-speed win.
**Cons:** SSE needs a small frontend change; flattening tools is a moderate
refactor of `agents.py`.

### Option C: Single-agent rewrite (drop ADK sub-agents entirely)
| Dimension | Assessment |
|-----------|------------|
| Complexity | High |
| Cost | Rewrite + re-test the whole advisor |
| Latency impact | High, but overlaps heavily with Option B |
| Team familiarity | Med |

**Pros:** Theoretical minimum hops.
**Cons:** Throws away working resilience (`ResilientAgentTool`) and news
isolation; Option B captures most of the win at a fraction of the risk.

## Trade-off Analysis

Caching optimizes the **repeat** path; the complaint is about the **first**
path. Streaming changes *when* the user sees output (immediately) without
changing total compute, and it's already built — highest reward per unit effort.
Pruning hops changes *how much* compute runs per turn. Together they cover both
perceived and actual latency. Option C's extra gain over B doesn't justify
discarding the graceful-degradation design that's already working.

## Consequences

- **Easier:** first-token feels instant; simple questions get ~3× fewer LLM
  calls; failures surface in ~30s instead of minutes; the bug stops corrupting
  good answers.
- **Harder:** SSE means the frontend reads a token stream, not a JSON blob —
  the error/echo states must handle partial streams.
- **Revisit later:** if p50 still lags after Tier 1+2, *then* evaluate semantic
  caching or Cloud Run min-instances=1 for cold starts — not before.

## Action Items

1. [x] ~~Fix `main.py` fallback indentation~~ — **not a real bug.** The served app
       is the root `main.py`, which never had it. See finding 1.
2. [x] Make news opt-in in `root_agent` instructions; stop proactive calls.
3. [x] Lower `ADVISOR_TIMEOUT_S` default to 30s.
4. [x] Add the SSE endpoint — as `POST /api/v1/analyze-major/stream`, in the app
       that is actually served.
5. [x] `src/lib/advisor.ts` consumes the SSE stream (echo + error state kept).
6. [x] Local data tools flattened onto `root_agent`.
7. [x] `RESPONSE_CACHE` kept, and now works on the streaming path too (it did not).
8. [x] Measured — see the results table below.
9. [x] **Cap the model's thinking budget.** Not in the original plan; the single
       largest win. See finding 3.

## Post-implementation findings

**1. The streaming work was written into a file nobody serves.** The repo had two
FastAPI apps: root `main.py` (launched by the Dockerfile and `npm run dev:backend`)
and `advisor/main.py`. STEP 1 and STEP 4 were both done in the latter, so neither
the bug fix nor the SSE endpoint ever reached a running process. `advisor/main.py`
now re-exports the real app so the two cannot diverge again.

**2. Streaming alone barely helped.** With the endpoint correctly wired, TTFT only
moved 7.7s → 6.0s. Nearly all the latency sat *before* the first token, so there
was almost nothing to stream early.

**3. The real bottleneck was thinking, not the agent chain.** Gemini 3.x thinks
before it writes, and that phase lands entirely in front of the first token.
Measured at the raw model layer on a representative prompt:

| thinking | TTFT | total |
|---|---|---|
| default | 8212ms | 8915ms |
| `LOW` | 4382ms | 4891ms |
| `MINIMAL` | **754ms** | **2387ms** |

The root agent reads a grounding block it was handed, picks at most one tool, and
writes three paragraphs — no extended reasoning budget is warranted. Set via
`ADVISOR_THINKING_LEVEL` (default `MINIMAL`); raise it if answer quality regresses.

**4. `parallel_research` was unreachable.** It subclasses `BaseTool` but never
overrode `_get_declaration()`, which returns `None` by default — so ADK omitted it
from every request and the model could not call it. The chat's entire news path had
been dead since the tool was added, silently answering recency questions from stale
local data. Fixed by declaring the function schema.

**5. The streaming path bypassed the cache.** `advise_stream` neither read nor wrote
`RESPONSE_CACHE`, so moving the frontend onto it would have dropped every hit. Both
paths now share one cache implementation; a repeat question replays in ~8ms.

**6. SSE framing corrupted markdown.** The original endpoint did
`chunk.replace("\n", "\\n")`. Advisor answers are markdown, and a bare newline in a
`data:` field ends the event — replies truncated at the first paragraph break. The
payload is now JSON-encoded.

**7. The chat ignored the news cache the server keeps warm.** `news.py` prewarms a
per-family feed at startup, refreshes it in the background, and persists it to
`.news_cache.json` — and the chat never read it, spawning a fresh ~6.4s live
`google_search` (LLM hop + search) for every recency question instead. Added
`get_recent_news`, a local tool that reads that warm feed, and routed general
recency questions to it. Live `parallel_research` is now reserved for questions
scoped to a specific school or company, which the cache genuinely cannot answer.

**8. Streaming cannot mask a slow tool.** A turn that calls a tool produces no token
until the tool returns, so a school-scoped question shows nothing for ~10s no matter
how well the transport streams. The stream now carries typed events — `status`
alongside `token` — naming the hop actually running, and `ThinkingIndicator` renders
that instead of the invented three-stage text it used to cycle through on a timer.

### Measured results

Same three questions, cache bypassed, against the live backend:

By question type, cache bypassed, measured against the live backend:

| question type | before | after |
|---|---|---|
| Grounded / evaluative (most turns) | ~7.7s to first word | **~1.0s** TTFT, ~2.7s total |
| General recency ("tech hiring lately") | ~10.4s | **~2.5s** TTFT, ~3.6s total |
| School-scoped ("what's going on at UW") | ~12s, unlabeled wait | status at **~1.3s**, ~11s TTFT |
| Repeat question (cache hit) | n/a on stream | **~8ms** |

Verified in the browser against the real client: newlines intact, 9–35 incremental
chunks, status events arriving at 1.4–2.2s.

**The school-scoped path is still slow and that is largely irreducible.** Its cost
is one live domain-scoped web search (6.4–9.6s, highly variable) that no cache can
stand in for. What changed is that the wait is now labeled from ~1.3s instead of
looking frozen, and a repeat of the same question is instant. Remaining levers, if
it needs to be faster: trim `NEWS_INSTRUCTION`'s output format (fewer generated
tokens, at the cost of the citations), or prewarm feeds per university the way
`news.py` already does per family.

---

## Prompt for Claude Code

> Copy-paste the block below into Claude Code, run from the repo root.

```
We're reducing latency in the AI advisor backend (Google ADK + FastAPI in
`advisor/`, React client in `src/lib/advisor.ts`). Do NOT add any new caching —
response caching in `runtime.py` already exists and stays. Work in this order and
run the test suite (`pytest`) after each step.

STEP 1 — Fix the fallback bug (advisor/main.py):
In `analyze_major`, the `guidance_text = (...)` fallback assignment is
mis-indented to function-body level, so it overwrites the real answer on every
request. Move it INSIDE the `except Exception` block only. On the success path,
`guidance_text` must keep `response.generated_guidance`. Also set `route_used`
correctly on both paths (real route on success, "fallback_handler" on error).

STEP 2 — Make news opt-in (advisor/agents.py, root_agent instruction):
Remove the "use news_researcher proactively — don't wait for the student to ask"
guidance. Replace with: only call news_researcher when the question clearly needs
recency (words like "recent", "now", "currently", "hiring", "layoffs", "latest",
specific companies) OR when a UNIVERSITY CONTEXT block is present. For everything
else, answer from the grounding block without news.

STEP 3 — Lower the timeout (advisor/config.py):
Change the `request_timeout_s` default from 90.0 to 30.0. Keep max_retries=2 and
the env override (`ADVISOR_TIMEOUT_S`).

STEP 4 — Add an SSE streaming endpoint (advisor/main.py):
`runtime.py` already has a working `AdvisorRuntime.advise_stream(req)` async
generator. Add `POST /api/advise/stream` that builds the same `AdvisorRequest`
as `/api/advise`, then returns a `StreamingResponse` (media_type
"text/event-stream") that yields each chunk from `advise_stream` as an SSE
`data:` line. On exception mid-stream, emit a final SSE event carrying the same
fallback error text so the client can render an error state. Keep the existing
non-streaming `/api/advise` and `/api/v1/analyze-major` endpoints working for
backward compatibility.

STEP 5 — Consume the stream on the frontend (src/lib/advisor.ts):
Update the advisor client to POST to `/api/advise/stream` and read the SSE
stream via `fetch` + `ReadableStream` reader, appending tokens as they arrive so
the UI shows text incrementally. Preserve the existing offline/echo mode
(unset `VITE_AGENT_URL`) and the designed error state with retry. Expose an
`onToken`/callback or async iterator the AdvisorPanel can consume. Follow the
project's TypeScript strict + design-token rules in CLAUDE.md.

STEP 6 — Flatten local data tools onto root_agent (advisor/agents.py):
Today `root_agent` calls `data_tool` (an AgentTool wrapping `data_agent`), which
then picks a sub-tool — two LLM hops for data already in the prompt. Attach the
fast local functions (`get_major_data`, `compare_majors`, `get_median_pay`,
`get_ai_exposure`, `get_top_majors`) DIRECTLY to `root_agent.tools`, so simple
data questions cost one LLM call. Keep `bigquery_toolset` and `news_tool`
reachable (behind a tool or a slimmed data_agent) ONLY for complex
rankings/aggregations and recency questions. Update the root instruction so it
prefers the direct local tools, uses the grounding block when present, and only
escalates to BigQuery/news when needed. Preserve `ResilientAgentTool` for news.

CONSTRAINTS:
- Change no data schema or design tokens.
- Keep `RESPONSE_CACHE` exactly as is.
- Every step must leave `pytest` green; update mocked endpoint tests
  (tests/test_endpoints_mocked.py) to cover the new stream endpoint and the
  fixed fallback path.
- Conventional commits, one per step, e.g. `fix(advisor): move fallback into
  except`, `perf(advisor): stream advisor responses over SSE`,
  `perf(advisor): flatten data tools onto root agent`.

After all steps, report measured before/after on time-to-first-token and total
latency using the existing `route.latency_ms` logging.
```
