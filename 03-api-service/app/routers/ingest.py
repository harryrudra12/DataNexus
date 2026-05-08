"""
DataNexus Era 3 — Ingest Router
Accepts data, classifies it, generates Data DNA, writes to fabric, logs to blockchain.
"""
import hashlib
import time
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException

from ..core.auth import CurrentUser, Permission, require_permission
from ..core.logging import get_logger
from ..core.config import get_settings
from ..models.schemas import (
    IngestRequest, IngestResponse,
    Classification, Jurisdiction,
)
from ..services.fabric import get_fabric_service, FabricService

router   = APIRouter(prefix="/api/v1", tags=["ingest"])
logger   = get_logger(__name__)
settings = get_settings()


@router.post("/ingest",
             response_model=IngestResponse,
             status_code=200,
             summary="Ingest data into the DataNexus fabric")
async def ingest_data(
    body:   IngestRequest,
    user:   CurrentUser = Depends(require_permission(Permission.INGEST_DATA)),
    fabric: FabricService = Depends(get_fabric_service),
) -> IngestResponse:
    """
    Production ingest pipeline:
    1. Validate the incoming payload (Pydantic)
    2. Compute SHA-256 content hash
    3. Run quality gate (refuse if sigma < 4.5)
    4. Generate dataset_id and Data DNA
    5. Log transformation to Hyperledger Fabric Lineage chaincode
    6. Return the full audit-ready response
    """
    start = time.time()
    raw_data = body.data.encode("utf-8")
    dataset_id = f"ds-{uuid.uuid4().hex[:12]}"

    log = logger.bind(
        dataset_id   = dataset_id,
        dataset_name = body.dataset_name,
        user_id      = user.user_id,
        tenant_id    = user.tenant_id,
    )

    # ─── Quality gate ─────────────────────────────────────────
    sigma = _estimate_sigma(raw_data, body.data_format)
    if sigma < settings.quality_quarantine_threshold:
        log.warning("ingest_quarantined", sigma=sigma)
        raise HTTPException(
            status_code=422,
            detail=f"Data quarantined: sigma={sigma:.2f} below threshold "
                   f"{settings.quality_quarantine_threshold}σ",
        )

    # ─── Compute hashes ───────────────────────────────────────
    content_hash = hashlib.sha256(raw_data).hexdigest()
    log = log.bind(content_hash=content_hash[:16] + "...", sigma=sigma)

    # ─── Log to Hyperledger Fabric ────────────────────────────
    region = body.allowed_regions[0] if body.allowed_regions else "IN"
    try:
        fabric_result = await fabric.log_transformation(
            job_id              = f"ingest-{dataset_id}",
            input_dataset_ids   = [],
            input_hashes        = [],
            output_dataset_id   = dataset_id,
            output_data         = raw_data,
            transformation_type = "INGEST",
            pipeline_id         = body.pipeline_id or "manual-ingest",
            sigma_level         = sigma,
            classification      = body.classification.value,
            jurisdictions       = [j.value for j in body.jurisdictions],
            region              = region,
            ipfs_cid            = "",
        )
    except Exception as e:
        log.error("fabric_write_failed", error=str(e))
        raise HTTPException(503, detail="Blockchain ledger temporarily unavailable")

    # ─── Log to quality chaincode in parallel ─────────────────
    try:
        await fabric.log_quality(
            pipeline_id       = body.pipeline_id or "manual-ingest",
            dataset_id        = dataset_id,
            run_id            = f"run-{uuid.uuid4().hex[:8]}",
            sigma_level       = sigma,
            records_processed = len(raw_data.split(b"\n")) if body.data_format == "csv" else 1,
            records_failed    = 0,
            node_id           = body.node_id,
            region            = region,
        )
    except Exception:
        # Quality logging failure shouldn't block ingest
        log.warning("quality_log_failed")

    elapsed_ms = int((time.time() - start) * 1000)
    log.info("ingest_complete",
             tx_id=fabric_result["tx_id"][:16] + "...",
             elapsed_ms=elapsed_ms)

    return IngestResponse(
        status        = "ingested",
        dataset_id    = dataset_id,
        content_hash  = content_hash,
        ipfs_cid      = fabric_result.get("ipfs_cid", ""),
        genome_hash   = fabric_result["genome_hash"],
        fabric_tx_id  = fabric_result["tx_id"],
        sigma         = sigma,
        region        = region,
        fabric_nodes  = 2,
        timestamp     = datetime.utcnow(),
    )


def _estimate_sigma(data: bytes, fmt: str) -> float:
    """
    Lightweight quality estimation. Real implementation runs Great Expectations.
    Returns a sigma score between 1.0 and 6.0.
    """
    if not data:
        return 1.0

    score = 6.0
    # Penalize empty fields (CSV)
    if fmt == "csv":
        empty_ratio = data.count(b",,") / max(len(data), 1)
        score -= empty_ratio * 20

    # Penalize very short or very long records
    line_count = data.count(b"\n") + 1
    avg_line_len = len(data) / line_count
    if avg_line_len < 5:   score -= 1.5  # suspiciously short
    if avg_line_len > 5000: score -= 1.0  # suspiciously long

    # Penalize binary garbage in text formats
    if fmt in ("csv", "json"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            score -= 2.5

    return max(1.0, min(6.0, score))
