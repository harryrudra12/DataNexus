"""
DataNexus Era 3 — Audit Router
Recent audit chain from Hyperledger Fabric with cursor pagination.
Used by the Audit tab on the dashboard.
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query

from ..core.auth import CurrentUser, Permission, require_permission
from ..core.logging import get_logger
from ..services.fabric import get_fabric_service, FabricService

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
logger = get_logger(__name__)


# Production: stream from Fabric event listener → Kafka → ClickHouse
# Demo: synthesize realistic recent events
_DEMO_AUDIT_EVENTS = [
    {"ts": "2025-05-07T08:32:08Z", "tx": "TX_91954854b09cbc6d9f4e",
     "action": "TRANSFORM", "dataset": "patient_records_apollo",
     "result": "OK", "sigma": 5.9, "user": "spark-job"},
    {"ts": "2025-05-07T08:31:55Z", "tx": "TX_a3c8d51fb26ef8a9c4b1",
     "action": "INGEST",    "dataset": "sales_transactions_q4",
     "result": "OK", "sigma": 5.4, "user": "kafka-connect"},
    {"ts": "2025-05-07T08:31:42Z", "tx": "TX_e7f2db89c14a07b5d8e2",
     "action": "BORDER",    "dataset": "iot_factory_sensors",
     "result": "BLOCKED", "reason": "DPDP-001",
     "target": "US", "user": "analytics-team"},
    {"ts": "2025-05-07T08:31:18Z", "tx": "TX_b6c4d92ef036a8d1c2f4",
     "action": "QUERY",     "dataset": "eu_customer_profile",
     "result": "OK", "user": "auditor_eu"},
    {"ts": "2025-05-07T08:30:55Z", "tx": "TX_d8a1b7c4e92ad3f5b691",
     "action": "AUTO-HEAL", "dataset": "iot_factory_sensors",
     "result": "FIXED", "user": "ai-os",
     "details": "Schema evolution applied: new column 'humidity'"},
    {"ts": "2025-05-07T08:30:31Z", "tx": "TX_f2e9c8a3b71d2c4e8f0a",
     "action": "TRANSFORM", "dataset": "patient_records_apollo",
     "result": "OK", "sigma": 5.9, "user": "spark-job"},
    {"ts": "2025-05-07T08:30:08Z", "tx": "TX_c5b8d4f9a23e7f1b6d0c",
     "action": "INGEST",    "dataset": "iot_factory_sensors",
     "result": "OK", "sigma": 4.8, "user": "edge-collector"},
    {"ts": "2025-05-07T08:29:45Z", "tx": "TX_a92b3c4d5e6f7a8b9c0d",
     "action": "BORDER",    "dataset": "patient_records_apollo",
     "result": "ALLOWED", "target": "IN-MH", "user": "apollo_admin",
     "details": "DPDP allowed: same country, multi-sig present"},
    {"ts": "2025-05-07T08:29:22Z", "tx": "TX_1f2e3d4c5b6a7e8f9a0b",
     "action": "QUERY",     "dataset": "sales_transactions_q4",
     "result": "OK", "user": "analyst_mumbai"},
    {"ts": "2025-05-07T08:29:01Z", "tx": "TX_4e5f6a7b8c9d0e1f2a3b",
     "action": "TRANSFORM", "dataset": "eu_customer_profile",
     "result": "OK", "sigma": 5.7, "user": "spark-job"},
]


@router.get("",
            summary="Recent audit events from Hyperledger Fabric")
async def list_audit_events(
    user:      CurrentUser = Depends(require_permission(Permission.VIEW_AUDIT)),
    limit:     int  = Query(50, ge=1, le=500),
    cursor:    Optional[str] = Query(None, description="Cursor from previous response"),
    action:    Optional[str] = Query(None, description="Filter: TRANSFORM, INGEST, BORDER, QUERY, AUTO-HEAL"),
    result:    Optional[str] = Query(None, description="Filter: OK, BLOCKED, FIXED, ALLOWED"),
    dataset:   Optional[str] = Query(None, description="Filter by dataset name"),
) -> dict:
    """Returns paginated audit events with optional filtering."""
    log = logger.bind(user_id=user.user_id, tenant_id=user.tenant_id)

    events = list(_DEMO_AUDIT_EVENTS)
    if action:
        events = [e for e in events if e["action"] == action.upper()]
    if result:
        events = [e for e in events if e["result"] == result.upper()]
    if dataset:
        events = [e for e in events if dataset.lower() in e["dataset"].lower()]

    # Cursor: simple offset-based for demo
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    page = events[offset:offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(events) else None

    log.info("audit_listed", count=len(page), total=len(events))

    return {
        "items":          page,
        "total":          len(events),
        "next_cursor":    next_cursor,
        "filters_applied": {
            "action":  action,
            "result":  result,
            "dataset": dataset,
        },
    }


@router.get("/dataset/{dataset_id}",
            summary="Full audit chain for a specific dataset")
async def dataset_audit(
    dataset_id: str,
    user:       CurrentUser = Depends(require_permission(Permission.VIEW_AUDIT)),
    fabric:     FabricService = Depends(get_fabric_service),
) -> dict:
    """All audit events touching this dataset, in chronological order."""
    log = logger.bind(dataset_id=dataset_id, user_id=user.user_id)

    # Try real fabric first
    try:
        lineage = await fabric.get_lineage(dataset_id)
        if lineage:
            log.info("audit_from_fabric", count=len(lineage))
            return {
                "dataset_id": dataset_id,
                "events":     lineage,
                "source":     "hyperledger_fabric",
                "verified":   True,
            }
    except Exception as e:
        log.warning("audit_fabric_failed", error=str(e))

    # Fallback to demo
    events = [e for e in _DEMO_AUDIT_EVENTS if dataset_id.lower() in e["dataset"].lower()]
    return {
        "dataset_id": dataset_id,
        "events":     events,
        "source":     "demo",
        "verified":   False,
    }


@router.get("/stats/24h",
            summary="Aggregated audit statistics for the last 24 hours")
async def audit_stats(
    user: CurrentUser = Depends(require_permission(Permission.VIEW_AUDIT)),
) -> dict:
    """Counts by action type and result for dashboard widgets."""
    by_action: dict[str, int] = {}
    by_result: dict[str, int] = {}

    for e in _DEMO_AUDIT_EVENTS:
        by_action[e["action"]] = by_action.get(e["action"], 0) + 1
        by_result[e["result"]] = by_result.get(e["result"], 0) + 1

    return {
        "window_hours": 24,
        "total_events": len(_DEMO_AUDIT_EVENTS),
        "by_action":    by_action,
        "by_result":    by_result,
        "blocked_pct":  round(by_result.get("BLOCKED", 0) / len(_DEMO_AUDIT_EVENTS) * 100, 1) if _DEMO_AUDIT_EVENTS else 0.0,
    }
