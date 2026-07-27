#!/usr/bin/env bash
# Create the two Cloud Build triggers so pushes to the default branch redeploy.
# Run ONCE, after scripts/deploy.sh has succeeded (the frontend trigger needs the
# backend's URL, which only exists after the first deploy).
#
# This reuses the GitHub App connection that already exists on this repo — the same
# one behind the existing major-visualizer trigger — so there is no browser OAuth step.
set -euo pipefail

PROJECT="${PROJECT:-sprinternship-sea-2026}"
REGION="${REGION:-us-west1}"
REPO_OWNER="${REPO_OWNER:-kakanis413}"
REPO_NAME="${REPO_NAME:-AI-Driven-Job-Market-Advisor-Pipeline}"
BRANCH="${BRANCH:-^main$}"
BACKEND="${BACKEND:-advisor-api}"
FRONTEND="${FRONTEND:-advisor-web}"

if ! command -v gcloud >/dev/null 2>&1; then
  export PATH="$HOME/Downloads/google-cloud-sdk/bin:$PATH"
fi

BACKEND_URL="$(gcloud run services describe "$BACKEND" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)')"
echo "==> Backend URL for frontend builds: $BACKEND_URL"

echo "==> Creating backend trigger"
gcloud builds triggers create github \
  --project="$PROJECT" \
  --name="deploy-${BACKEND}" \
  --region=global \
  --repo-owner="$REPO_OWNER" \
  --repo-name="$REPO_NAME" \
  --branch-pattern="$BRANCH" \
  --build-config=cloudbuild.backend.yaml \
  --substitutions="_REGION=${REGION},_SERVICE=${BACKEND}" \
  --description="Build and deploy ${BACKEND} to Cloud Run on push"

echo "==> Creating frontend trigger"
gcloud builds triggers create github \
  --project="$PROJECT" \
  --name="deploy-${FRONTEND}" \
  --region=global \
  --repo-owner="$REPO_OWNER" \
  --repo-name="$REPO_NAME" \
  --branch-pattern="$BRANCH" \
  --build-config=cloudbuild.frontend.yaml \
  --substitutions="_REGION=${REGION},_SERVICE=${FRONTEND},_AGENT_URL=${BACKEND_URL}/api/v1/analyze-major" \
  --description="Build and deploy ${FRONTEND} to Cloud Run on push"

gcloud builds triggers list --project="$PROJECT" --region=global \
  --format="table(name,github.owner,github.name,github.push.branch,filename)"
