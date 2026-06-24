import os
import pytest

# Enforce testing environment variables so local machines don't look for GCP cloud keys
os.environ["ENV"] = "testing"

from data_pipeline import MajorMarketDataPipeline
from agent_config import CollegeAdvisorAgent, MajorAnalysisSchema

def test_data_pipeline_flow():
    """Verify that our pipeline generates correct GCS filenames and handles mock structures."""
    pipeline = MajorMarketDataPipeline()
    
    gcs_result = pipeline.stage_raw_news_to_gcs("Computer Engineering", {"news_headline": "AI trends in 2026"})
    bq_result = pipeline.stream_metrics_to_bigquery("Computer Engineering", 0.85)
    
    assert "raw_news_computer_engineering.json" in gcs_result
    assert bq_result is True

def test_adk_agent_reasoning():
    """Verify that our ADK reasoning nodes properly catch structure and parse mock fields."""
    agent = CollegeAdvisorAgent(agent_id="advisor-agent-01")
    test_payload = MajorAnalysisSchema(
        major_name="Business Administration", 
        query_context="Will automation affect accounting metrics?"
    )
    
    response = agent.execute_agent_reasoning(test_payload)
    
    assert response["agent_node"] == "advisor-agent-01"
    assert "Business Administration" in response["generated_guidance"]