from pydantic import BaseModel, Field
from google.adk import Agent
from google.adk.tools import google_search, AgentTool

from tools import get_major_data


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

# Wrap news_agent as a tool for the root agent
news_tool = AgentTool(agent=news_agent)


# -----------------------------------------------------------------------------
# Root Agent: college advisor with news tool
# -----------------------------------------------------------------------------
root_agent = Agent(
    name="college_advisor",
    model="gemini-3.5-flash",
    description="Advises students on a college major's AI exposure and career outlook.",
    instruction="""You are an elite academic advisor reviewing AI exposure metrics for college majors.

You will be given a specific major's data: name, AI exposure score (0-10), median pay,
growth outlook, and the occupations it feeds into.

Rules:
- Ground every claim in the provided data — never invent numbers.
- High exposure does NOT mean job loss. Exposure measures how AI-transformable the
  *work* is, not whether the job disappears. Make this distinction explicit.
- Reference the specific occupations listed, not generic career advice.
- Keep responses to 3-5 short, conversational paragraphs.
- For questions about recent news, trends, or current events related to a major
  or career field, use the news_researcher tool.
""",
    tools=[get_major_data, news_tool],
)
