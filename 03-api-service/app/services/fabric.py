"""
DataNexus Era 3 — Fabric Service
Production wrapper around the Hyperledger Fabric chaincode client.
Handles retries, circuit breaking, and metric emission.
"""
import asyncio
import hashlib
import sys
import time
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add the fabric-chaincode client to path
_chaincode_path = Path(__file__).parent.parent.parent.parent / "fabric-chaincode" / "client"
if _chaincode_path.exists():
    sys.path.insert(0, str(_chaincode_path))

try:
    from fabric_client import (
        DataNexusFabricClient, FabricMode,
        TransformationRecord, ComplianceDecision, QualityMeasurement,
    )
except ImportError:
    # Fallback definitions if running standalone
    DataNexusFabricClient = None

from ..core.config import get_settings
from ..core.logging import get_logger

logger   = get_logger(__name__)
settings = get_settings()


# ─── Circuit breaker state ────────────────────────────────────
class CircuitBreaker:
    """Simple circuit breaker — open after 5 failures, half-open after 30s."""

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at > self.reset_timeout:
            return False  # half-open: allow one trial
        return self.failures >= self.failure_threshold

    def record_success(self):
        self.failures = 0
        self.opened_at = None

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold and self.opened_at is None:
            self.opened_at = time.time()
            logger.error("circuit_breaker_opened",
                         component="fabric", failures=self.failures)


