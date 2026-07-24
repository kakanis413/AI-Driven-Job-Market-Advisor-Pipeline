# Agent Architecture — AI-Driven Job Market Advisor

A design for the agents in this project: what each one is, where it runs, how
they connect, and how they serve the product goal. Written against the code that
exists today (`agent_config.py`, `main.py`, `tools.py`, `batch/exposure_calc.py`,
`data_pipeline.py`) and assumes ADC (Application Default Credentials) is working.

---

## 1. The one principle that shapes everything

**The visualizer never talks to an agent. The advisor is the only live agent.**

The treemap/heatmap loads a static, pre-computed `data.json` (cached on GCS). It
is instant, free, and identical for every visitor. Agents are expensive
(LLM latency + cost + can fail), so we keep them off the hot path and use them in
exactly two places:

- **Offline**, to *build* the data (score AI exposure per major) — runs on a
  schedule, not per request.
- **Online**, to *advise* one student who is asking a question about one major —
  runs per chat message, not per page load.

Everything below follows from that split. If you remember one thing, remember
this: **two planes — a write plane that makes the data, a read plane that serves
it — and the viz sits entirely inside the cheap read plane.**

---

## 2. The two planes

```
                    WRITE PLANE (offline, scheduled)                 READ PLANE (online, per user)
                    ================================                 =============================

  BigQuery raw tables                                                Browser
  ┌───────────────────────────┐                                     ┌──────────────────────────┐
  │ dim_major                 │                                     │ Treemap / Heatmap        │
  │ fact_exposure (occ rows)  │                                     │  loads data.json  ───────┼──┐
  │ cip4_to_soc_crosswalk     │                                     │  (NO agent call)         │  │
  │ dim_occupations           │                                     │                          │  │
  └─────────────┬─────────────┘                                     │ AdvisorPanel (chat)      │  │
                │ occupation rows per major                         └───────────┬──────────────┘  │
                ▼                                                                │ POST            │
    ┌───────────────────────────┐                                               │ major + question│
    │ (1) ExposureAnalystAgent  │  computes exact weighted mean                 ▼                 │
    │     + code executor       │  via Python, not "by vibes"        ┌────────────────────────┐   │
    └─────────────┬─────────────┘                                    │ FastAPI  /advisor/chat │   │
                  │ exposure_score                                   └───────────┬────────────┘   │
                  ▼                                                              │                 │
        writes major_summary                                                    ▼                 │
                  │                                                  ┌────────────────────────┐   │
                  ▼                                                  │ (2) AdvisorAgent       │   │
    ┌───────────────────────────┐                                   │     (coordinator)      │   │
    │ data_pipeline.py          │  SQL join + growth bucketing      │   tools:               │   │
    │  major_summary            │  + rationale text                 │   • get_major_data ────┼───┘ reads same data
    │  + fact_exposure          │                                   │   • compare_majors     │
    │  + crosswalk/occupations  │                                   │   • (3) MarketNews ────┼──► Google Search
    └─────────────┬─────────────┘                                   └───────────┬────────────┘     grounding
                  ▼                                                              │
             data.json  ───────────────► GCS (cached) ───────────► served to ───┘  grounded answer
```

Read that as: the **write plane** turns messy BigQuery tables into one clean
`data.json`; the **read plane** serves that file to the viz and lets the advisor
reason over it live.

---

## 3. What you have today

Two agents already exist, both `google-adk` `Agent`s on the same model:

| Agent | File | Plane | Job |
|---|---|---|---|
| `major_exposure_analyst` | `batch/exposure_calc.py` | write | Turns occupation-level exposure rows into one major-level score, using a **code executor** so the arithmetic is exact. Writes `major_summary`. |
| `college_advisor` (`root_agent`) | `agent_config.py` | read | Answers a student's question about a major. Currently has one tool, `get_major_data`, which is **a mock** (`tools.py` returns hard-coded Computer Science data for everything). |

Serving is `main.py` (FastAPI) with an ADK `Runner` + `InMemorySessionService`
and **two overlapping endpoints**: `/analyze-major` (grounds on the full record
the client sends — this is the one the frontend now uses) and `/ask-major`
(relies on the mock tool).

