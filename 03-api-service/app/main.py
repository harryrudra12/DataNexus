"""
DataNexus Era 3 — FastAPI Application
Wires all routers, middleware, lifespan events, and observability.

Production entry point:
uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import time
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram

from .core.config import get_settings
from .core.logging import (
    configure_logging,
    get_logger,
    new_request_id,
    request_id_var,
    user_id_var,
    tenant_id_var,
)
from .services.fabric import get_fabric_service

from .routers import auth as auth_router
from .routers import audit as audit_router
from .routers import compliance as compliance_router
from .routers import health as health_router
from .routers import ingest as ingest_router
from .routers import intent as intent_router
from .routers import lineage as lineage_router
from .routers import pipelines as pipelines_router
from .routers import query as query_router
from .routers import dashboard as dashboard_router


settings = get_settings()
logger = get_logger(__name__)


# ─── Prometheus metrics ──────────────────────────────────────
http_requests_total = Counter(
    "datanexus_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

http_request_duration = Histogram(
    "datanexus_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


# ─── Lifespan: startup + shutdown ────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage app lifecycle:
    - configure logging
    - initialize Fabric service if available
    - continue startup even if Fabric is unavailable in local mode
    """
    configure_logging()

    logger.info(
        "datanexus_starting",
        version=settings.app_version,
        environment=settings.app_env,
        fabric_mode=settings.fabric_mode,
    )

    fabric = get_fabric_service()

    try:
        await fabric.initialize()
        logger.info("fabric_initialized", channel=settings.fabric_channel_name)
    except Exception as e:
        logger.error("fabric_init_failed", error=str(e))
        logger.info("continuing_without_fabric", mode="local_fallback")

    logger.info(
        "datanexus_ready",
        host=settings.host,
        port=settings.port,
        docs_url=f"http://{settings.host}:{settings.port}/docs",
    )

    yield

    logger.info("datanexus_shutting_down")

    try:
        await fabric.close()
    except Exception as e:
        logger.error("fabric_shutdown_failed", error=str(e))

    logger.info("datanexus_stopped")


# ─── App ─────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "DataNexus Era 3 — open-source data fabric with blockchain-verified compliance, "
        "Six Sigma quality enforcement, and NLP queries in Indian languages.\n\n"
        "**Built on Hadoop · Guided by the Gita · Six Sigma enforced**"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={"name": "DataNexus", "url": "https://datanexus.io"},
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
)


# ─── CORS: local + configured origins ────────────────────────
local_cors_origins = [
    "http://localhost:13000",
    "http://127.0.0.1:13000",
    "http://localhost:18000",
    "http://127.0.0.1:18000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:13001",
    "http://127.0.0.1:13001",
]

configured_origins = list(settings.cors_origins or [])
cors_origins = sorted(set(configured_origins + local_cors_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
        "X-DataNexus-Sigma",
        "X-DataNexus-Version",
    ],
)


# ─── Trusted host middleware: production only ────────────────
if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "datanexus.io",
            "*.datanexus.io",
            "api.datanexus.io",
        ],
    )


# ─── Request context middleware ──────────────────────────────
@app.middleware("http")
async def request_context_middleware(request: Request, call_next: Callable) -> Response:
    """
    Per request:
    - attach correlation ID
    - structured request logs
    - Prometheus metrics
    - useful response headers
    """
    rid = request.headers.get("x-request-id") or new_request_id()

    request_id_var.set(rid)
    user_id_var.set("")
    tenant_id_var.set("")

    start = time.time()
    method = request.method
    path = request.url.path

    is_noisy = path in ("/health", "/ready", "/metrics", "/favicon.ico")

    if not is_noisy:
        logger.info("request_started", method=method, path=path)

    try:
        response = await call_next(request)
        duration = time.time() - start

        if not is_noisy:
            logger.info(
                "request_completed",
                method=method,
                path=path,
                status=response.status_code,
                duration_ms=round(duration * 1000, 2),
            )

        normalized_path = _normalize_path(path)

        http_requests_total.labels(
            method=method,
            path=normalized_path,
            status=response.status_code,
        ).inc()

        http_request_duration.labels(
            method=method,
            path=normalized_path,
        ).observe(duration)

        response.headers["X-Request-ID"] = rid
        response.headers["X-DataNexus-Version"] = settings.app_version
        response.headers["X-DataNexus-Mode"] = settings.app_env

        return response

    except Exception as e:
        duration = time.time() - start

        logger.exception(
            "request_failed",
            method=method,
            path=path,
            duration_ms=round(duration * 1000, 2),
            error=str(e),
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "detail": "An unexpected error occurred. Reference: " + rid,
                "request_id": rid,
            },
            headers={"X-Request-ID": rid},
        )


def _normalize_path(path: str) -> str:
    """Collapse high-cardinality path segments for metrics labels."""
    import re

    path = re.sub(r"/[a-f0-9-]{8,}", "/{id}", path)
    path = re.sub(r"/\d+", "/{id}", path)
    return path


# ─── Global exception handler ────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — never leak stack traces to clients."""
    rid = request_id_var.get() or "unknown"

    logger.exception(
        "unhandled_exception",
        error=str(exc),
        request_id=rid,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "Reference this ID with support: " + rid,
            "request_id": rid,
        },
    )


# ─── Routers ─────────────────────────────────────────────────
app.include_router(health_router.router)
app.include_router(auth_router.router)
app.include_router(ingest_router.router)
app.include_router(compliance_router.router)
app.include_router(lineage_router.router)
app.include_router(lineage_router.fabric_router)
app.include_router(pipelines_router.router)
app.include_router(audit_router.router)
app.include_router(query_router.router)
app.include_router(intent_router.router)
app.include_router(dashboard_router.router)


# ─── UI-friendly root/status endpoints ───────────────────────
@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "mode": settings.app_env,
        "tagline": "Built on Hadoop. Guided by the Gita. Six Sigma enforced.",
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
        "api_base": "http://localhost:18000",
        "ui_base": "http://localhost:13000",
    }


@app.get("/api/status", tags=["health"])
async def api_status() -> dict:
    """
    Lightweight endpoint for the static UI to confirm API connectivity.
    """
    return {
        "status": "online",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "fabric_mode": settings.fabric_mode,
        "api_base": "http://localhost:18000",
        "ui_base": "http://localhost:13000",
        "cors_origins": cors_origins,
    }


@app.get("/api/v1/status", tags=["health"])
async def api_v1_status() -> dict:
    """
    Compatibility endpoint for UI code that expects /api/v1/status.
    """
    return {
        "status": "online",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "fabric_mode": settings.fabric_mode,
    }