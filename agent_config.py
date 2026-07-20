import logging
from typing import Any

from pydantic import BaseModel, Field
from google.adk import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.tool_context import ToolContext
from google.adk.tools import google_search

from tools import BQ_DATASET, BQ_PROJECT, bigquery_toolset

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# ResilientAgentTool: wraps an agent so failures degrade gracefully
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


class OccupationInfo(BaseModel):

    title: str
    exposure: float


class MajorAnalysisSchema(BaseModel):
    major_name: str = Field(..., description="The US College Major being evaluated.")
    exposure: float = Field(..., description="AI exposure score 0-10 for this major.")
    median_pay: int = Field(..., description="Employment-weighted median pay.")
    growth: str = Field(..., description="Growth outlook, e.g. 'faster', 'average'.")
    occupations: list[OccupationInfo] = Field(
        ..., description="Occupations this major feeds into."
    )
    query_context: str = Field(..., description="User question regarding job market shifts.")


# -----------------------------------------------------------------------------
# Data Agent: has direct, read-only BigQuery access via bigquery_toolset
# -----------------------------------------------------------------------------
data_agent = Agent(
    name="data_agent",
    model="gemini-3.5-flash",
    description=(
        "Answers data questions about college majors' AI exposure, pay, growth, "
        "and occupations by querying BigQuery directly."
    ),
    instruction=f"""You have read-only BigQuery access to project '{BQ_PROJECT}',
dataset '{BQ_DATASET}'.

Tables available:
- dim_major(major_name, cip, family, completions, rationale): one row per college major.
- dim_occupation(soc, title): one row per occupation.
- bridge_cip_soc(cip, soc): maps majors (by cip) to the occupations they feed into (by soc).
- fact_exposure(cip, soc, exposure_score): AI exposure score (0-10), keyed by cip or soc.
- fact_employment(cip, median_pay, growth_outlook): pay and growth outlook per major.

For a single named major's data (exposure, median_pay, growth, occupations): join dim_major to
fact_exposure and fact_employment on cip, and join through bridge_cip_soc + dim_occupation for
its occupations.

For open-ended questions — "which majors have the fastest pay growth", "compare two majors",
"top 5 highest-exposure majors", and similar — write and run whatever SELECT query answers it.
You are not limited to single-major lookups.

Rules:
- Only ever run SELECT queries. You cannot and must not attempt to modify data.
- If you're unsure of an exact column or table name, use your schema-inspection tools to check
  before writing SQL — never guess at column names.
- Return the query result to the orchestrator as-is. Do not summarize or interpret it — that's
  the orchestrator's job.
""",
    tools=[bigquery_toolset],
)


# -----------------------------------------------------------------------------
# News Agent: searches for recent news on majors/careers
# -----------------------------------------------------------------------------
news_agent = Agent(
    name="news_researcher",
    model="gemini-3.5-flash",
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
    model="gemini-3.5-flash",
    description="Advises students on a college major's AI exposure and career outlook.",
    instruction="""You are an elite academic advisor reviewing AI exposure metrics for college majors.

Step 1 — figure out what you're missing:
- If the message already includes a "MAJOR DATA" block (exposure, median_pay, growth,
  occupations), you have what you need for that major — do not call data_agent unless the
  student is also asking something that data doesn't cover (e.g. a comparison to other majors).
- Otherwise, call data_agent with the student's actual data question — a specific major's
  numbers, a comparison across majors, a ranking, etc. data_agent can write whatever query the
  question needs; you don't need to reduce the question to "one major's name" first.
- If data_agent's result indicates the major or data wasn't found, say so plainly instead of
  guessing at numbers.
- For questions about recent news, trends, or current events related to a major or career
  field, use the news_researcher tool.
- If news_researcher returns status 'unavailable', continue WITHOUT news: answer from the
  verified data, note briefly that live news could not be fetched, and never invent
  headlines or trends.

Step 2 — once you have what you need (inline data, and/or tool results), write the advice
yourself:
- Ground every claim in the data you have — never invent numbers.
- High exposure does NOT mean job loss. Exposure measures how AI-transformable the
  *work* is, not whether the job disappears. Make this distinction explicit.
- Reference the specific occupations listed, not generic career advice.
- Keep responses to 3-5 short, conversational paragraphs.

Step 3 — if the student asks about AI skills they should learn:
Recommend relevant Google Skills courses. Match the course to their question:
- Generative AI → https://www.cloudskillsboost.google/paths/118
- Introduction to AI/ML → https://www.cloudskillsboost.google/paths/17
- Data Analytics → https://www.cloudskillsboost.google/paths/18
- Cloud Computing → https://www.cloudskillsboost.google/paths/9
- Browse all courses → https://www.cloudskillsboost.google/catalog

Include the direct link in your response. If no specific course matches, provide the
"Browse all courses" link and suggest they explore based on their interests.
""",
    tools=[data_tool, news_tool],
)
