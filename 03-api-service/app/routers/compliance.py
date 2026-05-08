"""
DataNexus Era 3 — Compliance Router
Border checks, compliance reports, blockchain-verified audit trail.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException

from ..core.auth import CurrentUser, Permission, require_permission
from ..core.logging import get_logger
from ..models.schemas import (
    BorderCheckRequest, BorderCheckResponse,
    ComplianceReport, ViolationDetail,
)
from ..services.fabric import get_fabric_service, FabricService

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])
logger = get_logger(__name__)


@router.post("/border",
             response_model=BorderCheckResponse,
             summary="Check if data transfer is permitted (DPDP/GDPR/HIPAA)")
async def border_check(
    body:   BorderCheckRequest,
    user:   CurrentUser = Depends(require_permission(Permission.APPROVE_TRANSFER)),
    fabric: FabricService = Depends(get_fabric_service),
) -> BorderCheckResponse:
    """
    Autonomous compliance check. Returns ALLOWED, BLOCKED, or ALLOWED_WITH_FIX.
    Every decision is logged permanently to Hyperledger Fabric.
    """
    log = logger.bind(
        dataset_id    = body.dataset_id,
        target        = body.target_country,
        purpose       = body.purpose,
        user_id       = user.user_id,
    )

    try:
        result = await fabric.check_transfer(
            dataset_id      = body.dataset_id,
            classification  = body.classification.value,
            jurisdictions   = [j.value for j in body.jurisdictions],
            target_region   = body.target_country,
            purpose         = body.purpose,
            has_consent     = body.has_consent,
            signature_count = body.signature_count,
        )
    except Exception as e:
        log.error("border_check_failed", error=str(e))
        raise HTTPException(503, detail="Compliance engine temporarily unavailable")

    log.info("border_check_complete",
             decision=result["decision"], rules_passed=result["rules_passed"])

    # Map violations to typed model
    violations = [
        ViolationDetail(
            rule_id     = v.get("ruleId", ""),
            law         = v.get("law", ""),
            law_section = v.get("lawSection", ""),
            description = v.get("description", ""),
            penalty     = v.get("penalty", ""),
            auto_fixed  = v.get("autoFixed", False),
        )
        for v in result.get("violations", [])
    ]

    return BorderCheckResponse(
        decision_id        = result["decision_id"],
        dataset_id         = body.dataset_id,
        target             = body.target_country,
        decision           = result["decision"],
        reason             = result["reason"],
        rules_evaluated    = result["rules_evaluated"],
        rules_passed       = result["rules_passed"],
        violations         = violations,
        auto_fixes_applied = result.get("auto_fixes_applied", []),
        fabric_tx_id       = result.get("fabric_tx_id", ""),
        timestamp          = datetime.utcnow(),
    )


@router.get("/report/{dataset_id}",
            summary="Generate 60-second blockchain-verified compliance report")
async def compliance_report(
    dataset_id: str,
    user:       CurrentUser = Depends(require_permission(Permission.GENERATE_REPORT)),
    fabric:     FabricService = Depends(get_fabric_service),
) -> dict:
    """
    Court-admissible compliance audit report.
    Includes blockchain proof that any third party can independently verify.
    """
    log = logger.bind(dataset_id=dataset_id, user_id=user.user_id)
    try:
        report = await fabric.generate_audit_report(dataset_id)
        log.info("compliance_report_generated",
                 lineage_records=report.get("lineage_records", 0))
        return report
    except Exception as e:
        log.error("compliance_report_failed", error=str(e))
        raise HTTPException(500, detail="Failed to generate compliance report")
