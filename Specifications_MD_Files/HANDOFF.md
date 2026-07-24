# Handoff — advisor service + frontend wiring

**What this push contains:** a working multi-agent AI advisor, wired to the frontend, with
tests and docs. Nothing in the data pipeline (`data_pipeline.py`, `batch/`) was touched —
that's still yours.

Status: `uvicorn main:app` boots clean · `pytest tests/ -q` → **31 passed, 2 skipped** ·
a real request returns a grounded Gemini answer on Vertex.

---

## 1. The new `advisor/` package (what each file does)

The old `agent_config.py` + `tools.py` (single agent, mock tool) are replaced by a package.
`main.py` is now thin — it validates the request and hands off to `advisor/runtime.py`.

| File | What it does |
|---|---|
| `config.py` | Single source of truth for model, project, and feature flags. Reads **non-secret** config from env only — auth is ADC, never keys in code. Flags: `ADVISOR_ENABLE_NEWS`, `ADVISOR_ENABLE_BIGQUERY`, `ADVISOR_CORS_ORIGINS`, `ADVISOR_MODEL`, `ADVISOR_DATA_FILE`. |
| `schemas.py` | The one request/response contract the React app talks to. Backward-compatible with the existing frontend (still returns `generated_guidance`). **`median_pay` and `growth` are nullable** — the real data has nulls, and rejecting them was a bug. |
| `data_source.py` | In-memory lookup over the same `data.json` the browser renders, so the UI and the advisor can never disagree. Loaded once, lazily. |
| `tools.py` | The tools the data agent calls — `get_major_data`, `compare_majors`. **Real lookups, no mocks.** Every tool returns an explicit `status`, so a miss is a fact the model reports ("I don't have that major") instead of an invitation to invent one. Also holds the optional BigQuery toolset builder. |
| `agents.py` | The agent roster: `data_agent`, `news_agent`, `advisor_agent`, plus the LLM-routed `orchestrator` and a `single_agent` fallback. |
| `runtime.py` | Turns a request into an answer: timeout, retry, route tracking, and the multi-agent → single-agent fallback. All orchestration lives here so it's testable without a web server. |
| `errors.py` | Typed errors → structured JSON. The chat panel never sees a stack trace. |

### Two design decisions worth knowing (don't undo these)

1. **We compose specialists with `AgentTool`, not `sub_agents`.** This is verified against
   google-adk 2.5.0, not assumed. `sub_agents` performs an LLM *transfer* — control hands off
   to the sub-agent and doesn't come back. Our flow is *gather facts → compose an answer*, so
   the orchestrator needs the result **returned** to it. That's `AgentTool`. Switching this to
   `sub_agents` will silently break the compose step.
2. **`google_search` sits alone in `news_agent`.** ADK's built-in tools "cannot be used
   together with other tools," so search gets its own isolated agent, reached via `AgentTool`.

### How routing works
The orchestrator decides **per question** which specialists to call — it does not run a fixed
pipeline. A pay question calls only `data_agent`; a current-events question also calls
`news_agent` (which costs a billed search, so it only fires when the question needs it). The
response reports what ran:
```
response | path=multi_agent agents=['advisor_agent'] search=False latency=11441ms degraded=False
```
`degraded: true` means the multi-agent path failed and the single-agent fallback answered.

---

## 2. Everything else in this push

**Backend**
- `main.py` — rewritten thin: validation + handoff to the runtime, structured error handler,
  `/healthz` reporting live config.

**Frontend**
- `src/lib/advisor.ts` — now sends **real nulls** instead of `median_pay ?? 0` and
  `growth ?? 'not available'`. The old coercion told the advisor pay was literally $0 — a
  grounding bug. Also sends `cip` and `soc`.
- `src/components/AdvisorPanel.tsx`, `src/pages/Explore.tsx` — a real "thinking" state, since
  a multi-agent answer takes ~11s and static dots read as frozen.
- **Deleted** `src/api.js` and `src/components/Majortile.jsx` — dead code. `api.js` was a
  second, conflicting copy of the advisor transport; `Majortile.jsx` was unimported and
  referenced an undefined variable. `src/lib/advisor.ts` is now the *only* path to the agent.

**Tests** (`31 passed, 2 skipped`)
- `conftest.py` — added the missing `client` and `mock_agent_response` fixtures. Only the LLM
  boundary is faked; validation, status codes and the response contract are exercised for real.
- `test_endpoints_mocked.py` — rewritten against the current API (dropped tests for the removed
  `/api/v1/ask-major`; null growth/pay now correctly expect 200, not 422).
- `test_agent_resilience.py` — new: proves a failure inside a wrapped agent comes back as a
  structured "unavailable" the orchestrator routes around, instead of 5xx-ing the request.
  This is the fix for the 502 on news questions.

**Docs**
- `WEBSITE_INTEGRATION.md` — the frontend↔agent contract. **Read this first if you're touching
  either side.**
- `ADK_PRODUCTION.md` — what ADK gives us and why the agent is built this way.
- `PLAN.md` / `AGENT_ARCHITECTURE.md` — the design and what was verified.
- `CLAUDE.md` — color ramp table updated to match the real tokens.

---

## 3. Things already established (please don't re-debug these)

- **Auth works:** Vertex AI + ADC, project `sprinternship-sea-2026`, location `global`,
  model `gemini-3.5-flash`.
- **The `set-quota-project` / `serviceusage.services.use` error is a red herring.** Gemini
  calls work without it — Vertex names the project in the request and checks `aiplatform`
  permissions. Ignore that warning.
- **`RefreshError: Reauthentication is needed`** just means ADC expired. Re-run
  `gcloud auth application-default login`. Not a code bug.
- **The BigQuery *Python client* is blocked by org IAM**; the `bq` CLI works. BigQuery is
  config-gated **off** by design — the service runs fully without it.
- **`VITE_AGENT_URL` is the full endpoint URL**, not a base URL (`.../api/v1/analyze-major`).
  Setting it to the host alone gives `POST /` → 405. Vite only reads `.env` at startup —
  restart the dev server after changing it.

---

## 4. Known gaps — these are data, not code

🔴 **`exposure` is `0.5` for all 376 majors.** The treemap currently renders as one flat
color. No frontend work can fix this — it needs the scoring pipeline output. **This is the
demo-critical item.**

🟡 **Only 24 of 376 majors have `cip` or `occupations`.** Until the crosswalk join populates
them, the detail card's occupation list is empty and the advisor can't cite specific
occupations. Deliberately **not** hand-filled — it needs real pipeline data.

---

## 5. Suggested split for today (4 of us)

- **Data/exposure owner** — run the task scoring and get real 0–10 exposure into `data.json`.
  Everything visual depends on this; it's the critical path.
- **Crosswalk/pipeline owner** — populate `cip` + `occupations` for all majors, and make sure
  the pipeline's final output matches the `Major` contract in `src/types.ts`.
- **Agent/cloud owner** — review `advisor/` and decide if we adopt it; if yes, next step is
  deploying it to Cloud Run (it's local-only right now).
- **Frontend (Yit)** — surface news per major in the detail card (the news agent already
  works), plus the mobile + accessibility pass.
- **Everyone** — read `WEBSITE_INTEGRATION.md` before changing either side of the API.

**Note:** `.claude/`, `.vscode/`, and `tests/AI-Driven-Job-Market-Advisor-Pipeline.code-workspace`
are local editor files — add them to `.gitignore` rather than committing them.
