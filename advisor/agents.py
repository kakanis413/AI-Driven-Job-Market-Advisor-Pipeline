"""The agent roster: data / news / advisor specialists + the LLM-routed orchestrator.

Design note (verified against google-adk 2.5.0, not assumed):
we compose specialists with `AgentTool`, NOT `sub_agents`. `sub_agents` performs an LLM
*transfer* — control moves to the sub-agent and it becomes the responder. Our flow is
gather-then-synthesize: the orchestrator needs the data agent's facts handed *back* so it
can compose the final answer. `AgentTool` returns control; transfer does not.

`google_search` is a built-in tool and ADK warns that built-ins "cannot be used together
with other tools", so it lives alone in `news_agent`, reached via AgentTool.
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from advisor.config import settings
from advisor.tools import build_bigquery_toolset, compare_majors, get_major_data

log = logging.getLogger(__name__)

# The product rule, stated once and reused so every path enforces it identically.
FRAMING_RULE = (
    "CRITICAL FRAMING: a high AI exposure score does NOT mean the job disappears. "
    "Exposure measures how transformable the *work* is by AI, not whether the occupation "
    "is eliminated. Always make this distinction explicit. The work changes; the job "
    "does not vanish."
)

GROUNDING_RULE = (
    "GROUNDING (absolute): state only numbers present in the data you were given or that a "
    "tool returned. Never invent or estimate an exposure score, salary, or growth figure. "
    "If a value is 'not available', say it is not available - never guess, and never report "
    "it as zero. If asked about a major that is not in the data, say so plainly."
)


def _cfg(temperature: float) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(temperature=temperature)


class ResilientAgentTool(AgentTool):
    """AgentTool whose failure degrades instead of aborting the whole run.

    A transient error inside a wrapped agent (e.g. a google_search hiccup in
    news_agent) would otherwise propagate out of the orchestrator's runner,
    burn the retry budget, and surface as a 5xx. Catching it here returns a
    structured result, so the orchestrator sees "that tool is unavailable"
    as a fact it can route around — answer without news, don't fail.
    """

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        try:
            return await super().run_async(args=args, tool_context=tool_context)
        except Exception as exc:  # noqa: BLE001 - degrade, never abort the run
            name = getattr(self.agent, "name", "agent")
            log.warning("agent tool %s failed; continuing without it: %s", name, exc)
            return {
                "status": "unavailable",
                "agent": name,
                "message": (
                    f"{name} could not complete (transient error). "
                    "Answer without its input and do not invent what it would have said."
                ),
            }


def build_data_agent() -> LlmAgent:
    """Facts only. Reads the same data.json the browser renders."""
    tools = [get_major_data, compare_majors, *build_bigquery_toolset()]
    return LlmAgent(
        name="data_agent",
        model=settings.model,
        description=(
            "Returns hard facts for a college major: AI exposure score, median pay, growth "
            "outlook, and the occupations it feeds into. Also compares two majors. "
            "Facts only - no advice."
        ),
        instruction=(
            "You retrieve facts about college majors.\n"
            "- Call get_major_data for one major; call compare_majors for two.\n"
            "- Report exactly what the tool returned, as a compact factual summary.\n"
            "- If the tool says not_found, say so and list did_you_mean. Invent nothing.\n"
            "- Give no career advice and no opinions. Facts only."
        ),
        tools=tools,
        generate_content_config=_cfg(0.0),
    )


def build_news_agent() -> LlmAgent:
    """Search-grounded current events. google_search is its ONLY tool (built-in constraint)."""
    return LlmAgent(
        name="news_agent",
        model=settings.model,
        description=(
            "Finds RECENT, cited news about AI's effect on a field or occupation. "
            "Use ONLY for questions about current events, latest developments, or trends."
        ),
        instruction=(
            "You find recent, credible signal about AI and the labour market.\n"
            "- Use google_search for 2-3 recent, relevant items.\n"
            "- Summarize briefly and cite the source of each claim.\n"
            "- If there is no notable recent signal, say exactly that. Never invent news.\n"
            f"- {FRAMING_RULE}"
        ),
        tools=[google_search],
        generate_content_config=_cfg(0.1),
    )


def build_advisor_agent() -> LlmAgent:
    """Writes the student-facing answer. No external tools — its skill is reasoning + voice."""
    return LlmAgent(
        name="advisor_agent",
        model=settings.model,
        description=(
            "Writes the final student-facing career guidance from facts already gathered. "
            "Call this LAST, and pass it the facts (and any news) you collected."
        ),
        instruction=(
            "You are an elite, warm academic advisor writing to one student.\n"
            f"{GROUNDING_RULE}\n"
            f"{FRAMING_RULE}\n"
            "Style:\n"
            "- 3-5 short, conversational paragraphs. No bullet lists, no headers.\n"
            "- Reference the specific occupations you were given by name - not generic advice.\n"
            "- Be honest about risk, then constructive about what to do with it.\n"
            "- If news context was provided, weave it in and keep its citations.\n"
            "- Never mention agents, tools, or that you were 'given data'. Just advise."
        ),
        generate_content_config=_cfg(0.4),
    )


def build_orchestrator() -> LlmAgent:
    """The router. Decides per question which specialists to call, then composes."""
    tools = [
        AgentTool(agent=build_data_agent()),
        AgentTool(agent=build_advisor_agent()),
    ]
    news_line = (
        "- Call news_agent ONLY if the question asks about recent trends, current events, "
        "the latest developments, or what is happening 'now'/'lately'. Searching costs "
        "money and time: SKIP it for factual, definitional, or comparative questions.\n"
        "- If news_agent returns status 'unavailable', continue WITHOUT news: answer from "
        "the verified data, note briefly that live news could not be fetched right now, "
        "and never invent headlines or trends.\n"
        if settings.enable_news
        else ""
    )
    if settings.enable_news:
        # Resilient: a search hiccup must degrade to "no news", never a 5xx.
        tools.insert(1, ResilientAgentTool(agent=build_news_agent()))

    return LlmAgent(
        name="college_advisor",
        model=settings.model,
        description="Coordinates specialists to answer a student's question about a major.",
        instruction=(
            "You coordinate a team of specialist agents to answer one student's question "
            "about a college major. You never answer from your own knowledge.\n\n"
            "The user message contains a VERIFIED DATA block for the major the student "
            "clicked. That block is authoritative.\n\n"
            "Routing rules:\n"
            "- If the VERIFIED DATA block answers the question, you do NOT need data_agent.\n"
            "- Call data_agent when you need facts beyond that block: a different major, a "
            "comparison between majors, or a major the student names that is not in the block.\n"
            f"{news_line}"
            "- ALWAYS finish by calling advisor_agent to write the answer. Pass it the "
            "verified data, plus anything data_agent or news_agent returned.\n"
            "- Return advisor_agent's text as your final answer, essentially verbatim.\n\n"
            f"{GROUNDING_RULE}\n"
            f"{FRAMING_RULE}"
        ),
        tools=tools,
        generate_content_config=_cfg(0.2),
    )


def build_single_agent() -> LlmAgent:
    """Internal fallback: one grounded agent, no routing, no search.

    Deliberately minimal — it exists so a multi-agent hiccup cannot take the service down.
    """
    return LlmAgent(
        name="college_advisor_fallback",
        model=settings.model,
        description="Single-agent grounded advisor (fallback path).",
        instruction=(
            "You are an elite, warm academic advisor writing to one student.\n"
            "The user message contains a VERIFIED DATA block. It is your only source of "
            "numbers.\n"
            f"{GROUNDING_RULE}\n"
            f"{FRAMING_RULE}\n"
            "Write 3-5 short, conversational paragraphs. Reference the specific occupations "
            "by name. No bullet lists, no headers. Never mention tools or agents."
        ),
        tools=[get_major_data],
        generate_content_config=_cfg(0.4),
    )