That's a solid skeleton. The design below keeps it and fills the gaps.

---

## 4. The target agent roster

Three agents, each with one clear job. Two you already have; one is new.

### Agent 1 — ExposureAnalystAgent (write plane, keep + harden)

- **What it does:** given the occupation rows for a major (SOC, title, exposure,
  employment weight), produce one major-level exposure score, the method used,
  and which occupations were included/excluded.
- **Why it's an agent and not just Python:** it has to reason about messy inputs
  (missing weights, missing exposures, "insufficient data") and *explain* itself
  in a structured `ExposureResult`. But the actual math runs in a **code
  executor** (`temperature=0`), so the number is deterministic — the LLM decides
  *what* to compute, Python computes it. This is the right pattern and already in
  place.
- **How it's invoked:** the batch loop in `run_batch()` iterates every major from
  `dim_major`, feeds it, and writes the score to `major_summary`. It runs on a
  **schedule** (e.g. nightly / when source data refreshes), never per request.
- **Input:** JSON occupation bundle. **Output:** `ExposureResult` (structured).

### Agent 2 — AdvisorAgent (read plane, keep + upgrade the tools)

- **What it does:** the student-facing chat. Owns *voice, empathy, framing, and
  the hard caveat* ("high exposure ≠ the job disappears"). It does not compute
  numbers or fetch raw data itself — it **delegates** and then explains.
- **Tools it calls (this is the upgrade):**
  - `get_major_data(major_name)` — **replace the mock** with a real lookup that
    reads the served data (see §6). This lets the advisor answer about *any*
    major, not just the one in the request, and enables follow-ups.
  - `compare_majors(major_a, major_b)` — optional, unlocks "is CS or Nursing more
    exposed?" which is a very natural student question.
  - `MarketNewsAgent` as a tool (Agent 3) — called only when the student asks
    about *current* events ("what's happening now", "latest").
- **How it's invoked:** per chat message, via one FastAPI endpoint. The Runner
  streams events; we return the final grounded answer.
- **Input:** the selected major's record + the student's message. **Output:**
  3–5 short conversational paragraphs, grounded, caveat included.

### Agent 3 — MarketNewsAgent (read plane, NEW — serves pillar 2)

- **What it does:** given a major or its occupations, fetch *recent* labor-market
  / AI-adoption signal via **Google Search grounding**, and return a short,
  **cited** context blurb. This is what makes the "real-time data & news" pillar
  real instead of aspirational.
- **Why a separate agent:** search-grounded answers have different reliability
  rules (must cite, must not overclaim, can be slow). Isolating it keeps the
  AdvisorAgent's instruction clean and lets you test/limit it independently.
- **How it's invoked:** the AdvisorAgent calls it as a tool, on demand — not on
  every message (latency + cost). Behind an explicit "current events" intent.
- **Input:** major/occupation + question. **Output:** short cited summary, or
  "no notable recent signal" so the advisor never invents news.

---

## 5. How a request actually flows (read plane, step by step)

1. Student opens the app → browser fetches `data.json` from GCS. **No agent.**
2. Student clicks a major tile → `AdvisorPanel` gets that `Major` object.
3. Student types "How will AI change this?" → frontend POSTs
   `{ major record, question }` to `/advisor/chat`.
4. `AdvisorAgent` reads the record it was handed (already grounded), and:
   - if the question is factual/comparative → calls `get_major_data` /
     `compare_majors`;
   - if the question is about *now* → calls `MarketNewsAgent`.
5. AdvisorAgent composes the final answer: grounded numbers + the mandatory
   caveat + specific occupations, 3–5 short paragraphs.
6. FastAPI returns `{ generated_guidance }`; the panel renders it. If anything
   failed, the frontend already degrades to the offline echo / error+retry.

---

## 6. The key improvements (and why)

1. **Collapse two endpoints into one.** `/analyze-major` and `/ask-major` overlap
   and the second one leans on the mock tool. Keep a single `/advisor/chat`
   (rename optional). Less surface area, one code path to test.
