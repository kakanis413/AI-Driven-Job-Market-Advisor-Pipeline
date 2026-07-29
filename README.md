# US College Major Visualizer & AI Advisor

A web application that helps students explore how AI may change US college majors and related careers. It combines a D3-powered major visualization, curated education and labor-market metrics, a Gemini-powered advisor, and search-grounded news.

The guiding product principle is simple: **the advisor is grounded on the same curated dataset shown in the interface.** Students should not see one set of numbers in the visualization and receive another in chat.

## What it does

- Visualizes majors by academic family, AI exposure, pay, growth, and career pathways.
- Provides a conversational advisor for questions about majors, careers, and AI exposure.
- Streams advisor responses with Server-Sent Events (SSE).
- Shows recent, search-grounded news by academic family.
- Supports optional university context in advisor requests.

## Impact

Choosing a major is increasingly a career-planning decision, not only an academic one. This project makes AI exposure, pay, growth outlook, and career pathways easier to compare in one place. It frames AI exposure as **how work may change or be augmented**, rather than as a prediction that a job will disappear.

The application is designed to turn complex labor-market and education data into an approachable starting point for exploration, discussion, and more informed academic planning.

## Target audience

- **Prospective and current college students** exploring majors and career directions.
- **Academic advisors and career-services teams** who need a visual, data-informed conversation aid.
- **Education and workforce researchers** interested in relationships between degree programs, occupations, and AI exposure.
- **Program and product stakeholders** studying how academic pathways are evolving with labor-market change.

## How to use the application

1. Open the major explorer and browse the visualization by academic family or metric.
2. Select a major to inspect its AI exposure, earnings, growth outlook, rationale, and related careers.
3. Ask the advisor a question about the selected major, a comparison, career preparation, or a general career-planning topic.
4. Visit the News view to see recent, search-grounded signals for an academic family.
5. Optionally select a university to add school context to an advisor request.

## Architecture
<img width="1291" height="754" alt="image" src="https://github.com/user-attachments/assets/66075bef-ad96-4d2d-bc52-9ef8e051ee6a" />


### Request flow

1. The browser loads the visualization and curated static datasets.
2. A student sends a question and the currently selected major context to the FastAPI service.
3. The ADK root agent uses Gemini to formulate guidance and can call local tools that read the same `data.json` rendered by the UI.
4. The API streams answer tokens and useful progress statuses back to the browser over SSE.
5. Current-events requests can use a dedicated Google Search-grounded news agent. The News page is cache-first and refreshes in the background.

### Data flow

BigQuery supports the **offline** curation pipeline. The pipeline combines education, labor-market, and scoring inputs; filters and normalizes the records; and exports the static dataset consumed by the application. The normal student request path does not query BigQuery for each chat message.

### Architecture explanation

The system intentionally separates **curated facts** from **current signals**:

- **Curated facts:** the visualization and advisor use the same exported major dataset. This grounds advisor answers in the metrics students see on screen and avoids a warehouse query on the common request path.
- **Conversational reasoning:** the `college_advisor` root agent uses Gemini through Google ADK to turn the selected-major context and student question into clear guidance. It can use local data tools for verified fields such as exposure, pay, rankings, comparisons, and related careers.
- **Current signals:** a dedicated news agent uses Google Search grounding for current labor-market and industry information. The News runtime caches feeds by academic family, returns cached results quickly, and refreshes them in the background.
- **Offline curation:** upstream education, labor-market, and scoring data are consolidated in BigQuery. The Python pipeline filters and normalizes records into the versioned `data.json` artifact deployed with the frontend and advisor API.

## Technology

| Area | Implementation |
| --- | --- |
| Frontend | React, TypeScript, Vite, D3 hierarchy, Tailwind, Framer Motion |
| API | FastAPI, Pydantic, Uvicorn |
| AI | Google ADK, Vertex AI, Gemini |
| Search | ADK Google Search grounding |
| Data curation | BigQuery, Google Cloud Storage, Python |
| Deployment | Docker, Cloud Build, Cloud Run |

## Repository layout

```text
.
├── src/                    # React UI, views, hooks, and client API utilities
├── public/                 # Curated major data and university directory
├── advisor/                # ADK agents, runtime, tools, schemas, news service
├── batch/                  # AI-exposure scoring and validation jobs
├── sql/                    # Warehouse rollup pipeline
├── scripts/                # Deployment and university-data utilities
├── data_pipeline.py        # BigQuery → curated data.json export pipeline
├── main.py                 # FastAPI entry point
├── Dockerfile              # Advisor API container
├── Dockerfile.frontend     # Frontend Nginx container
└── cloudbuild.*.yaml       # Cloud Build deployment definitions
```

## Run locally

### Prerequisites

- Node.js 22+
- Python 3.12+
- Google Cloud credentials with access to the configured Vertex AI project for live advisor and news features

### Install

```bash
npm ci
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\\Scripts\\activate`.

### Configure

Create a local `.env` file as needed:

```dotenv
GOOGLE_CLOUD_PROJECT=your-gcp-project
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=true
BQ_DATASET=majors

# Browser origin(s) allowed to call the API.
ADVISOR_CORS_ORIGINS=http://localhost:5173

# Optional guardrails for a public deployment.
ADVISOR_API_KEY=
ADVISOR_RATE_LIMIT_PER_MIN=0
```

Authenticate with Application Default Credentials before using Vertex AI locally:

```bash
gcloud auth application-default login
```

### Start the app

```bash
npm run dev
```

This starts the FastAPI API on `http://127.0.0.1:8000` and the Vite frontend on its displayed local URL. For the frontend to call a local API, build or run Vite with `VITE_AGENT_URL=http://127.0.0.1:8000/api/v1/analyze-major`.

Run the frontend production build with:

```bash
npm run build
```

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Service health and resolved configuration summary |
| `POST /api/v1/analyze-major` | Returns a complete advisor response as JSON |
| `POST /api/v1/analyze-major/stream` | Streams advisor tokens and progress statuses as SSE |
| `GET /api/v1/news?family=STEM` | Returns the cached/search-grounded news feed for an academic family |
| `GET /docs` | Interactive FastAPI documentation |

Advisor requests may include selected-major context such as `major_name`, AI exposure, pay, growth, occupations, and a student question in `query_context`.

## Data refresh

The curated major dataset is produced with:

```bash
python data_pipeline.py --output public/data.json
```

The pipeline queries the configured BigQuery tables, applies data-quality rules, normalizes display metrics, and writes the frontend/advisor-compatible JSON artifact. It can also upload an artifact to Cloud Storage when configured to do so.

## Deployment

The application is deployed as two Cloud Run services:

- **Advisor API:** FastAPI, ADK runtime, and the local data artifact.
- **Web frontend:** a Vite-built React application served by Nginx.

The backend must be deployed first because the frontend embeds the advisor URL at build time. The provided Cloud Build definitions are `cloudbuild.backend.yaml` and `cloudbuild.frontend.yaml`; `scripts/deploy.sh` performs that sequence.

## Reliability and guardrails

- Local data tools avoid a warehouse round trip on ordinary advisor questions.
- Responses have retry, timeout, and 24-hour in-process cache behavior.
- The news service uses stale-while-revalidate caching so visitors can receive an existing feed while refresh work happens in the background.
- News cache state is instance-local and best-effort; it is not a shared durable cache across Cloud Run instances or deployments.
- API-key and rate-limit middleware are configurable. For an internet-facing deployment, use a proper identity or gateway layer in addition to application-level limits.

## License

MIT. See [LICENSE](LICENSE).
