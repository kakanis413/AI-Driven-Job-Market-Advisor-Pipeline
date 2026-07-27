#!/usr/bin/env bash
# One-shot bootstrap deploy of both Cloud Run services, in the order the build
# requires: backend first, then the frontend compiled against the backend's URL.
#
# After this has run once, scripts/create-triggers.sh wires Cloud Build so pushes
# deploy automatically and you never need to run this again.
set -euo pipefail

PROJECT="${PROJECT:-sprinternship-sea-2026}"
REGION="${REGION:-us-west1}"
BACKEND="${BACKEND:-advisor-api}"
FRONTEND="${FRONTEND:-advisor-web}"

# The SDK is installed but not on PATH on this machine.
if ! command -v gcloud >/dev/null 2>&1; then
  export PATH="$HOME/Downloads/google-cloud-sdk/bin:$PATH"
fi
command -v gcloud >/dev/null 2>&1 || { echo "gcloud not found" >&2; exit 1; }

cd "$(dirname "$0")/.."

echo "==> Deploying backend ($BACKEND) to $REGION"
gcloud builds submit \
  --project="$PROJECT" \
  --config=cloudbuild.backend.yaml \
  --substitutions="_REGION=${REGION},_SERVICE=${BACKEND},COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo manual)"

BACKEND_URL="$(gcloud run services describe "$BACKEND" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)')"
echo "==> Backend live at $BACKEND_URL"

# Sanity-check the backend before compiling its URL into the frontend bundle.
# /healthz reports which model, project and dataset the instance actually resolved,
# so a misconfigured revision fails here instead of silently at first question.
echo "==> Health check"
curl -fsS --max-time 30 "${BACKEND_URL}/healthz" && echo

echo "==> Deploying frontend ($FRONTEND) against $BACKEND_URL"
gcloud builds submit \
  --project="$PROJECT" \
  --config=cloudbuild.frontend.yaml \
  --substitutions="_REGION=${REGION},_SERVICE=${FRONTEND},_AGENT_URL=${BACKEND_URL}/api/v1/analyze-major,COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo manual)"

FRONTEND_URL="$(gcloud run services describe "$FRONTEND" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)')"

echo
echo "Backend  : $BACKEND_URL"
echo "Frontend : $FRONTEND_URL"
