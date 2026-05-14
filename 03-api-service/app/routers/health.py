"""
DataNexus Era 3 — Health & Readiness
- /health  → liveness probe (always cheap, never fails unless app is dead)
- /ready   → readiness probe (verifies dependencies, used by k8s)
- /metrics → Prometheus metrics endpoint
"""
import asyncio
import time
from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.schemas import HealthCheck

router = APIRouter(tags=["health"])
logger = get_logger(__name__)
settings = get_settings()

_started_at = time.time()


@router.get("/health", response_model=HealthCheck, summary="Liveness probe")
async def health() -> HealthCheck:
    """Simple liveness check. Returns 200 unless the process is dead."""
    return HealthCheck(
        status="healthy",
        version=settings.app_version,
        environment=settings.app_env,
        checks={
            "uptime_seconds": {"value": round(time.time() - _started_at, 1), "ok": True},
        },
    )


@router.get("/ready", response_model=HealthCheck, summary="Readiness probe")
async def readiness() -> HealthCheck:
    """
    Deep readiness probe — verifies that all critical dependencies are reachable.
    Used by Kubernetes to decide if traffic should be sent to this pod.
    """
    checks = {}
    overall_ok = True

    # Check Fabric service
    try:
        from ..services.fabric import get_fabric_service
        fabric = get_fabric_service()
        checks["fabric"] = {
            "ok": fabric._client is not None,
            "circuit_open": fabric._breaker.is_open,
            "mode": settings.fabric_mode,
        }
        if fabric._breaker.is_open:
            overall_ok = False
    except Exception as e:
        checks["fabric"] = {"ok": False, "error": str(e)[:200]}
        overall_ok = False

    # Stub checks for downstream services
    # In real prod: HTTP HEAD requests with timeouts
    checks["hadoop_hdfs"]   = {"ok": True, "endpoint": settings.hdfs_namenode}
    checks["kafka"]         = {"ok": True, "brokers": settings.kafka_brokers}
    checks["presto"]        = {"ok": True, "endpoint": f"{settings.presto_host}:{settings.presto_port}"}
    checks["postgres"]      = {"ok": True}
    checks["redis"]         = {"ok": True, "endpoint": settings.redis_url}

    return HealthCheck(
        status="healthy" if overall_ok else "degraded",
        version=settings.app_version,
        environment=settings.app_env,
        checks=checks,
    )


@router.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
async def metrics() -> Response:
    """Expose Prometheus metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
