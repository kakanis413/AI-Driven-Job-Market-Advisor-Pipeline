from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

# Add project root to sys.path so 'advisor' imports work when executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.adk import Agent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from advisor.config import settings
from advisor.tools import (
    BQ_DATASET,
    BQ_PROJECT,
    compare_majors,
    get_ai_exposure,
    get_major_data,
    get_median_pay,
    get_top_majors,
)

log = logging.getLogger(__name__)

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
        "Fetches BOTH major/career data AND recent news/trends in parallel. "
        "Use for comprehensive career advice needing both verified stats and market trends. "
        "Input: topic (the major or career field). Returns: {data: ..., news: ...}"
    )

    def __init__(self, news_tool: AgentTool):
        super().__init__(name=self._TOOL_NAME, description=self._TOOL_DESC)
        self._news_tool = news_tool

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
- Return 3 concise bullet points with title, source, date, 1-sentence summary, and URL.
- If no news is found, state: "No significant new hiring trends reported in the last 90 days."
"""

def build_news_agent() -> Agent:
    return Agent(
        name="news_researcher",
        model=settings.model,
        description="Fetches real-time labor market news within the past 30-90 days.",
        instruction=NEWS_INSTRUCTION,
        tools=[google_search],
    )

news_agent = build_news_agent()
news_tool = AgentTool(agent=news_agent)
parallel_research_tool = ParallelResearchTool(news_tool=news_tool)


# -----------------------------------------------------------------------------
# Root Agent: Single-Turn Fast Execution Agent
# -----------------------------------------------------------------------------
ROOT_AGENT_INSTRUCTIONS = """You are an expert AI College & Career Advisor helping students understand AI's impact on their major and careers.

EFFICIENCY & STRICT TOOL ROUTING RULES:
1. DO NOT invoke BigQuery tools or `get_major_data` for course recommendations, general concepts, or skill comparisons unless exact numeric wages/stats are explicitly requested.
2. If 'PRE-LOADED TOP MAJORS DATA' or 'CONTEXT FOR THIS MAJOR' is present in prompt context, use it immediately without extra tool calls.
3. Perform AT MOST ONE tool call total per user request. Never make back-to-back tool calls.
4. Keep answers concise (max 2-3 short paragraphs or bullet points) to optimize streaming delivery speed.

RESPONSE FORMATTING:
- Lead directly with the answer—no long preambles.
- Structure clearly using markdown headers and bullet points.
- High AI exposure means task mix shifts, NOT immediate job loss.
"""

root_agent = Agent(
    name="college_advisor",
    model=settings.model,
    description="Advises students on college majors, AI exposure, and career outlook.",
    instruction=ROOT_AGENT_INSTRUCTIONS,
    tools=[
        parallel_research_tool,
        get_major_data,
        compare_majors,
        get_median_pay,
        get_ai_exposure,
        get_top_majors,
    ],
)