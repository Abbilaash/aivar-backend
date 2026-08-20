# AIVAR — Autonomous AI Asset Registry Backend

AIVAR (AI Visibility & Asset Registry) automatically monitors Kubernetes workloads, detects AI-related deployments, scores risk, maintains a centralized asset inventory, records audit logs, and alerts for ownerless assets.

---

## Technical Stack
- **Python**: 3.12 / 3.13 (Supports modern Python versions)
- **Framework**: FastAPI (Asynchronous)
- **Database ORM**: SQLAlchemy 2.0 Async ORM + asyncpg
- **Monitoring**: Kubernetes Python client watcher & Prometheus metrics
- **Database Engine**: PostgreSQL (Supabase)

---

## Security Architecture & Secret Handling
AIVAR enforces absolute privacy for sensitive Kubernetes credentials and application API keys:
- **No Secret Storage**: The database and application memory *never* store or log API key values, passwords, cluster token values, or Kubeconfig content.
- **Safe Metadata Collection**: The Kubernetes Discovery Watcher only inspects non-secret metadata (workload names, namespaces, image references, labels, annotation keys, environment variable names [excluding values], service account names, ConfigMap names, volume mount structure, etc.).
- **API Key Protection**: Non-monitoring routes are guarded via the `X-API-Key` header with a developer mode bypass for local testing.

---

## Database Configuration (Supabase)
AIVAR connects to **Supabase PostgreSQL** using SQLAlchemy async engines.

### Connection URL Modes:
1. **Direct Connection (IPv6)**: Use when deploying in an environment that supports IPv6.
   `postgresql+asyncpg://postgres:[YOUR_DB_PASSWORD]@[YOUR_DB_HOST]:5432/postgres`
2. **Session Pooler (Supavisor)**: Use in container/serverless environments with IPv4 fallbacks or dynamic connections.
   `postgresql+asyncpg://postgres.[YOUR_PROJECT_REF]:[YOUR_DB_PASSWORD]@aws-0-us-west-1.pooler.supabase.com:6543/postgres?prepared_statement_cache_size=0`

Configure this exclusively via the `DATABASE_URL` environment variable.

---

## Environment Variables (`.env`)

AIVAR reads configurations using Pydantic Settings. Create a `.env` file in the root backend directory:

```ini
# Database Connection (Supabase PostgreSQL URL)
DATABASE_URL=postgresql+asyncpg://postgres.[YOUR_PROJECT_REF]:[YOUR_DB_PASSWORD]@aws-0-us-west-1.pooler.supabase.com:6543/postgres?prepared_statement_cache_size=0

# Application Settings
APP_ENV=development # development, production
LOG_LEVEL=INFO
API_KEY=aivar-dev-secret-key-12345

# Cluster Discovery Settings
WATCHER_ENABLED=true
CLUSTER_NAME=local-cluster
CLUSTER_ENVIRONMENT=development

# Reconciliation Intervals and Retry Settings
RECONCILIATION_INTERVAL_SECS=60
WATCHER_RETRY_DELAY_SECS=5
WATCHER_MAX_RETRY_DELAY_SECS=60

# EKS / Custom Kubeconfig configs (Optional)
KUBECONFIG_PATH=
AWS_REGION=
EKS_CLUSTER_NAME=

# AIVAR Copilot Chatbot (EKS Service)
CHATBOT_SERVICE_URL=http://localhost:8081/chat
```

---

## Local Run Instructions

### Prerequisites
- Python 3.12 / 3.13
- PostgreSQL Database (Local or Supabase)

### 1. Setup Local Environment
Create `.env` based on `.env.example`:
```bash
cp .env.example .env
```
Modify `DATABASE_URL` in `.env` to point to your Supabase PostgreSQL database.

### 2. Start Application Locally
Initialize a virtual environment and install dependencies:
```bash
python3.13 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Run migrations to construct the database schema:
```bash
# Option A: Run Alembic migrations
alembic upgrade head

# Option B: Run via raw SQL editor on Supabase
# Copy paste the statements in the backend/db_schema.sql into your SQL Editor.
```

Launch the FastAPI application:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser to view the OpenAPI docs.

---

## Local Run with Docker Compose
To run the backend application locally inside a container using Docker Compose:
1. Copy the `.env` file or export your `DATABASE_URL` environment variable.
2. Run:
   ```bash
   docker compose up --build
   ```
   *Note: This utilizes the database configured under `DATABASE_URL` in your `.env`.*

---

## Production Deployment on AWS EC2
For production deployment, AIVAR is designed to be served behind an Nginx Reverse Proxy managed by Gunicorn process managers.

### 1. Deploy systemd Service (`/etc/systemd/system/aivar-backend.service`)
```ini
[Unit]
Description=AIVAR Backend Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/aivar-backend
EnvironmentFile=/home/ubuntu/aivar-backend/.env
ExecStart=/home/ubuntu/aivar-backend/venv/bin/gunicorn app.main:app \
          --workers 5 \
          --worker-class uvicorn.workers.UvicornWorker \
          --bind 127.0.0.1:8000 \
          --access-logfile /var/log/aivar/access.log \
          --error-logfile /var/log/aivar/error.log \
          --keep-alive 55 \
          --graceful-timeout 30

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 2. Nginx Server Configuration (`/etc/nginx/sites-available/aivar-backend`)
```nginx
server {
    listen 80;
    server_name your-domain-or-ip;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
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
