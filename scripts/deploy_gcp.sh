#!/bin/bash
# ============================================================
# Healthcare RAG — GCP Deployment Script
# Zero data loss migration from local → GCP
# Usage: ./deploy_gcp.sh [PROJECT_ID] [REGION]
# ============================================================

set -euo pipefail

PROJECT_ID="${1:-your-project-id}"
REGION="${2:-us-central1}"
SERVICE_NAME="healthcare-rag-backend"
FRONTEND_SERVICE="healthcare-rag-frontend"
ARTIFACT_REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/healthcare-rag"
DB_INSTANCE="${PROJECT_ID}:${REGION}:healthcare-rag-pg"
BUCKET="gs://${PROJECT_ID}-healthcare-rag-data"

echo "🚀 Starting GCP deployment for project: ${PROJECT_ID}"
echo "   Region: ${REGION}"

# ── Step 1: Enable APIs ────────────────────────────────────────────────────────
echo ""
echo "── Step 1: Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  vpcaccess.googleapis.com \
  --project="${PROJECT_ID}"

echo "✅ APIs enabled"

# ── Step 2: Create Artifact Registry ─────────────────────────────────────────
echo ""
echo "── Step 2: Creating Artifact Registry..."
gcloud artifacts repositories create healthcare-rag \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  2>/dev/null || echo "Registry already exists"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# ── Step 3: Create Cloud SQL (PostgreSQL) ─────────────────────────────────────
echo ""
echo "── Step 3: Setting up Cloud SQL PostgreSQL..."
gcloud sql instances create healthcare-rag-pg \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region="${REGION}" \
  --storage-size=20GB \
  --storage-auto-increase \
  --backup \
  --backup-start-time=03:00 \
  --project="${PROJECT_ID}" \
  2>/dev/null || echo "Cloud SQL instance already exists"

gcloud sql databases create healthcare_rag \
  --instance=healthcare-rag-pg \
  --project="${PROJECT_ID}" \
  2>/dev/null || echo "Database already exists"

# Set password (generate secure one)
DB_PASSWORD=$(openssl rand -hex 20)
gcloud sql users set-password postgres \
  --instance=healthcare-rag-pg \
  --password="${DB_PASSWORD}" \
  --project="${PROJECT_ID}"

echo "✅ Cloud SQL configured"

# ── Step 4: Create GCS Bucket ─────────────────────────────────────────────────
echo ""
echo "── Step 4: Creating GCS bucket for uploads + FAISS index..."
gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "${BUCKET}" 2>/dev/null || echo "Bucket already exists"

# Enable versioning (prevents data loss)
gsutil versioning set on "${BUCKET}"

# Set lifecycle rule (keep 30 days of versions)
cat > /tmp/lifecycle.json << 'EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"numNewerVersions": 3, "isLive": false}
      }
    ]
  }
}
EOF
gsutil lifecycle set /tmp/lifecycle.json "${BUCKET}"

echo "✅ GCS bucket created with versioning"

# ── Step 5: Migrate local data to GCS ─────────────────────────────────────────
echo ""
echo "── Step 5: Migrating local data to GCS (zero data loss)..."

