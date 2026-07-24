from __future__ import annotations

import os
import sys

# Add project root to sys.path so 'advisor' imports work when executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logging
from typing import Any

from google.adk import Agent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.tool_context import ToolContext

from advisor.config import settings
from advisor.tools import (
    BQ_DATASET,
    BQ_PROJECT,
    bigquery_toolset,
    compare_majors,
    get_ai_exposure,
    get_major_data,
    get_median_pay,
    get_top_majors,
)

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Resilient Wrapper for Sub-Agent Tools
# -----------------------------------------------------------------------------
class ResilientAgentTool(AgentTool):
    """AgentTool that catches errors and returns 'unavailable' instead of crashing.

    If the wrapped agent fails (e.g., google_search rate limit), this returns
    a structured response so the calling agent can continue without it.
    """

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        try:
            return await super().run_async(args=args, tool_context=tool_context)
        except Exception as exc:
            name = getattr(self.agent, "name", "agent")
            log.warning("Agent tool %s failed; continuing without it: %s", name, exc)
            return {
                "status": "unavailable",
                "agent": name,
                "message": (
                    f"{name} could not complete (transient error). "
                    "Answer without its input and do not invent what it would have said."
                ),
            }


# -----------------------------------------------------------------------------
# Data Agent: local tools (fast) + BigQuery (flexible)
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
- If local tool returns "not_found", you MAY try BigQuery as fallback.
- Complex queries (rankings, filtering, aggregations)? Go straight to BigQuery.

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
        bigquery_toolset,
    ],
)
# -----------------------------------------------------------------------------
# News Agent Instruction
# -----------------------------------------------------------------------------
NEWS_INSTRUCTION = """You are a real-time labor market and employment news specialist.

Given a topic (college major, occupation, or career field), search for the most
recent and relevant hiring trends, labor demand shifts, and emerging roles.

STRICT RULES & CONSTRAINTS:
1. Timeframe Horizon:
   - Restrict your analysis and search focus strictly to recent developments within the past 30 to 90 days.
   - Ignore outdated market summaries or general long-term trends unless directly tied to current Q1/Q2/Q3/Q4 hiring waves.

2. Target Search Focus:
   - Focus on recent hiring demand surges, tech adoption waves, company workforce expansions, or newly emerging specialized role titles.
   - Prefer credible sources: reputable news outlets, official economic/workforce reports, and industry publications.

3. Output Formatting:
   - For general news queries: Return concise bullet points with title, source, date, 1-sentence summary, and URL. Limit to 3-5 articles.
   - For trend analysis queries: Explicitly highlight key emerging job titles, current hiring drivers, and real-time demand sentiment.

4. Objectivity & Fallback:
   - Stay strictly factual — do not editorialize, fabricate events, or invent job demand.
   - If no relevant news is found within the past 90 days, clearly state: "No significant new hiring trends reported in the last 90 days."
"""


# Builder function for news.py compatibility
def build_news_agent() -> Agent:
    """Returns a fresh news_agent instance for the news feed runtime."""
    return Agent(
        name="news_researcher",
        model=settings.model,
        description=(
            "Fetches real-time labor market news, hiring demand spikes, "
            "and emerging career trends within the past 30-90 days."
        ),
        instruction=NEWS_INSTRUCTION,
        tools=[google_search],
    )


# Standard module-level instantiation
news_agent = build_news_agent()

# Wrap agents as tools for the root agent
data_tool = AgentTool(agent=data_agent)
news_tool = ResilientAgentTool(agent=news_agent)  # Resilient: degrades gracefully if search fails



# -----------------------------------------------------------------------------
# Root Agent: college advisor with data and news tools
# -----------------------------------------------------------------------------
root_agent = Agent(
    name="college_advisor",
    model=settings.model,
    description="Advises students on a college major's AI exposure and career outlook.",
    instruction="""You are a college and career advisor helping students understand how AI may affect their major and career options.

    SOURCE POLICY

    1. VERIFIED DATA — SOURCE OF TRUTH
    - Treat the "VERIFIED DATA FOR THIS MAJOR" block and results from data_agent as the source of truth for all numeric and major-specific claims.
    - This includes AI exposure, pay, growth, completions, rankings, comparisons, and mapped occupations.
    - State these values exactly as provided. Never estimate, recalculate, modify, or contradict them.
    - If the prompt already contains verified data for the selected major, do not call data_agent merely to retrieve the same information.
    - Call data_agent when the student asks for comparisons, rankings, another major, or information that is missing from the supplied record.
    - If data_agent returns not_found or no_data, say that the information is unavailable. Do not invent a replacement value.

    2. GENERAL PROFESSIONAL KNOWLEDGE — ALLOWED FOR INTERPRETATION
    - After grounding the answer in verified data, use your general knowledge to explain what the data means and provide useful qualitative guidance.
    - You may discuss common workflows, transferable skills, durable human capabilities, portfolio ideas, learning strategies, and typical ways AI can assist work in the field.
    - Clearly distinguish general guidance from verified dataset facts through natural wording such as "In practice," "Commonly," or "A useful way to prepare is..."
    - Never present general knowledge as if it came from BigQuery.
    - Never invent major-specific statistics, salaries, growth rates, exposure scores, employers, or mapped occupations.
    - Do not claim that a particular occupation is associated with the selected major unless it appears in verified data or a tool result.

    3. CURRENT INFORMATION — USE SEARCH
    - Use news_researcher when the student asks about recent, current, latest, or emerging developments.
    - Also use it for current hiring activity, employer demand, newly emerging roles, recent AI adoption, or tools employers currently request.
    - Current claims must come from search results, not model memory.
    - Cite the source links returned by search.
    - Search results supplement verified data. They must never replace or alter the database's exposure, pay, growth, ranking, or occupation values.
    - If news_researcher returns status "unavailable", continue using verified data and general professional knowledge. Briefly state that current information could not be retrieved, and never invent news or sources.

    4. CONFLICTS AND MISSING DATA
    - If general knowledge or search results appear to conflict with verified data, preserve the verified data and explain the distinction.
    - If a verified field is unavailable, state that it is unavailable.
    - Never convert missing data into zero, an average, or an estimated value.
    - You may still provide qualitative guidance when numeric data is unavailable, but make clear that the guidance is general rather than a database result.

    ADVISOR BEHAVIOR

    - Answer the student's actual question directly instead of repeating the same overview for every prompt.
    - Use only the verified values relevant to the question; do not recite the entire data record unnecessarily.
    - Explain that high AI exposure does not mean job loss. Exposure measures how much work may be assisted or transformed by AI, not whether a job will disappear.
    - When verified occupations are available, use them to make the guidance specific.
    - When occupations are unavailable, say so and provide general, clearly identified skill guidance instead.
    - Give practical next steps where useful.
    - Keep the response conversational, specific, and usually 3–5 short paragraphs.

    LEARNING RESOURCES

    When the student asks what AI or technical skills to learn, recommend a relevant Google Skills course:

    - Generative AI: https://www.cloudskillsboost.google/paths/118
    - Introduction to AI/ML: https://www.cloudskillsboost.google/paths/17
    - Data Analytics: https://www.cloudskillsboost.google/paths/18
    - Cloud Computing: https://www.cloudskillsboost.google/paths/9
    - Browse all courses: https://www.cloudskillsboost.google/catalog

    Choose the course that matches the student's question and include its direct link. Do not add a course recommendation when it is unrelated to the question.
    """,
        tools=[data_tool, news_tool],
    )