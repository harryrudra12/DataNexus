"""
DataNexus Era 3 — Authentication & Authorization
JWT-based auth + API keys for service-to-service. Role-based + tenant-scoped.
"""
import time
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, List

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from .config import get_settings
from .logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ─── Roles (RBAC) ─────────────────────────────────────────────
class Role(str, Enum):
    SUPER_ADMIN     = "super_admin"      # DataNexus internal
    TENANT_ADMIN    = "tenant_admin"     # customer admin
    DATA_OWNER      = "data_owner"       # owns specific datasets
    DATA_ENGINEER   = "data_engineer"    # builds pipelines
    ANALYST         = "analyst"          # read-only queries
    AUDITOR         = "auditor"          # compliance/audit access
    SERVICE_ACCOUNT = "service_account"  # automated systems


class Permission(str, Enum):
    READ_DATASET     = "dataset:read"
    WRITE_DATASET    = "dataset:write"
    DELETE_DATASET   = "dataset:delete"
    INGEST_DATA      = "data:ingest"
    QUERY_DATA       = "data:query"
    MANAGE_PIPELINE  = "pipeline:manage"
    VIEW_LINEAGE     = "lineage:view"
    GENERATE_REPORT  = "report:generate"
    APPROVE_TRANSFER = "transfer:approve"
    MANAGE_USERS     = "users:manage"
    VIEW_AUDIT       = "audit:view"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SUPER_ADMIN: set(Permission),
    Role.TENANT_ADMIN: {
        Permission.READ_DATASET, Permission.WRITE_DATASET, Permission.INGEST_DATA,
        Permission.QUERY_DATA, Permission.MANAGE_PIPELINE, Permission.VIEW_LINEAGE,
        Permission.GENERATE_REPORT, Permission.APPROVE_TRANSFER, Permission.MANAGE_USERS,
        Permission.VIEW_AUDIT,
    },
    Role.DATA_OWNER: {
        Permission.READ_DATASET, Permission.WRITE_DATASET, Permission.INGEST_DATA,
        Permission.QUERY_DATA, Permission.VIEW_LINEAGE, Permission.GENERATE_REPORT,
        Permission.APPROVE_TRANSFER, Permission.VIEW_AUDIT,
    },
    Role.DATA_ENGINEER: {
        Permission.READ_DATASET, Permission.WRITE_DATASET, Permission.INGEST_DATA,
        Permission.QUERY_DATA, Permission.MANAGE_PIPELINE, Permission.VIEW_LINEAGE,
        Permission.GENERATE_REPORT,
    },
    Role.ANALYST: {
        Permission.READ_DATASET, Permission.QUERY_DATA, Permission.VIEW_LINEAGE,
    },
    Role.AUDITOR: {
        Permission.READ_DATASET, Permission.VIEW_LINEAGE, Permission.GENERATE_REPORT,
        Permission.VIEW_AUDIT,
    },
    Role.SERVICE_ACCOUNT: {
        Permission.READ_DATASET, Permission.WRITE_DATASET, Permission.INGEST_DATA,
        Permission.QUERY_DATA, Permission.VIEW_LINEAGE,
    },
}


# ─── Models ───────────────────────────────────────────────────
class TokenPayload(BaseModel):
    sub:       str           # user_id
    tenant_id: str
    roles:     List[Role]
    iat:       int
    exp:       int
    jti:       str           # JWT ID for revocation


class CurrentUser(BaseModel):
    user_id:     str
    tenant_id:   str
    roles:       List[Role]
    permissions: set[Permission]
    is_service:  bool = False

    def has_permission(self, perm: Permission) -> bool:
        return perm in self.permissions

    def has_role(self, role: Role) -> bool:
        return role in self.roles


class TokenResponse(BaseModel):
    access_token:  str
    token_type:    str = "Bearer"
    expires_in:    int
    user_id:       str
    tenant_id:     str
    roles:         List[Role]


