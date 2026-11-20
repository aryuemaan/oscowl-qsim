#!/usr/bin/env bash
# Deploy OSCOWL Q-Sim (API + UI in one container) to Cloud Run.
#
#   export PROJECT_ID=your-project-id
#   export REGION=asia-south1          # optional (default Mumbai)
#   bash deploy/cloudrun/deploy.sh
#
# Optional: store your Gemini key in Secret Manager first (see docs/GCP_DEPLOY.md):
#   printf "%s" "YOUR_KEY" | gcloud secrets create gemini-api-key --data-file=-
set -euo pipefail
PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID first: export PROJECT_ID=your-project-id}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-oscowl-qsim}"
REPO="${REPO:-qsim}"
cd "$(dirname "$0")/../.."

gcloud config set project "$PROJECT_ID" >/dev/null
echo "==> Enabling APIs (first run takes a minute)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

if ! gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1; then
  echo "==> Creating Artifact Registry repository $REPO"
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location "$REGION"
fi

IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE:$(date +%Y%m%d-%H%M%S)"
echo "==> Building $IMAGE with Cloud Build"
gcloud builds submit --tag "$IMAGE" .

SECRET_ARGS=()
if gcloud secrets describe gemini-api-key >/dev/null 2>&1; then
  NUM="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  gcloud secrets add-iam-policy-binding gemini-api-key \
    --member="serviceAccount:${NUM}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
  SECRET_ARGS=(--set-secrets "GEMINI_API_KEY=gemini-api-key:latest")
  echo "==> Gemini key will be injected from Secret Manager"
else
  echo "==> No 'gemini-api-key' secret found: the service will run in offline AI mode"
fi

echo "==> Deploying to Cloud Run"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" --region "$REGION" --allow-unauthenticated \
  --cpu 2 --memory 2Gi --timeout 300 --concurrency 4 \
  --min-instances 0 --max-instances 5 \
  --set-env-vars "QSIM_AI_MODE=auto,SV_HARD_MAX=22,TIME_BUDGET_S=120" \
  "${SECRET_ARGS[@]}"

echo
echo "Live at: $(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
