from pydantic import BaseModel, Field

class MajorAnalysisSchema(BaseModel):
    major_name: str = Field(..., description="The US College Major being evaluated.")
    query_context: str = Field(..., description="User question regarding job market shifts.")

class CollegeAdvisorAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.system_instruction = "You are an elite academic advisor reviewing AI metrics."

    def execute_agent_reasoning(self, input_data: MajorAnalysisSchema) -> dict:
        return {
            "agent_node": self.agent_id,
            "status": "active_reasoning",
            "generated_guidance": f"Gemini 3.5 Flash suggests prioritizing cloud systems engineering for {input_data.major_name}.",
            "source_layer": "BigQuery.job_market_insights"
        }