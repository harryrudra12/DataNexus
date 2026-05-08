"""
DataNexus Era 3 — End-to-end API test.

Walks the full critical path:
  1. /health    — service is alive
  2. /auth/login — get a JWT
  3. /api/v1/ingest — write data with blockchain logging
  4. /api/v1/lineage/{id} — verify the write produced a lineage record
  5. /api/v1/compliance/border — DPDP blocks illegal transfer
  6. /api/v1/query/nlp — Telugu query translates to SQL
  7. /api/v1/pipeline/intent — natural language to deployed DAG
  8. /api/v1/fabric/status — fabric reports nodes online

Run:
    cd era3/api-service
    pip install -r requirements.txt
    pytest tests/test_api_e2e.py -v
"""
import os
import pytest
from httpx import ASGITransport, AsyncClient

# Disable auth requirement for the test fixture below
os.environ["REQUIRE_AUTH"] = "false"
os.environ["APP_ENV"] = "testing"
os.environ["FABRIC_MODE"] = "simulation"

from app.main import app  # noqa: E402


@pytest.fixture
async def client():
    """Async HTTP client bound directly to the FastAPI app — no network."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        # Trigger lifespan startup so the fabric service initializes
        async with ac.stream("GET", "/health"):
            pass
        yield ac


@pytest.fixture
async def auth_token(client):
    """Login and return a Bearer token."""
    resp = await client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ─── 1. HEALTH ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_health_returns_healthy(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["version"].startswith("3.")
    assert "uptime_seconds" in body["checks"]


@pytest.mark.asyncio
async def test_readiness_includes_fabric_check(client):
    resp = await client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert "fabric" in body["checks"]
    assert "kafka" in body["checks"]
    assert "presto" in body["checks"]


@pytest.mark.asyncio
async def test_root_returns_service_info(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "DataNexus API"
    assert "Hadoop" in body["tagline"]


# ─── 2. AUTH ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_login_with_valid_credentials(client):
    resp = await client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert len(body["access_token"]) > 50
    assert body["user_id"] == "u-admin-001"


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client):
    resp = await client.post(
        "/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_rejects_unknown_user(client):
    resp = await client.post(
        "/auth/login",
        json={"username": "ghost", "password": "anypassword"},
    )
    assert resp.status_code == 401


# ─── 3. INGEST ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ingest_creates_dataset_with_blockchain_proof(client, auth_token):
    resp = await client.post(
        "/api/v1/ingest",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "dataset_name":   "patient_test_jan2025",
            "data":           "patient_id,age,bp\nP001,45,120\nP002,62,140\nP003,38,118",
            "data_format":    "csv",
            "classification": "HEALTH",
            "jurisdictions":  ["DPDP_2023", "HIPAA"],
            "allowed_regions":["IN", "IN-TG"],
            "purpose":        "medical_treatment",
            "node_id":        "dn-hyderabad-01",
            "topic":          "datanexus.health.test",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ingested"
    assert body["dataset_id"].startswith("ds-")
    assert len(body["content_hash"]) == 64  # SHA-256
    assert body["sigma"] >= 4.5
    assert body["fabric_tx_id"]
    return body  # returned for chained tests


@pytest.mark.asyncio
async def test_ingest_quarantines_garbage_data(client, auth_token):
    """Sigma below 4.0 should reject the ingest with 422."""
    resp = await client.post(
        "/api/v1/ingest",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "dataset_name":   "garbage_data",
            "data":           ",,,,,,,,,,,,,,,,,,,",  # empty fields trigger sigma penalty
            "data_format":    "csv",
            "classification": "INTERNAL",
            "jurisdictions":  ["DPDP_2023"],
            "allowed_regions":["IN"],
            "purpose":        "test",
        },
    )
    assert resp.status_code == 422
    assert "quarantined" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ingest_rejects_invalid_dataset_name(client, auth_token):
    """Names with uppercase or special chars should fail validation."""
    resp = await client.post(
        "/api/v1/ingest",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "dataset_name":   "Bad-Name!",
            "data":           "x,y\n1,2",
            "data_format":    "csv",
            "classification": "INTERNAL",
            "jurisdictions":  ["DPDP_2023"],
            "allowed_regions":["IN"],
            "purpose":        "test",
        },
    )
    assert resp.status_code == 422  # Pydantic validation error


# ─── 4. LINEAGE ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_lineage_reflects_ingest(client, auth_token):
    """An ingested dataset must show up in /lineage/{id}."""
    # Ingest first
    ingest = await client.post(
        "/api/v1/ingest",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "dataset_name":   "lineage_test_data",
            "data":           "a,b\n1,2\n3,4",
            "data_format":    "csv",
            "classification": "INTERNAL",
            "jurisdictions":  ["DPDP_2023"],
            "allowed_regions":["IN"],
            "purpose":        "test",
        },
    )
    dataset_id = ingest.json()["dataset_id"]

    # Now read lineage
    resp = await client.get(
        f"/api/v1/lineage/{dataset_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dataset_id"] == dataset_id
    assert body["total"] >= 1
    assert body["integrity"] is True


# ─── 5. COMPLIANCE ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_dpdp_blocks_indian_pii_to_us(client, auth_token):
    """DPDP-001: Indian PII must not leave India without consent."""
    resp = await client.post(
        "/api/v1/compliance/border",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "dataset_id":      "test-dataset-001",
            "target_country":  "US",
            "purpose":         "pharma_research",
            "jurisdictions":   ["DPDP_2023"],
            "classification":  "PII",
            "has_consent":     False,
            "signature_count": 0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "BLOCKED"
    assert "DPDP" in body["reason"] or "DPDP-001" in body["reason"]
    assert any("DPDP" in v["law"] for v in body["violations"])


@pytest.mark.asyncio
async def test_dpdp_allows_within_india_with_multisig(client, auth_token):
    """Within-India transfer with consent + 3 signatures should be allowed."""
    resp = await client.post(
        "/api/v1/compliance/border",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "dataset_id":      "test-dataset-002",
            "target_country":  "IN-MH",
            "purpose":         "medical_treatment",
            "jurisdictions":   ["DPDP_2023"],
            "classification":  "HEALTH",
            "has_consent":     True,
            "signature_count": 3,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] in ("ALLOWED", "ALLOWED_WITH_FIX")


@pytest.mark.asyncio
async def test_gdpr_blocks_eu_data_to_singapore(client, auth_token):
    """GDPR-001: EU PII cannot go to non-adequate country."""
    resp = await client.post(
        "/api/v1/compliance/border",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "dataset_id":      "eu-customer-001",
            "target_country":  "SG",
            "purpose":         "analytics",
            "jurisdictions":   ["GDPR"],
            "classification":  "PII",
            "has_consent":     False,
            "signature_count": 0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "BLOCKED"
    assert any("GDPR" in v["law"] for v in body["violations"])


# ─── 6. NLP QUERY ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_telugu_query_translates_to_sql(client, auth_token):
    """Telugu input should auto-detect language and produce valid SQL."""
    resp = await client.post(
        "/api/v1/query/nlp",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "text":     "చివరి నెలలో అత్యధిక అమ్మకాలు ఏ ప్రాంతంలో",
            "language": "auto",
            "tables":   ["sales_transactions"],
            "execute":  True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "te"
    assert "SELECT" in body["sql"]
    assert "sales_transactions" in body["sql"]
    assert body["status"] == "executed"
    assert body["row_count"] is not None


@pytest.mark.asyncio
async def test_hindi_query_translates(client, auth_token):
    resp = await client.post(
        "/api/v1/query/nlp",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "text":     "पिछले महीने सबसे ज़्यादा बिक्री किस क्षेत्र में",
            "language": "hi",
            "tables":   ["sales"],
            "execute":  True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "SELECT" in body["sql"]


# ─── 7. INTENT (AI OS) ────────────────────────────────────────
@pytest.mark.asyncio
async def test_intent_to_deployed_pipeline(client, auth_token):
    """Natural language intent should produce an Airflow DAG."""
    resp = await client.post(
        "/api/v1/pipeline/intent",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "intent":   "Send daily sales reports for top 5 regions every morning at 6am",
            "language": "en",
            "tables":   ["sales_transactions"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pipeline_id"].startswith("auto-report-")
    assert body["intent_type"] == "REPORT"
    assert body["schedule"] == "0 6 * * *"
    assert body["status"] == "DEPLOYED"
    assert body["sigma_target"] >= 5.0


@pytest.mark.asyncio
async def test_intent_extracts_custom_schedule(client, auth_token):
    resp = await client.post(
        "/api/v1/pipeline/intent",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "intent":   "Generate quality report every 15 minutes",
            "tables":   ["datanexus_quality_log"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["schedule"] == "*/15 * * * *"


# ─── 8. FABRIC STATUS ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_fabric_status_returns_nodes(client, auth_token):
    resp = await client.get(
        "/api/v1/fabric/status",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_nodes"] >= 6
    assert body["online_nodes"] >= 6
    assert body["avg_sigma"] >= 4.0
    assert any(n["region"] == "IN-TG" for n in body["nodes"])


# ─── 9. REQUEST CORRELATION ───────────────────────────────────
@pytest.mark.asyncio
async def test_request_id_returned_in_headers(client):
    resp = await client.get("/health")
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) >= 16


@pytest.mark.asyncio
async def test_custom_request_id_is_echoed(client):
    custom_id = "my-trace-id-12345"
    resp = await client.get("/health", headers={"x-request-id": custom_id})
    assert resp.headers["x-request-id"] == custom_id


# ─── 10. OPENAPI SCHEMA ──────────────────────────────────────
@pytest.mark.asyncio
async def test_openapi_schema_is_valid(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "DataNexus API"
    paths = schema["paths"]
    # Verify every router is registered
    assert "/health" in paths
    assert "/auth/login" in paths
    assert "/api/v1/ingest" in paths
    assert "/api/v1/compliance/border" in paths
    assert "/api/v1/query/nlp" in paths
    assert "/api/v1/pipeline/intent" in paths
    assert "/api/v1/fabric/status" in paths
