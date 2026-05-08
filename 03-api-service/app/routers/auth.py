"""
DataNexus Era 3 — Auth Router
Login, token refresh, current user introspection.
"""
import hashlib
import hmac
from fastapi import APIRouter, Depends, HTTPException, status

from ..core.auth import (
    CurrentUser, Role, TokenResponse, LoginRequest as _LR,
    create_access_token, get_current_user,
)
from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.schemas import LoginRequest

router   = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger   = get_logger(__name__)


# ─── Demo user store (in production: Postgres + bcrypt) ───────
_DEMO_USERS = {
    "admin": {
        "user_id":        "u-admin-001",
        "tenant_id":      "datanexus-internal",
        # bcrypt-equivalent for demo: sha256("admin123") = 240be518...
        "password_hash":  "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9",
        "roles":          [Role.SUPER_ADMIN],
        "active":         True,
    },
    "apollo_admin": {
        "user_id":        "u-apollo-001",
        "tenant_id":      "tenant-apollo-hospital",
        # bcrypt-equivalent for demo: sha256("apollo2025")
        "password_hash":  "7085e9c9292f86f6e69c5c4da392a446c065a644749f733cc7ae273c7b4c538b",
        "roles":          [Role.TENANT_ADMIN, Role.DATA_OWNER],
        "active":         True,
    },
    "auditor_dpdp": {
        "user_id":        "u-auditor-001",
        "tenant_id":      "tenant-dpdp-board",
        # bcrypt-equivalent for demo: sha256("audit2025")
        "password_hash":  "1a822cc6d9855cb3c1ddc4f08fa9348103552bda3f0032eb922bc98f5e664d77",
        "roles":          [Role.AUDITOR],
        "active":         True,
    },
}


def _hash_password(password: str) -> str:
    """In production: use bcrypt. SHA-256 here for demo only."""
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(plaintext: str, stored_hash: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    return hmac.compare_digest(_hash_password(plaintext), stored_hash)


@router.post("/login", response_model=TokenResponse, summary="Issue an access token")
async def login(body: LoginRequest) -> TokenResponse:
    """Exchange username + password for a JWT."""
    user = _DEMO_USERS.get(body.username)

    if not user or not user["active"]:
        logger.warning("login_failed_unknown_user", username=body.username[:32])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not _verify_password(body.password, user["password_hash"]):
        logger.warning("login_failed_bad_password", username=body.username[:32])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Tenant override (super-admins can act on behalf of any tenant)
    tenant = body.tenant_id or user["tenant_id"]
    if tenant != user["tenant_id"] and Role.SUPER_ADMIN not in user["roles"]:
        raise HTTPException(403, detail="Cannot impersonate other tenant")

    token, expires_in = create_access_token(
        user_id   = user["user_id"],
        tenant_id = tenant,
        roles     = user["roles"],
    )

    logger.info("login_success",
                user_id=user["user_id"], tenant_id=tenant,
                roles=[r.value for r in user["roles"]])

    return TokenResponse(
        access_token = token,
        expires_in   = expires_in,
        user_id      = user["user_id"],
        tenant_id    = tenant,
        roles        = user["roles"],
    )


@router.get("/me", summary="Get current authenticated user")
async def me(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Returns the user info extracted from the auth token / API key."""
    return {
        "user_id":     user.user_id,
        "tenant_id":   user.tenant_id,
        "roles":       [r.value for r in user.roles],
        "permissions": [p.value for p in user.permissions],
        "is_service":  user.is_service,
    }
