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

from google.adk.integrations.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.integrations.bigquery.config import BigQueryToolConfig, WriteMode
from google.cloud import bigquery

from advisor.config import settings
from advisor.tools import (
    BQ_DATASET,
    BQ_PROJECT,
    bigquery_toolset,
    get_dynamic_top_careers,
    compare_majors,
    get_ai_exposure,
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
data_agent = Agent(
    name="data_agent",
    model=settings.model,
    description=(
        "Answers data questions about college majors' AI exposure, pay, growth, "
        "and occupations. Has fast local lookups AND BigQuery for complex queries."
    ),
    instruction=f"""You retrieve facts about college majors. You have TWO data sources:

1. LOCAL TOOLS (fast, free - TRY THESE FIRST):
   - get_major_data(major_name): instant lookup for one major
   - compare_majors(major_a, major_b): compare two majors
   - get_median_pay(major_name): get median pay for a major
   - get_ai_exposure(major_name): get AI exposure for a major
   - get_top_majors(): get top majors by pay or growth

2. BIGQUERY (for complex queries the local tools can't answer):
   - Project: '{BQ_PROJECT}', Dataset: '{BQ_DATASET}'
   - Tables: dim_major, dim_occupation, bridge_cip_soc, fact_exposure, fact_employment
   - Use for: rankings ("top 5 highest-paying"), aggregations, joins across tables

ROUTING RULES:
- Single major lookup? Use get_major_data first. Fast and free.
- Compare two majors? Use compare_majors first.
- If local tool returns "not_found", you MUST try BigQuery as fallback before reporting
  that the data wasn't found. Never say "not found" without trying both sources.
- Complex queries (rankings, filtering, aggregations)? Go straight to BigQuery.

TOP-CAREER ROUTING RULES:
- When the student asks for the top, best, strongest, recommended, or most
  promising occupations for a specific major, call
  get_dynamic_top_careers(major_name, n).
- Use get_dynamic_top_careers for occupations within a major. Do not confuse it
  with get_top_majors, which ranks college majors rather than occupations.
- Preserve the career order returned by get_dynamic_top_careers exactly.
- Do not recalculate, reorder, replace, or add occupations based on your own
  judgment.
- The ranking returned by the tool is deterministic and uses:
    1. 50% occupation median-pay percentile
    2. 30% occupation projected-growth percentile
    3. 20% balanced AI-exposure score
- Balanced AI exposure means occupation exposure values from 4.0 through 8.0
  receive the maximum AI-balance score. Values below 4.0 or above 8.0 receive a
  progressively lower balance score.
- AI exposure is not a prediction of job loss. The balance component represents
  a mix of meaningful AI assistance and continued human contribution.
- Use only the pay, growth, AI exposure, component scores, and final career
  score returned by the tool. Never estimate or substitute missing values.
- If the tool returns status="partial", clearly report that fewer than the
  requested number of occupations had complete verified data.
- If the tool returns status="no_data", "not_found", or "unavailable", report
  that result plainly. Do not invent a Top 3.
- Return the ranked occupations and their supporting metrics to the
  college_advisor. The college_advisor is responsible for explaining the
  results conversationally.

  USER-FACING TOP-CAREER PRESENTATION:
- Use the tool's component values internally to explain the ranking, but never
  expose technical field names such as pay_score, growth_score,
  ai_balance_score, or career_score in the response.
- Introduce the methodology once in plain language: the ranking gives the most
  importance to median pay, followed by projected growth, with balanced AI
  integration as the final factor.
- For each occupation, present only information a student can understand
  immediately:
    - occupation title
    - median annual pay
    - projected growth
    - a short explanation of why it ranked in that position
- Translate normalized values into natural language. For example:
    - describe a strong pay result as "high pay compared with other occupations"
    - describe a strong growth result as "one of the stronger growth outlooks"
    - describe exposure from 4.0 through 8.0 as "within the preferred range for
      balanced AI integration"
- Do not say or imply that higher AI exposure is automatically better.
- Exposure values from 4.0 through 8.0 receive the full balanced-AI
  contribution.
- When exposure is above 8.0 or below 4.0, state that it falls outside the
  preferred balance range and therefore contributes less to the ranking.
- For exposure above 8.0, do not describe the high exposure itself as an
  advantage. Explain that the occupation may still rank highly because strong
  pay or growth offsets the reduced AI-balance contribution.
- AI exposure measures how much the occupation's task mix may be transformed or
  assisted by AI. It does not predict that the occupation will disappear.
- Explain the actual reason for each ranking. Do not use generic phrases such as
  "excellent balance" when one of the three factors is outside the preferred
  range.
- Preserve the exact occupation order returned by the tool.

BIGQUERY RULES:
- Only SELECT queries. Never modify data.
- Use schema-inspection tools before writing SQL if unsure of column names.
- Return query results as-is. Do not interpret - that's the orchestrator's job.
""",
    tools=[
        get_major_data,
        compare_majors,
        get_median_pay,
        get_ai_exposure,
        get_top_majors,
        get_dynamic_top_careers,
        bigquery_toolset,
    ],
)
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
ROOT_AGENT_INSTRUCTIONS = """You are an expert AI College & Career Advisor helping students understand AI's impact on their major and careers.

TOOL BUDGET — every tool call costs the student seconds of waiting.
1. A 'CONTEXT FOR THIS MAJOR' or 'PRE-LOADED TOP AI EXPOSURE DATA' block is the
   student's own screen. Those numbers OUTRANK anything a tool returns — quote them
   verbatim, and never contradict them with a different figure for the same field.
   If such a block answers the question, call NO tools at all.
2. If it does not, use at most ONE local tool (get_major_data, compare_majors,
   get_median_pay, get_ai_exposure, get_top_majors). These are instant. Never chain
   them back-to-back.
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
6. Synthesize in ONE turn. Never call the same tool twice, and never call a tool
   after you have begun writing the answer.

WHEN A TOOL DEGRADES: if a tool returns status "unavailable" or "not_found", say so plainly
and answer from the verified data you already have. Never invent numbers, headlines, or dates.

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
    ],
)