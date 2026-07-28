import hashlib
from types import SimpleNamespace

import pytest

from app.services import fabric as fabric_module
from app.services.fabric import CircuitBreaker, FabricService


def test_circuit_breaker_opens_at_threshold_and_allows_timed_retry(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(fabric_module.time, "time", lambda: now[0])
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=30.0)

    breaker.record_failure()
    assert breaker.is_open is False

    breaker.record_failure()
    assert breaker.is_open is True

    now[0] = 130.0
    assert breaker.is_open is True

    now[0] = 130.001
    assert breaker.is_open is False

    breaker.record_success()
    assert breaker.failures == 0
    assert breaker.opened_at is None


@pytest.mark.asyncio
async def test_open_circuit_uses_fallback_then_recovers_live_client(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(fabric_module.time, "time", lambda: now[0])
    service = FabricService()
    service._breaker = CircuitBreaker(failure_threshold=1, reset_timeout=30.0)

    class LiveClient:
        def __init__(self):
            self.calls = 0

        async def log_transformation(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(
                tx_id="fabric-tx-recovered",
                genome_hash="fabric-genome-hash",
                output_hash="fabric-output-hash",
                timestamp="2026-07-28T10:00:00Z",
                ipfs_cid="",
            )

    live_client = LiveClient()
    service._client = live_client
    service._breaker.record_failure()
    data = b"patient_id,age\nP001,45"
    call = {
        "job_id": "ingest-ds-circuit-test",
        "input_dataset_ids": [],
        "input_hashes": [],
        "output_dataset_id": "ds-circuit-test",
        "output_data": data,
        "transformation_type": "INGEST",
        "pipeline_id": "manual-ingest",
        "sigma_level": 5.5,
        "classification": "HEALTH",
        "jurisdictions": ["DPDP_2023"],
        "region": "IN-TG",
    }

    fallback = await service.log_transformation(**call)

    assert fallback["fallback"] is True
    assert fallback["output_hash"] == hashlib.sha256(data).hexdigest()
    assert live_client.calls == 0
    assert service._fallback_lineage["ds-circuit-test"][0]["output_hash"] == fallback["output_hash"]

    now[0] = 130.001
    recovered = await service.log_transformation(**call)

    assert recovered["tx_id"] == "fabric-tx-recovered"
    assert "fallback" not in recovered
    assert live_client.calls == 1
    assert service._breaker.failures == 0
    assert service._breaker.opened_at is None
