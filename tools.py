import os

import google.auth
from dotenv import load_dotenv
from google.adk.integrations.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.integrations.bigquery.config import BigQueryToolConfig, WriteMode

load_dotenv()

BQ_PROJECT = os.getenv("BQ_PROJECT_ID")
BQ_DATASET = os.getenv("BQ_DATASET", "job_market")

# Application Default Credentials: `gcloud auth application-default login` locally,
# or the attached service account in Cloud Run / GKE / etc.
_credentials, _ = google.auth.default()
_credentials_config = BigQueryCredentialsConfig(credentials=_credentials)

# Read-only, hard-enforced: the agent can inspect schema and run SELECT queries,
# but can never write, update, or delete anything in BigQuery.
_tool_config = BigQueryToolConfig(write_mode=WriteMode.BLOCKED)

# Gives an agent schema-inspection tools (list tables, get table info, etc.)
# plus execute_sql — so it can write its own queries instead of being limited
# to whatever fixed query shape we hardcode ahead of time.
bigquery_toolset = BigQueryToolset(
    credentials_config=_credentials_config,
    bigquery_tool_config=_tool_config,
)