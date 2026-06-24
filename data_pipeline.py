import os
import json

class MajorMarketDataPipeline:
    def __init__(self):
        self.is_testing = True
        self.bucket_name = "us-college-major-artifacts"
        self.dataset_id = "job_market_insights"

    def stage_raw_news_to_gcs(self, major_name: str, raw_data: dict) -> str:
        file_name = f"raw_news_{major_name.lower().replace(' ', '_')}.json"
        return f"Mocked GCS Upload Path: daily_scrapes/{file_name}"

    def stream_metrics_to_bigquery(self, major_name: str, ai_exposure_score: float) -> bool:
        return True