# ─── Token operations ─────────────────────────────────────────
def create_access_token(
    user_id: str,
    tenant_id: str,
    roles: List[Role],
    ttl_minutes: Optional[int] = None,
) -> tuple[str, int]:
    """Create a signed JWT. Returns (token, expires_in_seconds)."""
    ttl = ttl_minutes or settings.jwt_access_ttl_minutes
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ttl)

    payload = {
        "sub":       user_id,
        "tenant_id": tenant_id,
        "roles":     [r.value for r in roles],
        "iat":       int(now.timestamp()),
        "exp":       int(expires_at.timestamp()),
        "jti":       hashlib.sha256(f"{user_id}{now.timestamp()}".encode()).hexdigest()[:16],
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, ttl * 60


def decode_token(token: str) -> TokenPayload:
    """Validate and decode a JWT. Raises HTTPException(401) on invalid."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as e:
        logger.warning("token_decode_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenPayload(
        sub=payload["sub"],
        tenant_id=payload["tenant_id"],
        roles=[Role(r) for r in payload.get("roles", [])],
        iat=payload["iat"],
        exp=payload["exp"],
        jti=payload["jti"],
    )


# ─── API Key store (in-memory for now; PostgreSQL in production) ──
class APIKeyStore:
    """Service-to-service API key validation. Backed by Postgres in prod."""

    def __init__(self):
        # In production, this is loaded from postgres api_keys table
        self._keys: dict[str, dict] = {
            # Demo key for local development only
            "dn_dev_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6": {
                "tenant_id": "tenant-dev-001",
                "user_id":   "service-account-dev",
                "roles":     [Role.SERVICE_ACCOUNT],
                "active":    True,
                "created":   "2025-01-01T00:00:00Z",
            },
        }

    def validate(self, api_key: str) -> Optional[dict]:
        """Constant-time API key validation."""
        for stored_key, meta in self._keys.items():
            if hmac.compare_digest(api_key, stored_key) and meta["active"]:
                return meta
        return None


_api_key_store = APIKeyStore()


# ─── FastAPI dependencies ─────────────────────────────────────
bearer_scheme   = HTTPBearer(auto_error=False)
api_key_scheme  = APIKeyHeader(name=settings.api_key_header, auto_error=False)


async def get_current_user(
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
) -> CurrentUser:
    """
    Resolve the current user from either:
      1. Authorization: Bearer <jwt>  (interactive users)
      2. X-DataNexus-API-Key: <key>   (service accounts)
    """
    if not settings.require_auth:
        # Dev mode: synthetic super-admin
        return CurrentUser(
            user_id="dev-user", tenant_id="tenant-dev",
            roles=[Role.SUPER_ADMIN],
            permissions=ROLE_PERMISSIONS[Role.SUPER_ADMIN],
        )

    # Try API key first (more common for service accounts)
    if api_key:
        meta = _api_key_store.validate(api_key)
        if not meta:
            raise HTTPException(401, detail="Invalid API key")
        roles = meta["roles"]
        perms = set().union(*(ROLE_PERMISSIONS[r] for r in roles))
        return CurrentUser(
            user_id=meta["user_id"], tenant_id=meta["tenant_id"],
            roles=roles, permissions=perms, is_service=True,
        )

    # Fall back to JWT
    if bearer and bearer.credentials:
        payload = decode_token(bearer.credentials)
        perms = set().union(*(ROLE_PERMISSIONS[r] for r in payload.roles))
        return CurrentUser(
            user_id=payload.sub, tenant_id=payload.tenant_id,
            roles=payload.roles, permissions=perms,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required — provide Bearer JWT or API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_permission(permission: Permission):
    """Dependency factory: enforce a permission requirement on an endpoint."""
    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_permission(permission):
            logger.warning(
                "permission_denied",
                user_id=user.user_id, required=permission.value,
                roles=[r.value for r in user.roles],
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required",
            )
        return user
    return _check


def require_role(role: Role):
    """Dependency factory: enforce role membership."""
    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_role(role) and not user.has_role(Role.SUPER_ADMIN):
            raise HTTPException(403, detail=f"Role required: {role.value}")
        return user
    return _check
