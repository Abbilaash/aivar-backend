# AIVAR — Autonomous AI Asset Registry Backend

AIVAR automatically monitors Kubernetes workloads, detects AI-related deployments, scores risk, maintains a centralized asset inventory, records audit logs, and alerts for ownerless assets.

---

## Technical Stack
- **Python**: 3.12
- **Framework**: FastAPI (Asynchronous)
- **Database ORM**: SQLAlchemy 2.0 Async ORM + asyncpg
- **Migrations**: Alembic
- **Monitoring**: Kubernetes Python client watcher & Prometheus metrics
- **Database Engine**: PostgreSQL (Supabase)

---

## Security Architecture & Secret Handling
AIVAR enforces absolute privacy for sensitive Kubernetes credentials and application API-keys:
- **No Secret Storage**: The database and application memory *never* store or log API key values, passwords, cluster token values, or Kubeconfig content.
- **Safe Metadata Collection**: The Kubernetes Discovery Watcher only inspects non-secret metadata (workload names, namespaces, image references, labels, annotation keys, env variable names [excluding values], service account names, ConfigMap names, volume mount structure, etc.).
- **API Key Protection**: Non-monitoring routes are guarded via the `X-API-Key` header with a developer mode bypass for local testing.

---

## Database Configuration (Supabase)
AIVAR connects to **Supabase PostgreSQL** using SQLAlchemy async engines.

### Connection URL Modes:
1. **Direct Connection (IPv6)**: Use when deploying in an environment that supports IPv6.
   `postgresql+asyncpg://postgres:[YOUR_DB_PASSWORD]@[YOUR_DB_HOST]:5432/postgres`
2. **Session Pooler (Supavisor)**: Use in container/serverless environments with IPv4 fallbacks or dynamic connections.
   `postgresql+asyncpg://postgres.[YOUR_PROJECT_REF]:[YOUR_DB_PASSWORD]@aws-0-us-west-1.pooler.supabase.com:5432/postgres`

Configure this exclusively via the `DATABASE_URL` environment variable.

---

## Local Run Instructions

### Prerequisites
- Python 3.12
- Docker and Docker Compose

### 1. Setup Local Environment
Create `.env` based on `.env.example`:
```bash
cp .env.example .env
```
Modify `DATABASE_URL` in `.env` to point to your Supabase PostgreSQL database.

### 2. Start Application Locally
Initialize a virtual environment and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Run Alembic migrations to construct the database schema:
```bash
alembic upgrade head
```

Launch the FastAPI application:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser to view the OpenAPI docs.

---

## Local Run with Docker Compose
If you want to run a local postgres DB along with the backend without manually setting up Python:
```bash
docker compose up --build
```
This automatically configures a local Postgres container and runs the database migrations.

---

## Kubernetes Deployment Commands

### 1. Create the Secret
Create the database credential secret directly in your cluster without saving the raw connection string to source control:
```bash
kubectl create secret generic aivar-backend-secrets \
  --from-literal=DATABASE_URL="postgresql+asyncpg://postgres:[YOUR_DB_PASSWORD]@[YOUR_DB_HOST]:5432/postgres" \
  --namespace default
```

### 2. Deploy ConfigMap and RBAC rules
```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/rbac.yaml
```

### 3. Run Database Migrations Job
Apply the migration job first to align the schema:
```bash
kubectl apply -f k8s/migration-job.yaml
```

### 4. Deploy Application Deployment and Service
```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

---

## REST Endpoints Examples

All non-monitoring API calls require authentication via the `X-API-Key` header (except in development mode).

### 1. Get Discovered Assets
```bash
curl -H "X-API-Key: aivar-dev-secret-key-12345" \
  "http://localhost:8000/api/v1/assets?risk_tier=high&status=active"
```

### 2. Get Asset Changes (Past 24 hours)
```bash
curl -H "X-API-Key: aivar-dev-secret-key-12345" \
  "http://localhost:8000/api/v1/changes?since_hours=24"
```

### 3. Get Active Alerts
```bash
curl -H "X-API-Key: aivar-dev-secret-key-12345" \
  "http://localhost:8000/api/v1/alerts?status=open"
```

### 4. Resolve Alert
```bash
curl -X PATCH -H "X-API-Key: aivar-dev-secret-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"status": "resolved"}' \
  "http://localhost:8000/api/v1/alerts/{alert_id}"
```

### 5. Health Check
```bash
curl "http://localhost:8000/healthz"
```
