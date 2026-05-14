"""
DataNexus Era 3 — Pipelines Router
List all pipelines, get individual pipeline status, sigma trend over time.
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from ..core.auth import CurrentUser, Permission, require_permission
from ..core.logging import get_logger
from ..models.schemas import PipelineStatus, SigmaTrendPoint
from ..services.fabric import get_fabric_service, FabricService

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])
logger = get_logger(__name__)


# Production: this comes from PostgreSQL pipelines table.
# For the demo, we ship realistic seed data that matches the dashboard fallback.
_DEMO_PIPELINES = [
    {
        "pipeline_id":   "patient_records_apollo",
        "status":        "healthy",
        "current_sigma": 5.9,
        "avg_sigma_24h": 5.85,
        "last_run":      "2025-05-07T08:30:00Z",
        "runs_today":    12,
        "heal_rate":     88.0,
        "sla_target":    5.5,
        "sla_met":       True,
        "region":        "IN-TG",
        "owner":         "apollo_hospital_hyd",
        "fabric_tx":     "TX_91954854b09cbc6",
    },
    {
        "pipeline_id":   "sales_transactions_q4",
        "status":        "healthy",
        "current_sigma": 5.4,
        "avg_sigma_24h": 5.42,
        "last_run":      "2025-05-07T08:25:00Z",
        "runs_today":    8,
        "heal_rate":     92.0,
        "sla_target":    5.0,
        "sla_met":       True,
        "region":        "IN-MH",
        "owner":         "datanexus_internal",
        "fabric_tx":     "TX_a3c8d51fb26",
    },
    {
        "pipeline_id":   "iot_factory_sensors",
        "status":        "warning",
        "current_sigma": 4.8,
        "avg_sigma_24h": 4.72,
        "last_run":      "2025-05-07T08:32:00Z",
        "runs_today":    288,
        "heal_rate":     78.0,
        "sla_target":    5.0,
        "sla_met":       False,
        "region":        "IN-AP",
        "owner":         "factory_op_ap",
        "fabric_tx":     "TX_e7f2db89c14",
    },
    {
        "pipeline_id":   "eu_customer_profile",
        "status":        "healthy",
        "current_sigma": 5.7,
        "avg_sigma_24h": 5.68,
        "last_run":      "2025-05-07T08:15:00Z",
        "runs_today":    4,
        "heal_rate":     95.0,
        "sla_target":    5.5,
        "sla_met":       True,
        "region":        "EU-DE",
        "owner":         "datanexus_eu",
        "fabric_tx":     "TX_b6c4d92ef03",
    },
]


@router.get("",
            summary="List all pipelines for the current tenant")
async def list_pipelines(
    user:      CurrentUser = Depends(require_permission(Permission.MANAGE_PIPELINE)),
    status:    Optional[str] = Query(None, description="Filter by status: healthy/warning/critical"),
    region:    Optional[str] = Query(None, description="Filter by region (IN-TG, EU-DE, etc.)"),
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict:
    """Returns paginated list of pipelines with current sigma scores."""
    log = logger.bind(user_id=user.user_id, tenant_id=user.tenant_id)

    # Filter
    items = _DEMO_PIPELINES
    if status:
        items = [p for p in items if p["status"] == status]
    if region:
        items = [p for p in items if p["region"] == region]

    # Paginate
    start = (page - 1) * page_size
    end   = start + page_size
    page_items = items[start:end]

    log.info("pipelines_listed", count=len(page_items), total=len(items))

    return {
        "items":     page_items,
        "total":     len(items),
        "page":      page,
        "page_size": page_size,
        "has_next":  end < len(items),
    }


@router.get("/{pipeline_id}",
            summary="Get a specific pipeline's full status")
async def get_pipeline(
    pipeline_id: str,
    user:        CurrentUser = Depends(require_permission(Permission.MANAGE_PIPELINE)),
) -> dict:
    log = logger.bind(pipeline_id=pipeline_id, user_id=user.user_id)
    pipeline = next((p for p in _DEMO_PIPELINES if p["pipeline_id"] == pipeline_id), None)
    if not pipeline:
        log.warning("pipeline_not_found")
        raise HTTPException(404, detail=f"Pipeline {pipeline_id} not found")
    return pipeline


@router.get("/{pipeline_id}/sigma-trend",
            summary="Sigma quality score over time for a pipeline")
async def sigma_trend(
    pipeline_id: str,
    hours:       int = Query(24, ge=1, le=720, description="Lookback window in hours"),
    user:        CurrentUser = Depends(require_permission(Permission.MANAGE_PIPELINE)),
    fabric:      FabricService = Depends(get_fabric_service),
) -> dict:
    """Returns sigma measurements over the requested time window."""
    log = logger.bind(pipeline_id=pipeline_id, user_id=user.user_id)

    # Try to get real data from Fabric
    try:
        trend = await fabric.get_sigma_trend(pipeline_id, limit=hours * 4)
        if trend:
            log.info("sigma_trend_from_fabric", points=len(trend))
            return {
                "pipeline_id": pipeline_id,
                "hours":       hours,
                "points":      trend,
                "source":      "hyperledger_fabric",
            }
    except Exception as e:
        log.warning("sigma_trend_fabric_failed", error=str(e))

    # Fallback: generate realistic demo trend
    pipeline = next((p for p in _DEMO_PIPELINES if p["pipeline_id"] == pipeline_id), None)
    base_sigma = pipeline["current_sigma"] if pipeline else 5.5

    points = []
    now = datetime.utcnow()
    for h in range(hours, 0, -1):
        t = now - timedelta(hours=h)
        # Realistic variance within ±0.4σ around base
        import math
        wave = math.sin(h / 6.0) * 0.2
        noise = (hash(f"{pipeline_id}{h}") % 100 - 50) / 250.0
        sigma = max(3.0, min(6.0, base_sigma + wave + noise))
        points.append({
            "timestamp":   t.isoformat() + "Z",
            "sigma_level": round(sigma, 2),
            "run_id":      f"run-{t.strftime('%Y%m%d%H')}",
        })

    log.info("sigma_trend_demo", points=len(points))
    return {
        "pipeline_id": pipeline_id,
        "hours":       hours,
        "points":      points,
        "source":      "demo",
    }
