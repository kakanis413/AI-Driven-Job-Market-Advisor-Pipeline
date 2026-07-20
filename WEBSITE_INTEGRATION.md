# Website ↔ Advisor Integration

How the React frontend talks to the FastAPI advisor service. This is the contract — if
either side changes, update this file and the tests in `tests/test_endpoints_mocked.py`.

---

## 1. The one endpoint

```
POST /api/v1/analyze-major
```

That's the only endpoint the website calls. (`/api/v1/ask-major` no longer exists — the
advisor package consolidated to a single route.)

Two support routes for humans/ops:
- `GET /` — liveness: `{"status":"ok","service":...,"version":...}`
- `GET /healthz` — config check: model, vertex on/off, majors loaded, multi_agent, news, bigquery

---

## 2. Request contract

The frontend sends **the clicked major's record + the student's question**.

```jsonc
{
  "major_name": "Computer Science",   // required, 1–200 chars
  "cip": "11.0701",                   // optional, may be null
  "exposure": 8.4,                    // optional, 0–10 (NOT 0–1), may be null
  "median_pay": 125831,               // optional integer USD, may be null
  "growth": "faster",                 // optional: declining|slower|average|faster, may be null
  "occupations": [                    // optional, may be [] (max 50)
    { "soc": "15-1252", "title": "Software Developers", "exposure": 9.0 }
  ],
  "query_context": "Is this risky?"   // required — the student's question, 1–2000 chars
}
```

**Send real nulls, never placeholders.** `median_pay: null` and `growth: null` are valid and
are reported to the agent as *"not available."* Coercing them to `0` or `"not available"`
strings tells the advisor pay is literally $0 — a grounding bug. (`median_pay: 0` is
defensively converted to `null` server-side for the same reason.)

**Exposure is 0–10.** A 0–1 normalized value will fail validation with 422. The frontend's
`normalizeMajors.ts` handles the rescale before data reaches this call.

---

## 3. Response contract

```jsonc
{
  "agent_node": "college_advisor",
  "status": "active_reasoning",      // or "degraded"
  "generated_guidance": "…",         // the text to render in the chat panel
  "route": { … },                    // which agents ran, whether search fired
  "degraded": false                  // true = the single-agent fallback answered
}
```

Read **`generated_guidance`**. `degraded: true` means the multi-agent path failed and the
fallback answered — still a valid answer, worth surfacing subtly if you want.

Errors return a structured envelope (never a raw 500/stack trace); the client throws on a
non-2xx so the panel can show its error state.

---

## 4. Frontend wiring

**Env var** (`.env` at the repo root):
```
VITE_AGENT_URL=http://localhost:8000/api/v1/analyze-major
```

> ⚠️ This is the **full endpoint URL**, not a base URL — `src/lib/advisor.ts` fetches
> `VITE_AGENT_URL` directly and does not append a path. Setting it to
> `http://localhost:8000` produces `POST /` → **405 Method Not Allowed**.
> Vite reads `.env` only at startup: **restart `npm run dev` after changing it.**

**The client** lives in `src/lib/advisor.ts` (`askAdvisor({ major, message })`). It:
- returns an "offline preview" echo when `VITE_AGENT_URL` is unset or no major is selected —
  clearly labeled so it's never mistaken for a real answer,
- otherwise POSTs the body above and returns `generated_guidance`.

`advisorIsLive` is exported so the UI can show a live/offline badge.

---

## 5. Running it locally

Two terminals:

```bash
# 1) backend
source .venv/bin/activate
uvicorn main:app --reload          # http://localhost:8000  (docs at /docs)

# 2) frontend
npm run dev                        # http://localhost:5173
```

Backend `.env` needs (Vertex via ADC — no API keys):
```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=sprinternship-sea-2026
GOOGLE_CLOUD_LOCATION=global
```

Authenticate once with `gcloud auth application-default login`. **ADC tokens expire** — a
`RefreshError: Reauthentication is needed` in the server log just means re-run that command.

> The `set-quota-project` warning about `serviceusage.services.use` is a **red herring** for
> Gemini. Vertex names the project in the request and checks `aiplatform` permissions, so
> model calls work without it. (It does block the BigQuery *Python client* — hence
> `ADVISOR_ENABLE_BIGQUERY` defaults to off.)

---

## 6. Useful backend env vars

| Var | Default | Purpose |
|---|---|---|
| `ADVISOR_MODEL` | `gemini-3.5-flash` | model id |
| `ADVISOR_DATA_FILE` | `advisor/data/majors.json` | the agent's major lookup |
| `ADVISOR_CORS_ORIGINS` | — | comma-separated allowlist (tighten before deploy) |
| `ADVISOR_ENABLE_BIGQUERY` | `false` | gated: needs IAM roles below |
| `ADVISOR_MAX_RETRIES` | `2` | transient-error retries |
| `ADVISOR_LOG_LEVEL` | `INFO` | logging |

To enable BigQuery later, the running identity needs `roles/serviceusage.serviceUsageConsumer`,
`roles/bigquery.jobUser`, and `roles/bigquery.dataViewer` on the project.

---

## 7. Verifying the loop

```bash
curl -s -X POST http://localhost:8000/api/v1/analyze-major \
  -H 'Content-Type: application/json' \
  -d '{"major_name":"Computer Science","exposure":8.4,"median_pay":125831,
       "growth":"faster","occupations":[{"soc":"15-1252","title":"Software Developers","exposure":9.0}],
       "query_context":"Is this risky?"}'
```

A healthy server log line looks like:
```
response | path=multi_agent agents=['advisor_agent'] search=False latency=11441ms degraded=False
```
`search=False` on a non-news question is correct — the orchestrator only calls the search
agent when the question needs current events, which keeps cost down.

Fast tests (no Gemini calls): `pytest tests/ -q`. Live test: `RUN_LIVE=1 pytest -m live`.

---

## 8. Known gaps

- **`occupations` is empty for most majors.** Only 24 of 376 records in
  `advisor/data/majors.json` have occupations or a `cip`. Until the pipeline's crosswalk join
  populates them, the advisor can't reference specific occupations for those majors and the
  detail card's occupation list renders empty. This needs real pipeline data — do not
  hand-fill it.
- **Latency ~11s** on the multi-agent path (several sequential model calls). Show a loading
  state, or stream, before demoing.
