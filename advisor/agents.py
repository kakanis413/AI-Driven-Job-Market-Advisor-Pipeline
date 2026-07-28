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
    """Cap the model's thinking budget to minimize time-to-first-token."""
    return BuiltInPlanner(
        thinking_config=types.ThinkingConfig(thinking_level=settings.thinking_level)
    )


# Configure loggers
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("google.adk").setLevel(logging.INFO)


# -----------------------------------------------------------------------------
# Parallel Research Tool (Strictly Guarded against General Enquiries)
# -----------------------------------------------------------------------------
class ParallelResearchTool(BaseTool):
    """Runs local python data lookups and web news concurrently."""

    _TOOL_NAME: str = "parallel_research"
    _TOOL_DESC: str = (
        "EXTREMELY SLOW WEB SEARCH (7-15s delay). "
        "DO NOT USE for general questions, classes, advice, salaries, majors, or follow-ups. "
        "Use ONLY if user explicitly types words like 'search the web' or 'live news'."
    )

    def __init__(self, news_tool: AgentTool):
        super().__init__(name=self._TOOL_NAME, description=self._TOOL_DESC)
        self._news_tool = news_tool

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self._TOOL_NAME,
            description=self._TOOL_DESC,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "topic": types.Schema(
                        type=types.Type.STRING,
                        description="The major or career field to research.",
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
# News Specialist
# -----------------------------------------------------------------------------
NEWS_INSTRUCTION = """You are a real-time labor market news specialist.
Given a topic, search for recent hiring trends and demand shifts within the past 30-90 days.

CRITICAL PERFORMANCE RULES:
- Perform AT MOST ONE search operation.
- Do NOT run multi-turn or follow-up searches.
- Return 3 concise bullet points with title, source, date, 1-sentence summary, and URL.
"""

def build_news_agent() -> Agent:
    return Agent(
        name="news_researcher",
        model=settings.model,
        description="Fetches real-time labor market news within the past 30-90 days.",
        instruction=NEWS_INSTRUCTION,
        tools=[google_search],
    )

class ResilientAgentTool(AgentTool):
    """An AgentTool whose failures come back as data, not exceptions."""

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        try:
            return await super().run_async(args=args, tool_context=tool_context)
        except Exception as exc:
            log.warning("news specialist degraded: %s", exc)
            return {
                "status": "unavailable",
                "agent": self.agent.name,
                "message": "Live news is temporarily unavailable.",
            }


news_agent = build_news_agent()
news_tool = ResilientAgentTool(agent=news_agent)
parallel_research_tool = ParallelResearchTool(news_tool=news_tool)


# -----------------------------------------------------------------------------
# Root Agent: Ultra-Fast Global Decision Policy
# -----------------------------------------------------------------------------
ROOT_AGENT_INSTRUCTIONS = """You are an expert AI College & Career Advisor designed for high-speed, instant responses.

GLOBAL LOW-LATENCY ROUTING STRATEGY (Target < 2s TTFT):

1. DEFAULT TO DIRECT INSTANT ANSWER (ZERO TOOL CALLS):
   - For classes, course planning, major comparison thoughts, career advice, transition tips, or general "how to prepare" questions, answer IMMEDIATELY from built-in knowledge.
   - If numbers/data are present in the UI context block or past turns, answer directly without invoking tools.

2. FAST LOCAL PYTHON DATA LOOKUPS (< 200ms):
   - Only call a tool if specific numerical statistics are needed that are NOT in context:
     * Specific wage/pay numbers -> `get_median_pay`
     * Top career lists -> `get_dynamic_top_careers`
     * General major stats -> `get_major_data`
     * AI Exposure scores -> `get_ai_exposure`
     * Major ranking lists -> `get_top_majors`
     * Major comparison metrics -> `compare_majors`

3. STRICT BAN ON SLOW WEB TOOLS (`get_recent_news`, `parallel_research`):
   - NEVER call web tools for general questions, course recommendations, university advice, or follow-ups.
   - Use web search ONLY if the user explicitly asks "Search the live web for recent headlines from this month".

4. TOOL BUDGET:
   - AT MOST 1 tool call per request. Never call tools sequentially.
"""

root_agent = Agent(
    name="college_advisor",
    model=settings.model,
    description="Advises students on college majors, AI exposure, and career outlook.",
    instruction=ROOT_AGENT_INSTRUCTIONS,
    planner=fast_planner(),
    tools=[
        get_dynamic_top_careers,
        get_major_data,
        compare_majors,
        get_median_pay,
        get_ai_exposure,
        get_top_majors,
        get_recent_news,
        parallel_research_tool,
    ],
)