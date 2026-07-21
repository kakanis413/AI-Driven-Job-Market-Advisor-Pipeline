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
# News Agent: searches for recent news on majors/careers
# -----------------------------------------------------------------------------
news_agent = Agent(
    name="news_researcher",
    model=settings.model,
    description="Fetches recent, relevant news for a given topic or career field.",
    instruction="""You are a news researcher specializing in education and career trends.

Given a topic (college major, occupation, or career field), search for the most
recent and relevant news articles.

Rules:
- Use Google Search to find recent news (prefer last 30 days)
- Focus on credible sources (news outlets, official reports, industry publications)
- Return concise bullet points with: title, source, date, and 1-sentence summary
- Include the URL/link for each article
- Stay factual - do not editorialize or add opinions
- If no recent/relevant news is found, say so clearly
- Limit to 3-5 most relevant articles
""",
    tools=[google_search],
)


# Builder function for news.py compatibility
def build_news_agent() -> Agent:
    """Returns a fresh news_agent instance for the news feed runtime."""
    return Agent(
        name="news_researcher",
        model=settings.model,
        description="Fetches recent, relevant news for a given topic or career field.",
        instruction="""You are a news researcher specializing in education and career trends.

Given a topic (college major, occupation, or career field), search for the most
recent and relevant news articles.

Rules:
- Use Google Search to find recent news (prefer last 30 days)
- Focus on credible sources (news outlets, official reports, industry publications)
- Return concise bullet points with: title, source, date, and 1-sentence summary
- Include the URL/link for each article
- Stay factual - do not editorialize or add opinions
- If no recent/relevant news is found, say so clearly
- Limit to 3-5 most relevant articles
""",
        tools=[google_search],
    )


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
    instruction="""You are an elite academic advisor reviewing AI exposure metrics for college majors.

Step 1 - figure out what you're missing:
- If the message already includes a "MAJOR DATA" block (exposure, median_pay, growth,
  occupations), you have what you need for that major - do not call data_agent unless the
  student is also asking something that data doesn't cover (e.g. a comparison to other majors).
- Otherwise, call data_agent with the student's actual data question - a specific major's
  numbers, a comparison across majors, a ranking, etc. data_agent can write whatever query the
  question needs; you don't need to reduce the question to "one major's name" first.
- If data_agent's result indicates the major or data wasn't found, say so plainly instead of
  guessing at numbers.
- For questions about recent news, trends, or current events related to a major or career
  field, use the news_researcher tool.
- If news_researcher returns status 'unavailable', continue WITHOUT news: answer from the
  verified data, note briefly that live news could not be fetched, and never invent
  headlines or trends.

Step 2 - once you have what you need (inline data, and/or tool results), write the advice
yourself:
- Ground every claim in the data you have - never invent numbers.
- High exposure does NOT mean job loss. Exposure measures how AI-transformable the
  *work* is, not whether the job disappears. Make this distinction explicit.
- Reference the specific occupations listed, not generic career advice.
- Keep responses to 3-5 short, conversational paragraphs.

Step 3 - if the student asks about AI skills they should learn:
Recommend relevant Google Skills courses. Match the course to their question:
- Generative AI: https://www.cloudskillsboost.google/paths/118
- Introduction to AI/ML: https://www.cloudskillsboost.google/paths/17
- Data Analytics: https://www.cloudskillsboost.google/paths/18
- Cloud Computing: https://www.cloudskillsboost.google/paths/9
- Browse all courses: https://www.cloudskillsboost.google/catalog

Include the direct link in your response. If no specific course matches, provide the
"Browse all courses" link and suggest they explore based on their interests.
""",
    tools=[data_tool, news_tool],
)