2. **Make `get_major_data` real.** Simplest robust option: load `data.json` into
   an in-memory dict keyed by major name at startup, and have the tool read that.
   Benefits: the advisor grounds on the *exact same data the user sees* (no
   drift), zero per-request BigQuery cost, instant. Swap to a live BigQuery query
   later only if you need freshness or cross-major SQL the file can't answer.
   *Trade-off:* in-memory means a data refresh needs a process restart or a
   reload hook — fine for a demo, noted for scale.
3. **Centralize model + config.** `"gemini-3.5-flash"` is hard-coded in two files.
   Put the model name, temperature, and project in one `agents/config.py`. One
   place to change, no drift. **Verify the model id** against the models your
   Gemini Enterprise platform actually exposes before the demo — a wrong id
   surfaces as a runtime 404/permission error, not a validation error.
4. **Add MarketNewsAgent** to deliver pillar 2. Even a minimal version (one
   search-grounded blurb with citations) visibly raises the project above "static
   scores + chatbot."
5. **Mind the ADK constraint:** an agent with an `output_schema` generally cannot
   also use tools/transfer. That's why ExposureAnalyst (schema + code executor)
   and Advisor (tools, free-text) are **separate agents** — don't try to merge
   them or give the advisor an `output_schema`.
6. **Sessions:** `InMemorySessionService` loses memory on restart and isn't shared
   across workers. Fine now. For real multi-turn memory or multiple server
   instances, move to a persistent session service.
7. **Tighten CORS** (`allow_origins=["*"]` → your frontend origin) before any
   public demo. Already flagged in the code.

---

## 7. Suggested file structure

Group the agents into one package so `main.py` just wires them to HTTP:

```
agents/
  __init__.py
  config.py          # model name, temperature, project, GCP settings — one source
  exposure_analyst.py# Agent 1 (moved from batch/, imported by the batch loop)
  advisor.py         # Agent 2 (the coordinator) + its instruction
  market_news.py     # Agent 3 (search-grounded)
  tools.py           # REAL get_major_data, compare_majors (replaces the mock)
batch/
  exposure_calc.py   # keeps the batch loop; imports agents.exposure_analyst
main.py              # FastAPI: one /advisor/chat endpoint, imports agents.advisor
data_pipeline.py     # unchanged (BigQuery → data.json → GCS)
```

Nothing here fights your existing `CLAUDE.md`; it just gives the agents a home and
kills the mock.

---

## 8. Build order (fastest path to "agents working")

1. Replace the mock `get_major_data` with the in-memory `data.json` lookup. This
   alone makes the advisor genuinely grounded and kills the CS-for-everything bug.
2. Collapse to one `/advisor/chat` endpoint; point the frontend at it.
3. Confirm end-to-end with ADC: run the batch scorer → `data_pipeline.py` →
   fresh `data.json` (with real growth) → advisor answers from it.
4. Add `compare_majors` (small, high value).
5. Add `MarketNewsAgent` (the pillar-2 stretch).
6. Centralize config, tighten CORS, decide on session persistence.

---

## 9. Trade-offs, made explicit

| Decision | Chose | Because | Cost / revisit when |
|---|---|---|---|
| Viz data source | Static `data.json` | Instant, free, no agent on page load | Stale between pipeline runs — fine (scores move slowly) |
| Advisor grounding | Read the served `data.json` in-memory | UI/agent never disagree; zero request-time BQ | Needs reload on refresh; go to BQ if you need live freshness |
| One coordinator + tools | vs. one mega-prompt | Testable, each capability isolated, easy to extend | More moving parts than a single prompt |
| News as its own agent | vs. folding search into advisor | Different reliability rules (must cite), independently limitable | Extra latency/cost — so it's on-demand only |
| Exact score via code executor | vs. LLM doing the math | Deterministic, defensible numbers | Slightly slower batch — irrelevant offline |

---

## 10. What I'd revisit as it grows

- **Caching advisor answers** for common (major, question) pairs to cut cost.
- **A guardrail check** that the caveat is present in every advisor answer (it's a
  hard product rule, not just an instruction).
- **Persistent + shared sessions** once there's more than one server or real
  multi-turn memory.
- **Observability:** log tool calls, latency, and failures per agent so you can
  see which tool is slow or erroring.
- **Live BigQuery grounding** if the product needs numbers fresher than the
  pipeline cadence.
