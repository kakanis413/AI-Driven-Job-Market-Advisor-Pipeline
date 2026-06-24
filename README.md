# AI-Driven Job Market Advisor Pipeline 🚀
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![GCP Storage](https://img.shields.io/badge/Google_Cloud_Storage-4285F4?style=flat&logo=google-cloud&logoColor=white)](https://cloud.google.com/storage)
[![BigQuery](https://img.shields.io/badge/BigQuery-669DF2?style=flat&logo=google-cloud&logoColor=white)](https://cloud.google.com/bigquery)

An enterprise-grade Python backend microservice built on **FastAPI** that automates the ingestion, normalization, and intelligent processing of academic major performance indicators and labor market disruption data. 

The microservice implements an automated extraction-load pipeline that standardizes telemetry data into **Google Cloud Storage (GCS)** buckets, streams real-time data metrics into **Google BigQuery**, and orchestrates an intelligent context-aware reasoning loop through a virtual **Vertex AI Agentic Design Kit (ADK)** layer powered by the Gemini 3.5 Flash persona.

---

## 🏛 Architecture Diagram



1. **Ingestion Layer:** FastAPI receives structured incoming payloads via a type-safe router (`/api/v1/analyze-major`).
2. **Infrastructure Fabric:** The ingestion controller triggers clean filename standardization, tracking local object writes representing GCS paths and signaling sync statuses to BigQuery tables.
3. **Intelligence Orchestration:** The query context is injected into a context-bound `CollegeAdvisorAgent` instance running specialized prompt engineering layers to deliver analytical advice.

---

## ⚙️ Core Engineering Features

- **Type-Safe Schema Validation:** Enforced through `Pydantic V2` models, ensuring that incoming payload matrices completely eliminate risk of runtime database corruptions.
- **Deterministic String Normalization:** Dynamically sanitizes complex multi-word parameters (e.g., `"Computer Engineering"` to `raw_news_computer_engineering.json`) for precise file path matching.
- **Decoupled Architecture:** Completely breaks apart data ingestion processes from downstream LLM evaluation steps, supporting high-throughput asynchronous workloads.
- **Auto-Generated Documentation:** Exposes an interactive testing playground instantly via native Swagger UI hooks (`/docs`).

---

## 📂 Project Blueprint

```text
google-prep-project/
├── .venv/                  # Isolated Python environment virtual directory
├── agent_config.py         # Vertex AI Agent configuration & Pydantic schemas
├── data_pipeline.py        # GCS & BigQuery ingestion layout controllers
├── main.py                 # FastAPI Application bootstrap router and main entry point
├── requirements.txt        # Managed service level dependencies
└── test_main.py            # Unit-testing suite utilizing pytest framework
