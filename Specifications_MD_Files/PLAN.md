# PLAN — Production Multi-Agent Advisor

What I'm building, why, and what I verified before writing a line of it.
Written against **google-adk 2.5.0** (clean venv), **Gemini 3.5 Flash on Vertex via ADC**,
project `sprinternship-sea-2026`, location `global`.

---

## 0. Ground rules I followed

**Every symbol below was imported and confirmed in a scratch script before design.**
Where `AGENT_ARCHITECTURE.md` / `agent_layer.md` disagree with the installed package, the
**installed package wins**. The two places that matters are recorded in §5.

---

## 1. The product problem this solves

A student clicks a major in the treemap and asks a question. The answer must be:

- **Grounded** — every number comes from our data, never the model's memory.
- **Correctly framed** — high AI exposure means *the work changes*, not *the job disappears*.
- **Cheap and fast** — a billed Google Search must not fire on every chat turn.
- **Impossible to take down** — the viz is static and must never depend on the agent, and the
  agent itself needs a fallback so one flaky path doesn't 500 the demo.

Everything below follows from those four.

---

## 2. The architecture, in plain English

```
React AdvisorPanel
      │  POST /api/v1/analyze-major   { major record + student question }
      ▼
FastAPI (validation, timeout, retry, structured errors)
      ▼
┌─────────────────────────────────────────────────────────┐
│ ORCHESTRATOR (LlmAgent — decides, per question)         │
│   tools = [AgentTool(data), AgentTool(news), AgentTool(advisor)]
│                                                          │
│   ├─ data_agent    → the major's exposure/pay/occupations│
│   ├─ news_agent    → google_search  ← ONLY when asked    │
│   └─ advisor_agent → writes the grounded guidance        │
└─────────────────────────────────────────────────────────┘
      │  (on any failure)
      └─► SINGLE-AGENT FALLBACK — one grounded agent, no routing
```

### Why an orchestrator that *routes* instead of a fixed pipeline

A `SequentialAgent` would run Data → News → Advisor in fixed order **every single turn**, which
fires a billed Google Search even for "what's the median pay?". The LLM orchestrator reads the
question and calls only what it needs. That is both cheaper and smarter. The tradeoff — routing
is model-decided, so it's less rigidly predictable — I mitigate with a tightly-worded
orchestrator instruction and by proving the routing behavior in tests.

### Why `AgentTool`, NOT `sub_agents` — the key design decision

The design docs sketch `root_agent = Agent(..., sub_agents=[data, news, advisor])`. Both symbols
exist in 2.5.0, but they have **different semantics**, and `sub_agents` is wrong for this job:

| | `sub_agents=[...]` | `tools=[AgentTool(agent=...)]` |
|---|---|---|
| Mechanism | LLM-driven **transfer** (`transfer_to_agent`) | Agent invoked **as a tool** |
| Control | **Hands off** — the sub-agent becomes the responder | **Returns** to the orchestrator with a result |
| Fits "gather facts, then compose"? | No — control leaves and doesn't naturally come back | **Yes** — orchestrator collects data + news, then composes |

Our flow is *gather → synthesize*: the orchestrator needs the data agent's numbers **back** so it
can hand them to the advisor. That's `AgentTool`. I proved this live before committing to it
(§4).

### Each agent's job

- **data_agent** — returns hard facts for one major (exposure, pay, occupations). Facts only,
  no advice. Reads the same `public/data.json` the user is looking at, so the UI and the agent
  can never disagree. BigQuery is an *optional* upgrade (§6).
- **news_agent** — isolated agent whose **only** tool is `google_search`. Returns 2–3 recent,
  cited items, or explicitly says "no notable recent signal" so the advisor never invents news.
  Isolated because search-grounded output has different reliability rules (must cite, can be
  slow, costs money) and because of the built-in-tool constraint in §5.
- **advisor_agent** — no external tools. Its skill is reasoning and writing: 3–5 short
  paragraphs, grounded strictly in what it was handed, mandatory "exposure ≠ job loss" framing,
  references the specific occupations.
- **orchestrator** — routes, then composes the final student-facing answer.

### Grounding (mandatory, non-negotiable)

Grounding is what makes this a credible advisor instead of a chatbot. Two mechanisms stack:

1. **Request-passed data** (default, always available) — the frontend sends the exact record the
   student is looking at. This is the reliable path and needs no cloud permissions.
2. **Search grounding** (on demand only) — `google_search` in the news agent, for current events.

