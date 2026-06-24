import os
from fastapi import FastAPI

# Force testing mode so it runs cleanly right on your laptop
os.environ["ENV"] = "testing"

from data_pipeline import MajorMarketDataPipeline
from agent_config import CollegeAdvisorAgent, MajorAnalysisSchema

app = FastAPI(title="Google Cloud Project Workspace")

pipeline = MajorMarketDataPipeline()
agent = CollegeAdvisorAgent(agent_id="kirkland-advisor-node-01")

@app.get("/")
def home():
    return {"message": "Use the interactive browser tools at http://127.0.0.1:8080/docs"}

@app.post("/api/v1/analyze-major")
def analyze_major_endpoint(payload: MajorAnalysisSchema):
    mock_scraped_news = {"headline": f"AI trends for {payload.major_name}."}
    gcs_path = pipeline.stage_raw_news_to_gcs(payload.major_name, mock_scraped_news)
    pipeline.stream_metrics_to_bigquery(payload.major_name, ai_exposure_score=0.78)
    agent_response = agent.execute_agent_reasoning(payload)
    
    return {
        "infrastructure_logs": {
            "gcs_path": gcs_path,
            "bigquery_stream_status": "synced"
        },
        "vertex_ai_geap_layer": agent_response
    }

# THIS BLOCK FORCES THE SERVER TO START IMMEDIATELY
if __name__ == "__main__":
    import uvicorn
    print("\n--- BOOTING UP INTERACTIVE DASHBOARD SERVER ---")
    uvicorn.run(app, host="127.0.0.1", port=8080)