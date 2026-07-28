from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

# Add project root to sys.path so 'advisor' imports work when executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.adk import Agent
from google.adk.planners import BuiltInPlanner
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from advisor.config import settings
from advisor.tools import (
    compare_majors,
    get_ai_exposure,
    get_dynamic_top_careers,
    get_major_data,
    get_median_pay,
    get_recent_news,
    get_top_majors,
)

log = logging.getLogger(__name__)


def fast_planner() -> BuiltInPlanner:
    """Cap the model's thinking budget.

    Thinking happens entirely before the first output token, so it is pure
    time-to-first-token — the exact thing streaming is meant to fix. Capping it is
    what makes streaming actually feel instant; without it, streaming just delivers
    a slow answer in pieces. See Settings.thinking_level for measurements.
    """
    return BuiltInPlanner(
        thinking_config=types.ThinkingConfig(thinking_level=settings.thinking_level)
    )


# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Enable ADK framework logging
logging.getLogger("google.adk").setLevel(logging.INFO)


# -----------------------------------------------------------------------------
# Parallel Research Tool: Direct Python Lookup + Fast Web Search
# -----------------------------------------------------------------------------
class ParallelResearchTool(BaseTool):
    """Runs local python data lookups and web news concurrently."""

    _TOOL_NAME: str = "parallel_research"
    _TOOL_DESC: str = (
        "Searches the live web. Use only when the question is scoped to a specific "
        "school or names a specific company — `get_recent_news` covers general "
        "recency questions instantly. Fetches major/career data AND live news in "
        "parallel. Input: topic (the major or career field). "
        "Returns: {data: ..., news: ...}"
    )

    def __init__(self, news_tool: AgentTool):
        super().__init__(name=self._TOOL_NAME, description=self._TOOL_DESC)
        self._news_tool = news_tool

    def _get_declaration(self) -> types.FunctionDeclaration:
        """Advertise the tool to the model.

        BaseTool's default returns None, which makes ADK omit the tool from the
        request entirely — the model cannot call what it was never shown. Without
        this the news path is unreachable no matter what the instructions say, and
        recency questions get silently answered from stale local data.
        """
        return types.FunctionDeclaration(
            name=self._TOOL_NAME,
            description=self._TOOL_DESC,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "topic": types.Schema(
                        type=types.Type.STRING,
                        description="The major or career field to research, e.g. 'Computer science'.",
                    )
                },
                required=["topic"],
            ),
        )

    async def _safe_run_news(
        self, args: dict[str, Any], ctx: ToolContext
    ) -> Any:
        try:
            return await self._news_tool.run_async(args=args, tool_context=ctx)
        except Exception as exc:
            log.warning("Parallel research: news lookup failed: %s", exc)
            return {
                "status": "unavailable",
                "message": "Live news temporarily unavailable.",
            }

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        topic = args.get("topic") or args.get("query") or args.get("request") or ""

        async def fetch_data_direct():
            try:
                data = get_major_data(topic)
                if data and data != "not_found":
                    return data
            except Exception:
                pass
            return f"Data lookup for '{topic}' completed."

        news_request = {"request": f"Find recent hiring trends and news for: {topic}"}

        log.info("parallel_research: starting concurrent fetch for %r", topic)

        data_result, news_result = await asyncio.gather(
            fetch_data_direct(),
            self._safe_run_news(news_request, tool_context),
        )

        return {
            "data": data_result,
            "news": news_result,
        }


# -----------------------------------------------------------------------------
# News Agent Specialist (Strict Single Search)
# -----------------------------------------------------------------------------
NEWS_INSTRUCTION = """You are a real-time labor market news specialist.
Given a topic, search for recent hiring trends and demand shifts within the past 30-90 days.

CRITICAL PERFORMANCE RULES:
- Perform AT MOST ONE search operation.
- Do NOT run multi-turn or follow-up searches.
- Stay strictly factual: every claim must trace to a search result you actually got.
- Return 3 concise bullet points with title, source, date, 1-sentence summary, and URL.
- If no news is found, state: "No significant new hiring trends reported in the last 90 days."
"""