The advisor's instruction forbids inventing numbers, and the orchestrator is told never to answer
from its own knowledge. A `null` `median_pay`/`growth` must be reported as *"not available"* —
never as `$0` or a guess.

---

## 3. How the website connects

The React app **already** POSTs to `/api/v1/analyze-major` via `src/lib/advisor.ts`. So I keep
that exact path and response key (`generated_guidance`) — **the existing frontend keeps working
with zero changes**, and the multi-agent upgrade is invisible to it.

One contract, documented in `WEBSITE_INTEGRATION.md`:

```
POST /api/v1/analyze-major
{ major_name, exposure, median_pay?, growth?, occupations[{title, exposure}], query_context }
→ { agent_node, status, generated_guidance, route, degraded }
```

`median_pay` and `growth` are **optional/nullable** — the real `public/data.json` has
`growth: null` for all 234 majors and `median_pay: null` for 9. The current frontend coerces
those to `0` / `"not available"` to dodge a 422; making them nullable server-side means the
agent learns "unknown" instead of being told pay is literally $0. That coercion is a real
grounding bug and the new contract fixes it.

---

## 4. What I verified before designing (real output, not assumptions)

Clean venv, `google-adk==2.5.0`. All confirmed present:
`Agent`/`LlmAgent` (same class), `.sub_agents`, `.tools`, `.output_key`, `before_model_callback`,
`google.adk.tools.google_search`, `AgentTool`, `FunctionTool`, `ToolContext`, `Runner`,
`InMemorySessionService` (async `create_session`), `Event.is_final_response`, `CallbackContext`.

**Live routing probe on Vertex** — the decisive test:

```
Q: What is the median pay for Business Administration?
   tools invoked: ['data_agent']          ← no billed search
Q: What's the LATEST news on AI replacing finance jobs in 2026?
   tools invoked: ['news_agent']          ← search grounding fired
```

Routing works, and `google_search` runs correctly inside an `AgentTool`-wrapped agent.

---

## 5. Where the installed API contradicts the design docs

1. **`BigQueryToolset` moved.** Docs say `from google.adk.tools.bigquery import BigQueryToolset`.
   2.5.0 emits: *"google.adk.tools.bigquery is deprecated, use google.adk.integrations.bigquery"*.
   → I use `google.adk.integrations.bigquery`.
2. **Built-in tools can't mix freely.** ADK source (`llm_agent.py`): *"the built-in tools cannot be
   used together with other tools."* 2.5.0 auto-wraps them, but relying on that is fragile.
   → `google_search` lives **alone** in `news_agent`, reached via `AgentTool`.
3. **`sub_agents` vs `AgentTool`** — see §2. Docs sketch `sub_agents`; semantics say `AgentTool`.

---

## 6. BigQuery: optional by design, because org IAM blocks it

The BigQuery Python client is blocked by org policy (`USER_PROJECT_DENIED`). So:

- **Default path = data passed in the request** (+ local `data.json` lookup). Always works.
- **BigQuery = config-gated** behind `ADVISOR_ENABLE_BIGQUERY=true` (default `false`). Off, the
  service never imports it and runs fully. Exact IAM roles to switch it on later are documented
  in `WEBSITE_INTEGRATION.md`.

The service must run 100% without BigQuery. It does.

---

## 7. Reliability & cost

- **Single-agent fallback** — if the multi-agent path throws or times out, one grounded agent
  answers instead. Response carries `degraded: true` so it's never silently pretended away.
- **Timeouts + retry** — bounded wall-clock per request; retry only transient errors.
- **Structured errors** — never a raw 500/stack trace; always typed JSON the panel can render.
- **Cost** — search fires only on current-events questions (proven in §4 and in tests).
- **Secrets** — ADC only. Nothing hardcoded.
- **CORS** — configurable allowlist, not `*`.

---

## 8. Files

```
advisor/
  config.py        # model, project, flags — one source of truth
  data_source.py   # loads public/data.json once; name lookup
  tools.py         # get_major_data, compare_majors (real, not mock)
  agents.py        # data / news / advisor / orchestrator + fallback
  runtime.py       # Runner, sessions, timeout, retry, fallback switch
  schemas.py       # the one request/response contract
  errors.py        # structured error envelope
main.py            # FastAPI wiring (keeps /api/v1/analyze-major)
tests/             # fast mocked tests + one skippable live test
```

## 9. Definition of done

Clean venv + uvicorn boots with zero import errors · a real request returns a grounded
multi-agent answer on Vertex/ADC · a news question routes to search and a simple one does not ·
pytest green · `WEBSITE_INTEGRATION.md` with a copy-paste TS fetch function.
