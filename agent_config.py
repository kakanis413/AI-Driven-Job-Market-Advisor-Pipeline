from pydantic import BaseModel, Field
from google.adk import Agent
from google.adk.tools.agent_tool import AgentTool

from tools import BQ_DATASET, BQ_PROJECT, bigquery_toolset


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


# --- data_agent: has direct, read-only BigQuery access via bigquery_toolset.
# Rather than being limited to one hardcoded query shape, it can inspect the
# schema and write its own SQL — so it can answer both "get me Computer
# Science's data" and open-ended questions like "which majors have the
# fastest pay growth" without a new Python function for each shape of ask.
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


# --- root_agent: the advisor. It's the one making the call on whether it
# needs data_agent, and it's the one writing the final advice — no separate
# agent downstream of it.
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
- You do not currently have a news_agent — recent-news lookup for a major (layoffs, hiring
  trends, new tools/models affecting the field) is not implemented yet. If a student's
  question depends on that, say plainly that you don't have current news access yet.
  Do not guess at or invent recent events.

Step 2 — once you have what you need (inline data, and/or tool results), write the advice
yourself:
- Ground every claim in the data you have — never invent numbers.
- High exposure does NOT mean job loss. Exposure measures how AI-transformable the
  *work* is, not whether the job disappears. Make this distinction explicit.
- Reference the specific occupations listed, not generic career advice.
- Keep responses to 3-5 short, conversational paragraphs.
""",
    tools=[AgentTool(agent=data_agent)],
)