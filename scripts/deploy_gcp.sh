#!/usr/bin/env bash
# Provision Minerva on Google Cloud from scratch: Cloud Run + Cloud SQL (Postgres
# with pgvector) + Secret Manager. Run after `gcloud auth login`.
#
# This is the FIRST-RUN script. To ship new code to the service that already
# exists, don't run this — it rewrites every secret, and a missing DB_PASS would
# overwrite DATABASE_URL with a broken URL. Just redeploy the image instead:
#
#     gcloud run deploy daily-coach --source . --region=asia-east1
#
# Reads API keys from the local .env (gitignored) and the Firebase service
# account from secrets/firebase-admin.json. Idempotent-ish: re-running skips
# resources that already exist.
set -euo pipefail

PROJECT="project-53471801-f70d-47e4-a57"
REGION="asia-east1"            # Changhua, Taiwan — closest to the user
INSTANCE="coach-db"
DB_NAME="coach"
DB_USER="coach"
# The live service. Named before the project was renamed to Minerva; renaming it
# would change the URL, which is already in Firebase's authorized domains.
SERVICE="daily-coach"
CONN="${PROJECT}:${REGION}:${INSTANCE}"

cd "$(dirname "$0")/.."
set -a; source .env; set +a   # load API keys from .env

# Every secret below is rebuilt from these, so a missing one would silently
# publish a broken value. Fail loudly instead.
: "${DB_PASS:?set DB_PASS in .env — it is the Cloud SQL password for $DB_USER}"

echo "==> 1. Set project + enable APIs"
gcloud config set project "$PROJECT"
gcloud services enable \
  run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com

echo "==> 2. Cloud SQL Postgres instance (skip if it exists; ~10 min to create)"
if ! gcloud sql instances describe "$INSTANCE" >/dev/null 2>&1; then
  # ENTERPRISE edition so the cheap shared-core db-f1-micro tier is allowed
  # (ENTERPRISE_PLUS, the default, rejects it). pgvector needs no instance
  # flag — the app runs CREATE EXTENSION on first use.
  gcloud sql instances create "$INSTANCE" \
    --database-version=POSTGRES_16 --edition=ENTERPRISE \
    --tier=db-f1-micro --region="$REGION"
fi
DB_PASS="$(openssl rand -base64 18)"
gcloud sql users set-password "$DB_USER" --instance="$INSTANCE" --password="$DB_PASS" 2>/dev/null \
  || gcloud sql users create "$DB_USER" --instance="$INSTANCE" --password="$DB_PASS"
gcloud sql databases create "$DB_NAME" --instance="$INSTANCE" 2>/dev/null || true

echo "==> 3. Secrets (API keys + DB URL + Firebase admin json)"
put_secret () { # name value
  if gcloud secrets describe "$1" >/dev/null 2>&1; then
    printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=-
  else
    printf '%s' "$2" | gcloud secrets create "$1" --data-file=-
  fi
}
# Cloud Run reaches Cloud SQL over a unix socket at /cloudsql/<CONN>.
DB_URL="postgresql+psycopg://${DB_USER}:${DB_PASS}@/${DB_NAME}?host=/cloudsql/${CONN}"
put_secret DATABASE_URL "$DB_URL"
put_secret ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY"
put_secret OPENAI_API_KEY "$OPENAI_API_KEY"
put_secret ELEVENLABS_API_KEY "$ELEVENLABS_API_KEY"
put_secret LANGSMITH_API_KEY "$LANGSMITH_API_KEY"
gcloud secrets describe FIREBASE_CREDENTIALS >/dev/null 2>&1 \
  && gcloud secrets versions add FIREBASE_CREDENTIALS --data-file=secrets/firebase-admin.json \
  || gcloud secrets create FIREBASE_CREDENTIALS --data-file=secrets/firebase-admin.json

echo "==> 4. Deploy to Cloud Run (builds the image from source)"
gcloud run deploy "$SERVICE" \
  --source . --region="$REGION" --allow-unauthenticated \
  --add-cloudsql-instances="$CONN" \
  --set-secrets="DATABASE_URL=DATABASE_URL:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,ELEVENLABS_API_KEY=ELEVENLABS_API_KEY:latest,LANGSMITH_API_KEY=LANGSMITH_API_KEY:latest" \
  --set-secrets="/secrets/firebase-admin.json=FIREBASE_CREDENTIALS:latest" \
  --set-env-vars="FIREBASE_CREDENTIALS=/secrets/firebase-admin.json"

echo "==> Done. Next: create tables + pgvector via a one-off (see README)."
gcloud run services describe "$SERVICE" --region="$REGION" --format="value(status.url)"
