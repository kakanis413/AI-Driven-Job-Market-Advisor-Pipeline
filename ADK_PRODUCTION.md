# ADK in Production — What It Buys Us, and Why the Agent Is Built This Way

Companion to `PLAN.md` / `AGENT_ARCHITECTURE.md`. Every claim below was verified
against the **installed `google-adk` 2.5.0** (`.venv`, Python 3.12) by importing
the symbol or reading the package source — cited as `path:line` under
`site-packages/google/adk/`. Where older design docs disagree with the installed
package, the package wins.

---

## 1. What ADK gives us over plain Gemini calls

A raw `google-genai` integration would make one `generateContent` call. Our
advisor needs a *loop*: the model decides to call a tool, we execute it, feed
the result back, and repeat until a final answer. ADK owns that loop so we
don't hand-roll it:

- **The tool-calling loop.** `Runner.run_async(...)` yields a stream of
  `Event`s; function calls appear as `content.parts[*].function_call`, tool
  results are fed back automatically, and `event.is_final_response()` marks the
  end. `advisor/runtime.py` consumes exactly this stream — it's also how we get
  routing telemetry (`RouteInfo.agents_called`) for free, by watching which
  `function_call` names go past.
- **Python functions as tools, schema included.** `get_major_data` and
  `compare_majors` in `advisor/tools.py` are plain typed functions; ADK builds
  the `FunctionDeclaration` from the signature + docstring. No JSON schema by
  hand.
- **Agents as tools** (`AgentTool`) — the composition primitive the whole
  orchestrator is built on (§2).
- **Built-in Google Search grounding** (`google.adk.tools.google_search`) —
  billed, search-grounded answers with no custom search API integration (§3).
- **Session plumbing.** `InMemorySessionService` + `Runner` give us per-request
  conversation state without writing any of it.

What ADK does **not** give us — and why `advisor/runtime.py` exists: wall-clock
timeouts, retry with backoff, the multi-agent → single-agent fallback, typed
error envelopes (`advisor/errors.py`), and degradation of a flaky sub-agent
(`ResilientAgentTool`, §5). That reliability layer is ours.

---

## 2. Why `AgentTool`, not `sub_agents`

Both exist in 2.5.0; they have different control flow, and the difference is
the whole design:

- **`sub_agents=[...]` is a transfer.** When an agent has sub-agents, ADK wires
  a `TransferToAgentTool` into the request
  (`flows/llm_flows/agent_transfer.py:29,51`): the LLM calls
  `transfer_to_agent`, control *moves* to the sub-agent, and the sub-agent
  becomes the responder. Control does not naturally come back with a result.
- **`tools=[AgentTool(agent=...)]` is a call.** `AgentTool._get_declaration`
  turns the wrapped agent into an ordinary function declaration — and
  explicitly sets `result.description = self.agent.description`
  (`tools/agent_tool.py`). At call time, `AgentTool.run_async(*, args,
  tool_context)` spins up an internal `Runner`, runs the wrapped agent to
  completion, and **returns its output to the caller** like any tool result.

Our flow is *gather → synthesize*: the orchestrator must get the data agent's
facts (and maybe the news agent's citations) **handed back**, then pass them to
the advisor agent to write the final answer. That is `AgentTool` semantics.
With `sub_agents`, control would leave the orchestrator and the composition
step would never run.

---

## 3. Why `google_search` sits alone in its own agent

The ADK source states it three times (`agents/llm_agent.py:149,160,744`):

> *"the built-in tools cannot be used together with other tools."*

`google_search` is a built-in (executed server-side by Gemini, not by ADK), so
it cannot share an agent with `get_major_data`/`compare_majors`. 2.5.0 has
code paths that auto-wrap built-ins to soften this, but the constraint is still
in the model-request builder — relying on the workaround is fragile.

So `news_agent` holds `google_search` as its **only** tool, and the
orchestrator reaches it through `AgentTool`. That isolation also matches the
product rules: search-grounded output must cite sources, is slow (~seconds),
and is billed — a separate agent is independently promptable, testable, and
skippable.

---

## 4. How the orchestrator picks a sub-agent

There is no routing table. Each specialist becomes a function declaration whose
name is the agent's `name` and whose description is the agent's `description`
(verified in `AgentTool._get_declaration`, §2). Routing **is** Gemini's
function calling: the orchestrator model reads the student's question and the
three declarations, and emits `function_call`s for the ones it needs.

We steer that choice in two places, both in `advisor/agents.py`:

1. **Specialist descriptions** are written as routing hints — e.g. news_agent's
   description says "Use ONLY for questions about current events."
2. **The orchestrator instruction** sets policy: don't call `data_agent` if the
   request's verified-data block already answers; call `news_agent` only for
   current-events questions (search costs money); ALWAYS finish by calling
   `advisor_agent` and return its text.

`PLAN.md` §4 recorded the live probe: a pay question invoked only
`data_agent`; a "latest news" question invoked `news_agent`. The
`route.agents_called` field in every response makes this auditable per request.

---

## 5. Failure containment: `ResilientAgentTool`

A transient failure inside a sub-agent (in practice: a `google_search` hiccup
in news_agent) would propagate out of the orchestrator's run, burn the retry
budget re-running billed searches, and could surface as a 5xx.
`ResilientAgentTool` (in `advisor/agents.py`) overrides
`AgentTool.run_async` — signature verified: `(self, *, args: dict, tool_context:
ToolContext) -> Any` — to catch any exception and return
`{"status": "unavailable", ...}` instead. The orchestrator's instruction tells
it to treat that as a fact: answer from the verified data, say live news
couldn't be fetched, invent nothing. The single-agent fallback in `runtime.py`
remains the net under everything else.

---

## 6. 2.5.0 gotchas we verified (don't trust older docs)

| Claim in older docs | What installed 2.5.0 actually does |
|---|---|
| `from google.adk.tools.bigquery import ...` | Deprecation warning on import: *"google.adk.tools.bigquery is deprecated, use google.adk.integrations.bigquery instead"* — we use `integrations` (and gate it off entirely; org IAM blocks the BQ Python client). |
| "An agent with `output_schema` cannot also use tools" (`AGENT_ARCHITECTURE.md` §6.5) | `agents/llm_agent.py:394`: *"The ADK supports using `output_schema` and `tools` together"* — tools run during the thought loop, structure is enforced on the final output. Our split (schema'd batch analyst vs. tool-using advisor) still stands for clarity, but it is no longer forced by the framework. |
| `Agent(..., sub_agents=[...])` sketch for the orchestrator | Wires transfer, not call-and-return (§2) — wrong for gather→synthesize. |

The habit that keeps this document true: **before using an ADK symbol, import
it from the installed package and read its source.** The docs lag; the package
doesn't.