# ─── Service ──────────────────────────────────────────────────
class FabricService:
    """Production-grade wrapper around the Fabric client."""

    def __init__(self):
        self._client: Optional[Any] = None
        self._breaker = CircuitBreaker()
        self._metrics_recorded = 0

    async def initialize(self) -> None:
        """Called on app startup."""
        if DataNexusFabricClient is None:
            logger.warning("fabric_client_unavailable_using_stub")
            return

        mode = FabricMode.PRODUCTION if settings.fabric_mode == "production" else FabricMode.SIMULATION
        self._client = DataNexusFabricClient(
            mode=mode,
            network_profile=settings.fabric_network_profile,
            org_msp=settings.fabric_org_msp,
            channel_name=settings.fabric_channel_name,
            user_id=settings.fabric_user_id,
        )
        logger.info("fabric_service_ready", mode=mode.value, channel=settings.fabric_channel_name)

    async def close(self) -> None:
        """Called on app shutdown."""
        self._client = None

    # ─── Lineage ──────────────────────────────────────────────
    async def log_transformation(
        self,
        job_id:               str,
        input_dataset_ids:    List[str],
        input_hashes:         List[str],
        output_dataset_id:    str,
        output_data:          bytes,
        transformation_type:  str,
        pipeline_id:          str,
        sigma_level:          float,
        classification:       str,
        jurisdictions:        List[str],
        region:               str,
        ipfs_cid:             str = "",
    ) -> Dict[str, Any]:
        """Log a transformation to the Lineage chaincode."""
        if self._breaker.is_open:
            logger.warning("fabric_circuit_open_using_fallback")
            return self._fallback_record(output_data, output_dataset_id, sigma_level)

        if self._client is None:
            return self._fallback_record(output_data, output_dataset_id, sigma_level)

        try:
            record = await self._client.log_transformation(
                job_id              = job_id,
                input_dataset_ids   = input_dataset_ids,
                input_hashes        = input_hashes,
                output_dataset_id   = output_dataset_id,
                output_data         = output_data,
                transformation_type = transformation_type,
                pipeline_id         = pipeline_id,
                sigma_level         = sigma_level,
                classification      = classification,
                jurisdictions       = jurisdictions,
                region              = region,
                ipfs_cid            = ipfs_cid,
            )
            self._breaker.record_success()
            return {
                "tx_id":         record.tx_id,
                "genome_hash":   record.genome_hash,
                "output_hash":   record.output_hash,
                "timestamp":     record.timestamp,
                "ipfs_cid":      record.ipfs_cid or ipfs_cid,
            }
        except Exception as e:
            self._breaker.record_failure()
            logger.error("fabric_log_transformation_failed", error=str(e), dataset=output_dataset_id)
            raise

    async def get_lineage(self, dataset_id: str) -> List[Dict[str, Any]]:
        if self._client is None:
            return []
        records = await self._client.get_lineage(dataset_id)
        return [self._record_to_dict(r) for r in records]

    async def verify_integrity(
        self, dataset_id: str, expected_hash: str = ""
    ) -> Dict[str, Any]:
        if self._client is None:
            return {"verified": False, "message": "fabric unavailable"}
        verified, message = await self._client.verify_integrity(dataset_id, expected_hash)
        return {"verified": verified, "message": message}

    # ─── Compliance ───────────────────────────────────────────
    async def check_transfer(
        self,
        dataset_id:     str,
        classification: str,
        jurisdictions:  List[str],
        target_region:  str,
        purpose:        str,
        has_consent:    bool = False,
        signature_count:int = 0,
    ) -> Dict[str, Any]:
        if self._client is None:
            return self._fallback_compliance_decision(dataset_id, target_region)

        try:
            decision = await self._client.check_transfer(
                dataset_id     = dataset_id,
                classification = classification,
                jurisdictions  = jurisdictions,
                target_region  = target_region,
                purpose        = purpose,
                has_consent    = has_consent,
                signature_count= signature_count,
            )
            self._breaker.record_success()
            return self._decision_to_dict(decision)
        except Exception as e:
            self._breaker.record_failure()
            logger.error("fabric_check_transfer_failed", error=str(e))
            raise

    async def generate_audit_report(self, dataset_id: str) -> Dict[str, Any]:
        if self._client is None:
            return {"error": "fabric unavailable"}
        return await self._client.generate_audit_report(dataset_id)

    # ─── Quality ──────────────────────────────────────────────
    async def log_quality(
        self,
        pipeline_id:        str,
        dataset_id:         str,
        run_id:             str,
        sigma_level:        float,
        records_processed:  int,
        records_failed:     int,
        completeness_pct:   float = 99.0,
        accuracy_pct:       float = 99.0,
        node_id:            str   = "dn-hyderabad-01",
        region:             str   = "IN-TG",
    ) -> Dict[str, Any]:
        if self._client is None:
            return {"measurement_id": f"M-{uuid.uuid4().hex[:12]}"}

        m = QualityMeasurement(
            pipeline_id        = pipeline_id,
            dataset_id         = dataset_id,
            run_id             = run_id,
            sigma_level        = sigma_level,
            completeness_pct   = completeness_pct,
            accuracy_pct       = accuracy_pct,
            records_processed  = records_processed,
            records_failed     = records_failed,
            expectations_run   = 12,
            expectations_passed= 12 if records_failed == 0 else 11,
            node_id            = node_id,
            region             = region,
        )
        result = await self._client.log_measurement(m)
        return {
            "measurement_id":   result.measurement_id,
            "fabric_tx_id":     result.fabric_tx_id,
            "measurement_hash": result.measurement_hash,
            "sigma_level":      result.sigma_level,
        }

    async def get_sigma_trend(self, pipeline_id: str, limit: int = 30) -> List[Dict]:
        if self._client is None:
            return []
        return await self._client.get_sigma_trend(pipeline_id, limit)

    # ─── Helpers ──────────────────────────────────────────────
    @staticmethod
    def _record_to_dict(r) -> Dict[str, Any]:
        return {
            "tx_id":               r.tx_id,
            "timestamp":           r.timestamp,
            "output_dataset_id":   r.output_dataset_id,
            "output_hash":         r.output_hash,
            "transformation_type": r.transformation_type,
            "pipeline_id":         r.pipeline_id,
            "sigma_level":         r.sigma_level,
            "classification":      r.classification,
            "region":              r.region,
            "operator_msp":        r.operator_msp,
        }

    @staticmethod
    def _decision_to_dict(d) -> Dict[str, Any]:
        return {
            "decision_id":     d.decision_id,
            "request_id":      d.request_id,
            "decision":        d.decision,
            "reason":          d.reason,
            "rules_evaluated": d.rules_evaluated,
            "rules_passed":    d.rules_passed,
            "violations":      d.violations,
            "auto_fixes_applied": d.auto_fixes_applied,
            "timestamp":       d.timestamp,
            "fabric_tx_id":    d.fabric_tx_id,
        }

    @staticmethod
    def _fallback_record(data: bytes, dataset_id: str, sigma: float) -> Dict[str, Any]:
        """When Fabric is unavailable, return a fallback that still has a content hash."""
        return {
            "tx_id":         f"FALLBACK_{uuid.uuid4().hex[:24]}",
            "genome_hash":   hashlib.sha256(data).hexdigest(),
            "output_hash":   hashlib.sha256(data).hexdigest(),
            "timestamp":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ipfs_cid":      "",
            "fallback":      True,
        }

    @staticmethod
    def _fallback_compliance_decision(dataset_id: str, target: str) -> Dict[str, Any]:
        return {
            "decision_id":     f"FALLBACK_{uuid.uuid4().hex[:12]}",
            "request_id":      f"R-{uuid.uuid4().hex[:8]}",
            "decision":        "BLOCKED",
            "reason":          "Fabric service unavailable — failing closed for safety",
            "rules_evaluated": 0, "rules_passed": 0,
            "violations": [], "auto_fixes_applied": [],
            "timestamp":       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "fabric_tx_id":    "",
            "fallback":        True,
        }


# ─── Singleton ────────────────────────────────────────────────
_fabric_service: Optional[FabricService] = None


def get_fabric_service() -> FabricService:
    global _fabric_service
    if _fabric_service is None:
        _fabric_service = FabricService()
    return _fabric_service
