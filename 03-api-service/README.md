# DataNexus Era 3 — API Service

The production FastAPI service that wires together every DataNexus Era 3 component.
This is the spine of the platform — the dashboard calls it, customers integrate with it,
Kubernetes deploys it.

## What is in this folder

```
api-service/
├── app/
│   ├── core/
│   │   ├── config.py     Pydantic Settings — every env var validated
│   │   ├── logging.py    Structured logging with correlation IDs
│   │   └── auth.py       JWT + API keys + 7 roles + 11 permissions
│   ├── models/
│   │   └── schemas.py    Pydantic request/response models
│   ├── services/
│   │   └── fabric.py     Hyperledger Fabric service wrapper + circuit breaker
│   ├── routers/
│   │   ├── health.py     /health, /ready, /metrics
│   │   ├── auth.py       /auth/login, /auth/me
│   │   ├── ingest.py     /api/v1/ingest (with quality gate)
│   │   ├── compliance.py /api/v1/compliance/border + /report
│   │   ├── lineage.py    /api/v1/lineage, /dataset, /fabric/status
│   │   ├── query.py      /api/v1/query/nlp (Telugu/Hindi/English)
│   │   └── intent.py     /api/v1/pipeline/intent (AI OS)
│   └── main.py           FastAPI app + lifespan + middleware + routers
├── tests/
│   └── test_api_e2e.py   End-to-end tests covering every endpoint
├── deploy/               Kubernetes manifests (next session)
├── Dockerfile            Multi-stage production build
├── requirements.txt      Pinned dependencies
├── verify.sh             One-command local verification
└── README.md             (this file)
```

## Quick start

### Local development

```bash
# 1. One-time setup
cd era3/api-service
bash verify.sh   # creates .venv, installs deps, runs tests

# 2. Start the service
source .venv/bin/activate
uvicorn app.main:app --reload

# 3. Open the docs
open http://localhost:8000/docs
```

### Docker

```bash
docker build -t datanexus-api:latest .
docker run -p 8000:8000 \
    -e APP_ENV=development \
    -e FABRIC_MODE=simulation \
    datanexus-api:latest
```

## Endpoints

| Method | Path                              | What it does                            |
| ------ | --------------------------------- | --------------------------------------- |
| `GET`  | `/health`                         | Liveness probe                           |
| `GET`  | `/ready`                          | Readiness probe with dependency checks   |
| `GET`  | `/metrics`                        | Prometheus metrics                       |
| `POST` | `/auth/login`                     | Get a JWT                                |
| `GET`  | `/auth/me`                        | Current user info                        |
| `POST` | `/api/v1/ingest`                  | Ingest data with quality + blockchain    |
| `GET`  | `/api/v1/dataset/{id}`            | Dataset metadata                         |
| `GET`  | `/api/v1/lineage/{id}`            | Full blockchain-verified lineage         |
| `POST` | `/api/v1/compliance/border`       | DPDP/GDPR/HIPAA border check             |
| `GET`  | `/api/v1/compliance/report/{id}`  | 60-second compliance report              |
| `POST` | `/api/v1/query/nlp`               | Telugu/Hindi/English → Presto SQL        |
| `POST` | `/api/v1/pipeline/intent`         | Natural language → deployed Airflow DAG  |
| `GET`  | `/api/v1/fabric/status`           | Zero-gravity fabric status               |

Full interactive docs at `http://localhost:8000/docs` once running.

## Demo credentials

| Username       | Password      | Role                       |
| -------------- | ------------- | -------------------------- |
| `admin`        | `admin123`    | Super admin                |
| `apollo_admin` | `apollo2025`  | Tenant admin + Data owner  |
| `auditor_dpdp` | `audit2025`   | Auditor                    |

In production, replace `_DEMO_USERS` in `app/routers/auth.py` with PostgreSQL + bcrypt.

## Configuration

Every setting is driven by environment variables. See `app/core/config.py` for the full list.

Critical for production:

```bash
APP_ENV=production
JWT_SECRET_KEY=$(openssl rand -hex 32)   # required — refuses to start with default
FABRIC_MODE=production
FABRIC_NETWORK_PROFILE=/etc/datanexus/fabric.yaml
POSTGRES_DSN=postgresql+asyncpg://...
```

## Testing

```bash
pytest tests/ -v              # all tests
pytest tests/ -v -k auth      # only auth tests
pytest tests/ --cov=app       # with coverage
```

The end-to-end test suite covers:

- Health and readiness endpoints
- Login with valid/invalid/unknown credentials
- Ingest with valid data, quarantined data, and validation errors
- Lineage retrieval after ingest
- DPDP blocks Indian PII to US (DPDP-001)
- DPDP allows within-India transfer with multi-sig
- GDPR blocks EU data to non-adequate country
- Telugu and Hindi NLP queries auto-translate to SQL
- Intent → DAG with custom schedules
- Fabric status returns expected nodes
- Request correlation headers
- OpenAPI schema completeness

## Production deployment notes

- **Auth secret**: app refuses to start in production with the default JWT key.
- **Auth backend**: replace the in-memory `_DEMO_USERS` dict in `auth.py` with PostgreSQL.
- **API keys**: replace `APIKeyStore` with a Postgres-backed table.
- **Fabric**: set `FABRIC_MODE=production` and provide a Hyperledger network profile.
- **CORS**: set `CORS_ORIGINS` to your actual frontend domains.
- **Workers**: behind a load balancer, run with `--workers $(nproc)`.
- **Observability**: scrape `/metrics` with Prometheus, point `SENTRY_DSN` at your Sentry org.

## Wiring the dashboard

The React dashboard (`DataNexus_Dashboard.html`) currently uses static demo data.
Wiring it to this API is the next session — replace each demo array with `fetch()` calls to the relevant endpoint.

---

DataNexus · datanexus.io · Apache 2.0 · 2025
*Built on Hadoop · Guided by the Gita · Six Sigma enforced*
