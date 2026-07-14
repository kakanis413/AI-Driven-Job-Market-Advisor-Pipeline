from pydantic import BaseModel, Field
from google.adk import Agent

from tools import get_major_data


class OccupationInfo(BaseModel):
    soc: str
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
""",
    tools=[get_major_data],
)