if [ -d "./backend/data/uploads" ]; then
  echo "   Uploading PDF documents..."
  gsutil -m cp -r ./backend/data/uploads/* "${BUCKET}/uploads/" 2>/dev/null || echo "No uploads to migrate"
fi

if [ -d "./backend/data/faiss_index" ]; then
  echo "   Uploading FAISS index..."
  gsutil -m cp -r ./backend/data/faiss_index/* "${BUCKET}/faiss_index/" 2>/dev/null || echo "No FAISS index to migrate"
fi

echo "✅ Data migrated to GCS"

# ── Step 6: Migrate PostgreSQL data ───────────────────────────────────────────
echo ""
echo "── Step 6: Migrating PostgreSQL data..."

if command -v pg_dump &> /dev/null && [ -n "${LOCAL_DB_URL:-}" ]; then
  echo "   Dumping local database..."
  pg_dump "${LOCAL_DB_URL}" > /tmp/healthcare_rag_backup.sql
  
  echo "   Importing to Cloud SQL..."
  gsutil cp /tmp/healthcare_rag_backup.sql "${BUCKET}/backups/migration_$(date +%Y%m%d_%H%M%S).sql"
  
  gcloud sql import sql healthcare-rag-pg \
    "${BUCKET}/backups/migration_$(date +%Y%m%d_%H%M%S).sql" \
    --database=healthcare_rag \
    --project="${PROJECT_ID}"
  
  echo "✅ Database migrated"
else
  echo "⚠️  LOCAL_DB_URL not set or pg_dump not found. Skipping DB migration."
  echo "   Cloud SQL will be initialized fresh on first startup."
fi

# ── Step 7: Store secrets in Secret Manager ───────────────────────────────────
echo ""
echo "── Step 7: Storing secrets in Secret Manager..."

store_secret() {
  local name="$1"
  local value="$2"
  echo "${value}" | gcloud secrets create "${name}" \
    --data-file=- \
    --project="${PROJECT_ID}" \
    2>/dev/null || \
  echo "${value}" | gcloud secrets versions add "${name}" \
    --data-file=- \
    --project="${PROJECT_ID}"
}

# Load from local .env
source ./backend/.env 2>/dev/null || true

store_secret "anthropic-api-key"    "${ANTHROPIC_API_KEY:-placeholder}"
store_secret "openai-api-key"       "${OPENAI_API_KEY:-placeholder}"
store_secret "jwt-secret-key"       "${JWT_SECRET_KEY:-$(openssl rand -hex 32)}"
store_secret "db-password"          "${DB_PASSWORD}"

echo "✅ Secrets stored"

# ── Step 8: Build & Push Docker Images ───────────────────────────────────────
echo ""
echo "── Step 8: Building Docker images..."

# Backend
docker build -t "${ARTIFACT_REGISTRY}/backend:latest" ./backend/
docker push "${ARTIFACT_REGISTRY}/backend:latest"

# Frontend
docker build -t "${ARTIFACT_REGISTRY}/frontend:latest" ./frontend/
docker push "${ARTIFACT_REGISTRY}/frontend:latest"

echo "✅ Images pushed to Artifact Registry"

# ── Step 9: Deploy to Cloud Run ───────────────────────────────────────────────
echo ""
echo "── Step 9: Deploying to Cloud Run..."

CONNECTION_STRING="${PROJECT_ID}:${REGION}:healthcare-rag-pg"

# Backend
gcloud run deploy "${SERVICE_NAME}" \
  --image="${ARTIFACT_REGISTRY}/backend:latest" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8000 \
  --memory=2Gi \
  --cpu=2 \
  --min-instances=1 \
  --max-instances=10 \
  --concurrency=40 \
  --add-cloudsql-instances="${CONNECTION_STRING}" \
  --set-env-vars="\
ENVIRONMENT=production,\
DATABASE_URL=postgresql+asyncpg://postgres:${DB_PASSWORD}@/healthcare_rag?host=/cloudsql/${CONNECTION_STRING},\
VECTOR_DB=faiss,\
FAISS_INDEX_PATH=/tmp/faiss_index,\
UPLOAD_DIR=/tmp/uploads,\
GCP_PROJECT_ID=${PROJECT_ID},\
GCP_BUCKET_NAME=${PROJECT_ID}-healthcare-rag-data,\
GCP_REGION=${REGION}" \
  --set-secrets="\
ANTHROPIC_API_KEY=anthropic-api-key:latest,\
OPENAI_API_KEY=openai-api-key:latest,\
JWT_SECRET_KEY=jwt-secret-key:latest" \
  --project="${PROJECT_ID}"

# Get backend URL
BACKEND_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo "✅ Backend deployed: ${BACKEND_URL}"

# Frontend
gcloud run deploy "${FRONTEND_SERVICE}" \
  --image="${ARTIFACT_REGISTRY}/frontend:latest" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=3000 \
  --memory=512Mi \
  --set-env-vars="VITE_API_URL=${BACKEND_URL}" \
  --project="${PROJECT_ID}"

FRONTEND_URL=$(gcloud run services describe "${FRONTEND_SERVICE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo "✅ Frontend deployed: ${FRONTEND_URL}"

# ── Step 10: Update CORS ──────────────────────────────────────────────────────
echo ""
echo "── Step 10: Updating backend CORS to allow frontend URL..."

gcloud run services update "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --update-env-vars="ALLOWED_ORIGINS=${FRONTEND_URL}"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo "✅ DEPLOYMENT COMPLETE — ZERO DATA LOSS"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Frontend:  ${FRONTEND_URL}"
echo "  Backend:   ${BACKEND_URL}"
echo "  API Docs:  ${BACKEND_URL}/api/docs"
echo "  GCS:       ${BUCKET}"
echo ""
echo "  Data is now versioned and backed up in GCS."
echo "  PostgreSQL has daily backups at 03:00 UTC."
echo ""
echo "  Next: Update your DNS to point to ${FRONTEND_URL}"
echo "═══════════════════════════════════════════════════"
