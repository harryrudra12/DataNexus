"""
DataNexus Era 3 — Lineage, Datasets & Fabric routers
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException

from ..core.auth import CurrentUser, Permission, require_permission
from ..core.logging import get_logger
from ..models.schemas import (
    LineageResponse, LineageRecord,
    DatasetResponse, FabricStatus, FabricNode,
    Classification, Jurisdiction,
)
from ..services.fabric import get_fabric_service, FabricService

router = APIRouter(prefix="/api/v1", tags=["lineage"])
logger = get_logger(__name__)


# ─── Lineage ──────────────────────────────────────────────────
@router.get("/lineage/{dataset_id}",
            response_model=LineageResponse,
            summary="Full blockchain-verified lineage chain")
async def get_lineage(
    dataset_id: str,
    user:       CurrentUser = Depends(require_permission(Permission.VIEW_LINEAGE)),
    fabric:     FabricService = Depends(get_fabric_service),
) -> LineageResponse:
    """Returns every transformation that produced this dataset, with integrity check."""
    log = logger.bind(dataset_id=dataset_id, user_id=user.user_id)

    raw_records   = await fabric.get_lineage(dataset_id)
    integrity     = await fabric.verify_integrity(dataset_id)

    records = [
        LineageRecord(
            tx_id               = r["tx_id"],
            timestamp           = r["timestamp"],
            output_dataset_id   = r["output_dataset_id"],
            output_hash         = r["output_hash"],
            transformation_type = r["transformation_type"],
            pipeline_id         = r["pipeline_id"],
            sigma_level         = r["sigma_level"],
            classification      = r["classification"],
            region              = r["region"],
            operator_msp        = r["operator_msp"],
        )
        for r in raw_records
    ]
    log.info("lineage_retrieved", count=len(records), integrity=integrity["verified"])

    return LineageResponse(
        dataset_id = dataset_id,
        records    = records,
        total      = len(records),
        integrity  = integrity["verified"],
    )


# ─── Datasets ─────────────────────────────────────────────────
@router.get("/dataset/{dataset_id}",
            response_model=DatasetResponse,
            summary="Get dataset metadata with DNA integrity check")
async def get_dataset(
    dataset_id: str,
    user:       CurrentUser = Depends(require_permission(Permission.READ_DATASET)),
    fabric:     FabricService = Depends(get_fabric_service),
) -> DatasetResponse:
    log = logger.bind(dataset_id=dataset_id, user_id=user.user_id)

    records = await fabric.get_lineage(dataset_id)
    if not records:
        log.warning("dataset_not_found")
        raise HTTPException(404, detail=f"Dataset {dataset_id} not found")

    # Latest record is the canonical metadata
    latest = records[0]
    integrity = await fabric.verify_integrity(dataset_id)

    return DatasetResponse(
        dataset_id     = dataset_id,
        dataset_name   = latest["output_dataset_id"],
        classification = Classification(latest["classification"]) if latest["classification"] else Classification.CONFIDENTIAL,
        jurisdictions  = [],
        sigma          = latest["sigma_level"],
        genome_hash    = latest["output_hash"],
        integrity_ok   = integrity["verified"],
        ipfs_cid       = "",
        fabric_tx      = latest["tx_id"],
        creator_id     = latest["operator_msp"],
        created_at     = latest["timestamp"],
        parent_ids     = [],
    )


# ─── Fabric status ────────────────────────────────────────────
fabric_router = APIRouter(prefix="/api/v1/fabric", tags=["fabric"])


@fabric_router.get("/status",
                   response_model=FabricStatus,
                   summary="Zero gravity fabric status")
async def fabric_status(
    user:   CurrentUser = Depends(require_permission(Permission.VIEW_LINEAGE)),
    fabric: FabricService = Depends(get_fabric_service),
) -> FabricStatus:
    """Real-time view of all fabric nodes, datasets in flight, and avg sigma."""
    # In production: query a state-store of registered nodes
    demo_nodes = [
        FabricNode(node_id="dn-hyderabad-01", region="IN-TG",
                   node_type="core_cloud", online=True, items=1247, avg_sigma=5.9),
        FabricNode(node_id="dn-mumbai-01",    region="IN-MH",
                   node_type="core_cloud", online=True, items=892,  avg_sigma=5.4),
        FabricNode(node_id="dn-delhi-01",     region="IN-DL",
                   node_type="core_cloud", online=True, items=445,  avg_sigma=5.6),
        FabricNode(node_id="dn-hospital-hyd", region="IN-TG",
                   node_type="edge",       online=True, items=28,   avg_sigma=5.9),
        FabricNode(node_id="dn-factory-ap",   region="IN-AP",
                   node_type="edge_iot",   online=True, items=4502, avg_sigma=4.8),
        FabricNode(node_id="dn-eu-frankfurt", region="EU-DE",
                   node_type="core_cloud", online=True, items=312,  avg_sigma=5.7),
    ]
    avg_sigma = sum(n.avg_sigma for n in demo_nodes) / len(demo_nodes)
    total = sum(n.items for n in demo_nodes)
    online = sum(1 for n in demo_nodes if n.online)

    return FabricStatus(
        fabric_id        = "datanexus-prod-01",
        total_datasets   = total,
        total_nodes      = len(demo_nodes),
        online_nodes     = online,
        avg_sigma        = round(avg_sigma, 2),
        total_movements  = 1247,
        nodes            = demo_nodes,
    )
