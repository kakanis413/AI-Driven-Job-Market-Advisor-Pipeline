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
    get_bigquery_toolset,
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
    what makes streaming actually feel instant; without this, streaming just
    delivers a slow answer in pieces. See Settings.thinking_level for measurements.
    """
    return BuiltInPlanner(
        thinking_config=types.ThinkingConfig(thinking_level=settings.thinking_level)
    )

# Configure root logger for millisecond accuracy
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Enable ADK framework logging
logging.getLogger("google.adk").setLevel(logging.INFO)


# -----------------------------------------------------------------------------
# Resilient wrapper: a failing specialist degrades, it never aborts the turn
# -----------------------------------------------------------------------------
class ResilientAgentTool(AgentTool):
    """An AgentTool whose failures come back as data, not exceptions.

    google_search is the flakiest hop in the chain (rate limits, transient 5xx).
    Letting that bubble up would 5xx a request whose *answer* never needed news.
    Returning a structured "unavailable" lets the root agent route around it —
    the root instruction tells it to answer from the grounding block instead.
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


# -----------------------------------------------------------------------------
# Optimized Parallel Research Tool: Direct Local Python Lookup + Fast Web Search
# -----------------------------------------------------------------------------
class ParallelResearchTool(BaseTool):
    """Runs local python data lookups and web news concurrently.

    Directly executes get_major_data in Python (<5ms) to eliminate LLM hop latency,
    while fetching news concurrently.
    """

    _TOOL_NAME: str = "parallel_research"
    _TOOL_DESC: str = (
        "THE tool for any question about what is happening recently or right now: "
        "current hiring, layoffs, latest trends, this year's market, named companies. "
        "Fetches major/career data AND live news in parallel. Local data alone cannot "
        "answer recency questions — use this instead of get_major_data whenever the "
        "question is time-sensitive. "
        "Input: topic (the major or career field). Returns: {data: ..., news: ...}"
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

        # Direct, instant local python lookup (No LLM overhead)
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

        # Run local python lookup and news search in parallel
        data_result, news_result = await asyncio.gather(
            fetch_data_direct(),
            self._safe_run_news(news_request, tool_context),
        )

        return {
            "data": data_result,
            "news": news_result,
        }


# -----------------------------------------------------------------------------
# News Agent Specialist (Strict 1-Turn Enforcement)
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
    return Agent(
        name="news_researcher",
        model=settings.model,
        description="Fetches real-time labor market news within the past 30-90 days.",
        instruction=NEWS_INSTRUCTION,
        planner=fast_planner(),
        tools=[google_search],
    )

news_agent = build_news_agent()
news_tool = ResilientAgentTool(agent=news_agent)
parallel_research_tool = ParallelResearchTool(news_tool=news_tool)


# -----------------------------------------------------------------------------
# Root Agent: Single-Turn Fast Execution Agent
# -----------------------------------------------------------------------------
ROOT_AGENT_INSTRUCTIONS = f"""You are an expert AI College & Career Advisor helping students understand AI's impact on their major and careers.

TOOL BUDGET — every tool call costs the student seconds of waiting.
1. A 'CONTEXT FOR THIS MAJOR' or 'PRE-LOADED TOP AI EXPOSURE DATA' block is the
   student's own screen. Those numbers OUTRANK anything a tool returns — quote them
   verbatim, and never contradict them with a different figure for the same field.
   If such a block answers the question, call NO tools at all.
2. If it does not, first use the single most appropriate local tool (get_major_data,
   compare_majors, get_median_pay, get_ai_exposure, get_top_majors). These are instant.
   If that tool succeeds and contains the requested information, answer immediately
   and do NOT query BigQuery.
3. For questions about what is happening lately — "who is hiring", "recent layoffs",
   "latest trends", "this year's market" — call `get_recent_news`. It is instant.
4. Call `parallel_research` ONLY when the question is scoped to a specific school
   (a 'UNIVERSITY CONTEXT' block is present) or names a specific company, because
   only it can search the live web. It costs ~7 seconds, so it is the last resort:
   if `get_recent_news` returns items that answer the question, stop there.
5. Do NOT reach for news at all on evaluative or advice questions, even ones that
   sound current — "is this major still worth it", "should I switch majors", "how do
   I prepare", "what does my exposure score mean" are answerable from the data above.
   When in doubt, answer without news. Rule 1 always wins: if the context block
   answers the question, no tool call is justified.
6. BIGQUERY IS A DATA FALLBACK. If the appropriate local tool returns
   status="not_found", or its successful result lacks the information required to
   answer the question, use the BigQuery tools yourself. There is no separate data
   agent. Never use BigQuery before attempting the most appropriate local tool,
   including for filtering, aggregation, ranking, or join requests.
7. BigQuery project: `{settings.project}`. Dataset: `{settings.bigquery_dataset}`.
   Generate SELECT queries only, use fully qualified table names, inspect schema when
   unsure of column names, select only needed columns, and use LIMIT for non-aggregate
   queries. Never modify data and never invent results when a query returns no rows.
8. Never call the same tool twice and never call a tool after you have begun writing
   the answer. Use at most one final BigQuery data query when practical.

WHEN A TOOL DEGRADES:
- A local data tool returning status="not_found" triggers the BigQuery fallback.
- If BigQuery or a news tool returns status="unavailable", say so plainly and answer
  only from verified data already available.
- Never invent numbers, headlines, or dates.

RESPONSE FORMATTING:
- Lead with the answer. No preamble, no restating the question, no "great question".
  The first sentence carries the number or the verdict.
- 2-3 tight paragraphs, max 3 sentences each. Markdown headers/bullets only when they
  genuinely aid scanning.
- High AI exposure means the task mix shifts, NOT immediate job loss. Keep that framing
  present, but do not open with it every time.
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
        get_recent_news,
        get_bigquery_toolset(),
    ],
)
