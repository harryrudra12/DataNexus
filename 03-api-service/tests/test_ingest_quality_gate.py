from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.core.auth import CurrentUser
from app.models.schemas import IngestRequest
from app.routers import ingest


def _request() -> IngestRequest:
    return IngestRequest(
        dataset_name="quality_boundary",
        data="column_a,column_b\nvalue_a,value_b",
        data_format="csv",
        classification="INTERNAL",
        jurisdictions=["DPDP_2023"],
        allowed_regions=["IN"],
        purpose="quality validation",
    )


def _user() -> CurrentUser:
    return CurrentUser(
        user_id="quality-tester",
        tenant_id="tenant-test",
        roles=[],
        permissions=set(),
    )


def _fabric() -> AsyncMock:
    fabric = AsyncMock()
    fabric.log_transformation.return_value = {
        "tx_id": "tx-quality-boundary",
        "genome_hash": "genome-quality-boundary",
        "ipfs_cid": "",
    }
    return fabric


def test_estimator_penalizes_non_utf8_only_for_text_formats():
    binary_payload = b"\xff" * 100

    assert ingest._estimate_sigma(binary_payload, "csv") == 3.5
    assert ingest._estimate_sigma(binary_payload, "json") == 3.5
    assert ingest._estimate_sigma(binary_payload, "avro") == 6.0


@pytest.mark.asyncio
async def test_ingest_below_quality_threshold_skips_all_ledger_writes(monkeypatch):
    fabric = _fabric()
    monkeypatch.setattr(ingest.settings, "quality_quarantine_threshold", 4.0)
    monkeypatch.setattr(ingest, "_estimate_sigma", lambda _data, _format: 3.99)

    with pytest.raises(HTTPException) as exc_info:
        await ingest.ingest_data(_request(), _user(), fabric)

    assert exc_info.value.status_code == 422
    assert "sigma=3.99 below threshold 4.0" in exc_info.value.detail
    fabric.log_transformation.assert_not_awaited()
    fabric.log_quality.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingest_at_quality_threshold_records_lineage_and_quality(monkeypatch):
    fabric = _fabric()
    monkeypatch.setattr(ingest.settings, "quality_quarantine_threshold", 4.0)
    monkeypatch.setattr(ingest, "_estimate_sigma", lambda _data, _format: 4.0)

    response = await ingest.ingest_data(_request(), _user(), fabric)

    assert response.status == "ingested"
    assert response.sigma == 4.0
    transformation = fabric.log_transformation.await_args.kwargs
    assert transformation["output_data"] == _request().data.encode("utf-8")
    assert transformation["sigma_level"] == 4.0
    quality = fabric.log_quality.await_args.kwargs
    assert quality["dataset_id"] == response.dataset_id
    assert quality["sigma_level"] == 4.0
