"""Authentication and RBAC contract tests with enforcement enabled."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import auth as auth_core
from app.main import app


DEMO_API_KEY = "dn_dev_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"


@pytest.fixture(autouse=True)
def enforce_auth(monkeypatch):
    """Keep these tests independent from the auth-disabled E2E fixture."""
    monkeypatch.setattr(auth_core.settings, "require_auth", True)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client


async def login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_protected_route_rejects_missing_and_tampered_credentials(client):
    missing = await client.get("/api/v1/audit")

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"

    token = await login(client, "admin", "admin123")
    tampered = await client.get(
        "/api/v1/audit",
        headers={"Authorization": f"Bearer {token}tampered"},
    )

    assert tampered.status_code == 401
    assert tampered.json()["detail"] == "Invalid or expired token"


@pytest.mark.asyncio
async def test_auditor_can_view_audit_but_cannot_ingest(client):
    token = await login(client, "auditor_dpdp", "audit2025")
    headers = {"Authorization": f"Bearer {token}"}

    allowed = await client.get("/api/v1/audit", headers=headers)
    denied = await client.post(
        "/api/v1/ingest",
        headers=headers,
        json={
            "dataset_name": "rbac_denied_ingest",
            "data": "id,value\n1,allowed",
            "data_format": "csv",
            "classification": "INTERNAL",
            "jurisdictions": ["DPDP_2023"],
            "allowed_regions": ["IN"],
            "purpose": "rbac_test",
        },
    )

    assert allowed.status_code == 200
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Permission denied: data:ingest required"


@pytest.mark.asyncio
async def test_service_api_key_resolves_permissions_and_invalid_key_is_rejected(client):
    valid_headers = {"X-DataNexus-API-Key": DEMO_API_KEY}

    identity = await client.get("/auth/me", headers=valid_headers)
    query = await client.post(
        "/api/v1/query/nlp",
        headers=valid_headers,
        json={
            "text": "top regions by revenue",
            "language": "en",
            "tables": ["sales"],
            "execute": False,
        },
    )
    invalid = await client.get(
        "/auth/me",
        headers={"X-DataNexus-API-Key": "invalid-key"},
    )

    assert identity.status_code == 200
    assert identity.json()["is_service"] is True
    assert identity.json()["roles"] == ["service_account"]
    assert "data:query" in identity.json()["permissions"]
    assert query.status_code == 200
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "Invalid API key"


@pytest.mark.asyncio
async def test_only_super_admin_can_override_login_tenant(client):
    denied = await client.post(
        "/auth/login",
        json={
            "username": "apollo_admin",
            "password": "apollo2025",
            "tenant_id": "tenant-other",
        },
    )
    allowed = await client.post(
        "/auth/login",
        json={
            "username": "admin",
            "password": "admin123",
            "tenant_id": "tenant-other",
        },
    )

    assert denied.status_code == 403
    assert denied.json()["detail"] == "Cannot impersonate other tenant"
    assert allowed.status_code == 200
    assert allowed.json()["tenant_id"] == "tenant-other"

    identity = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {allowed.json()['access_token']}"},
    )
    assert identity.status_code == 200
    assert identity.json()["tenant_id"] == "tenant-other"