def build_news_agent() -> Agent:
    # Deliberately NO planner. Capping this agent's thinking to MINIMAL makes it
    # skip the google_search call and answer from memory: grounding_chunks comes
    # back empty, so every item fails the "URL must trace to a chunk" rule in
    # _join_items_to_chunks and the whole feed drops to zero items. Measured on
    # Business: 0 chunks with the planner, 3 with it removed. The root agent is the
    # opposite case — it reads a grounding block it was handed and needs no search
    # decision, so fast_planner() belongs there and only there.
    return Agent(
        name="news_researcher",
        model=settings.model,
        description="Fetches real-time labor market news within the past 30-90 days.",
        instruction=NEWS_INSTRUCTION,
        tools=[google_search],
    )

class ResilientAgentTool(AgentTool):
    """An AgentTool whose failures come back as data, not exceptions.

    google_search is the flakiest hop in the chain (rate limits, transient 5xx).
    Letting that raise would 5xx a request whose answer never needed news at all.
    A structured "unavailable" lets the root agent route around it and answer from
    the grounding block instead.
    """

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        try:
            return await super().run_async(args=args, tool_context=tool_context)
        except Exception as exc:
            log.warning("news specialist degraded: %s", exc)
            return {
                "status": "unavailable",
                "agent": self.agent.name,
                "message": (
                    "Live news is temporarily unavailable. Answer from the verified "
                    "data you already have and say recent news could not be checked — "
                    "do NOT invent headlines, companies, or dates."
                ),
            }


news_agent = build_news_agent()
news_tool = ResilientAgentTool(agent=news_agent)
parallel_research_tool = ParallelResearchTool(news_tool=news_tool)


# -----------------------------------------------------------------------------
# Root Agent: Single-Turn Fast Execution Agent
# -----------------------------------------------------------------------------
ROOT_AGENT_INSTRUCTIONS = """You are an expert AI College & Career Advisor helping students understand AI's impact on their major and careers.

EFFICIENCY & STRICT TOOL ROUTING RULES — every tool call costs the student seconds.
1. A 'CONTEXT FOR THIS MAJOR' or 'PRE-LOADED TOP AI EXPOSURE DATA' block is the
   student's own screen. Those numbers outrank anything a tool returns — quote them
   verbatim. If such a block answers the question, call NO tools at all.
2. Otherwise use the single most appropriate local tool (get_major_data,
   compare_majors, get_median_pay, get_ai_exposure, get_top_majors). These are
   instant. Do not call one for course recommendations, general concepts, or skill
   comparisons unless exact numeric wages or stats are requested.
3. For what is happening lately — "who is hiring", "recent layoffs", "latest
   trends" — call `get_recent_news`. It is instant.
4. Call `parallel_research` ONLY when the question is scoped to a specific school
   (a 'UNIVERSITY CONTEXT' block is present) or names a specific company. It is the
   only tool that searches the live web, and it costs ~7 seconds.
5. Do NOT reach for news on evaluative questions that merely sound current — "is
   this major still worth it", "should I switch", "what does my score mean" are
   answerable from the data above. When in doubt, answer without news.
6. Perform AT MOST ONE tool call per request. Never call a tool after you have
   begun writing the answer.

TOP CAREER QUESTIONS:
- For the top, best, or most promising careers within a major, call
  get_dynamic_top_careers — not get_top_majors, which ranks majors instead.
- Preserve its exact order. Never invent, replace, or reorder careers.
- Present each career's title, median annual pay, and projected growth.
- If status is "partial", say fewer than the requested number were verified. If it
  is "no_data" or "not_found", say so instead of manufacturing a Top 3.

WHEN A TOOL DEGRADES:
- If a tool returns status="unavailable" or "not_found", say so plainly and answer
  only from verified data you already have.
- Never invent numbers, headlines, companies, or dates.

RESPONSE FORMATTING:
- Lead directly with the answer — no preamble, no restating the question. The first
  sentence carries the number or the verdict.
- 2-3 short paragraphs. Markdown headers and bullets only where they aid scanning.
- High AI exposure means the task mix shifts, NOT immediate job loss.
"""

root_agent = Agent(
    name="college_advisor",
    model=settings.model,
    description="Advises students on college majors, AI exposure, and career outlook.",
    instruction=ROOT_AGENT_INSTRUCTIONS,
    planner=fast_planner(),
    tools=[
        parallel_research_tool,
        get_major_data,
        compare_majors,
        get_median_pay,
        get_ai_exposure,
        get_top_majors,
        get_dynamic_top_careers,
        get_recent_news,
    ],
)