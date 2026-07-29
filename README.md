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

## Product
![Advisor](https://www.image2url.com/r2/default/gifs/1785362854125-fea1aa67-db06-462d-8cd3-eadfb84ddb2d.gif)

## License

MIT. See [LICENSE](LICENSE).
