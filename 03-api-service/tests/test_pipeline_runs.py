"""Regression tests for synchronous pipeline execution and run history."""

from __future__ import annotations

import os
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ["REQUIRE_AUTH"] = "false"
os.environ["APP_ENV"] = "testing"
os.environ["FABRIC_MODE"] = "simulation"

from app.main import app  # noqa: E402
from app.routers import dashboard, runs  # noqa: E402


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client


@pytest.fixture
def pipeline() -> dict[str, Any]:
    return {
        "id": "pl-test",
        "name": "customer_events",
        "sigma": 5.6,
        "laws": ["DPDP"],
        "region": "IN-MH",
        "source": "kafka",
        "target": "presto_gold",
    }


class RecordingCursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = rows or []
        self.executions: list[tuple[str, Any]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        self.executions.append((statement, params))

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.recording_cursor = RecordingCursor(rows)
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.recording_cursor

    def commit(self):
        self.commits += 1


def patch_duplicate_handlers(monkeypatch, attribute: str, value) -> None:
    """Patch both currently registered copies of the pipeline-run handlers."""
    monkeypatch.setattr(dashboard, attribute, value)
    monkeypatch.setattr(runs, attribute, value)


@pytest.mark.asyncio
async def test_execute_real_persists_complete_run_and_audit(
    client, monkeypatch, pipeline
):
    connection = RecordingConnection()
    persisted_runs: list[dict[str, Any]] = []
    audit_events: list[dict[str, Any]] = []

    patch_duplicate_handlers(monkeypatch, "get_pipelines_from_db", lambda: [pipeline])
    patch_duplicate_handlers(monkeypatch, "ensure_db", lambda: True)
    patch_duplicate_handlers(monkeypatch, "get_conn", lambda: connection)
    patch_duplicate_handlers(
        monkeypatch,
        "insert_pipeline_run_record",
        lambda run_record: persisted_runs.append(run_record),
    )
    patch_duplicate_handlers(
        monkeypatch,
        "insert_audit_event",
        lambda _cursor, event: audit_events.append(event),
    )
    patch_duplicate_handlers(
        monkeypatch, "now_iso", lambda: "2026-07-17T10:00:00+00:00"
    )
    patch_duplicate_handlers(monkeypatch, "now_time", lambda: "10:00:00")

    response = await client.post(
        "/api/v1/dashboard/pipelines/pl-test/execute-real"
    )

    assert response.status_code == 200
    body = response.json()
    run = body["run"]
    assert body["status"] == "completed"
    assert run["run_id"].startswith("RUN_")
    assert run["fabric_tx"].startswith("TX_")
    assert run["pipeline_id"] == "pl-test"
    assert run["pipeline_name"] == "customer_events"
    assert run["duration_ms"] == 1200 + len("customer_events") * 37
    assert [log["step"] for log in run["logs"]] == [
        "queued",
        "source_connect",
        "quality_scan",
        "compliance_guard",
        "target_write",
        "audit_commit",
    ]
    assert all(log["status"] == "completed" for log in run["logs"])
    assert all(
        log["ts"] == "2026-07-17T10:00:00+00:00" for log in run["logs"]
    )
    assert "DPDP policy guard evaluated" in run["logs"][3]["message"]
    assert run["fabric_tx"] in run["logs"][-1]["message"]

    assert body["audit_event"] == {
        "ts": "10:00:00",
        "tx": run["fabric_tx"],
        "action": "PIPELINE_EXECUTION",
        "dataset": "customer_events",
        "result": "COMPLETED",
        "actor": "execution-engine",
        "law": "DPDP",
        "region": "IN-MH",
    }
    assert persisted_runs == [run]
    assert audit_events == [body["audit_event"]]
    assert connection.commits == 1
    update_statement, update_params = connection.recording_cursor.executions[0]
    assert "SET runs = runs + 1" in update_statement
    assert update_params == ("pl-test",)


@pytest.mark.asyncio
async def test_execute_real_unknown_pipeline_has_no_side_effects(
    client, monkeypatch
):
    patch_duplicate_handlers(monkeypatch, "get_pipelines_from_db", lambda: [])
    patch_duplicate_handlers(
        monkeypatch, "now_iso", lambda: "2026-07-17T10:00:00+00:00"
    )

    def unexpected_database_access():
        pytest.fail("unknown pipelines must not access persistence")

    patch_duplicate_handlers(monkeypatch, "ensure_db", unexpected_database_access)

    response = await client.post(
        "/api/v1/dashboard/pipelines/missing/execute-real"
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "not_found",
        "message": "Pipeline missing was not found",
        "timestamp": "2026-07-17T10:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_recent_pipeline_runs_maps_database_rows_and_honors_limit(
    client, monkeypatch
):
    logs = [{"step": "audit_commit", "status": "completed"}]
    connection = RecordingConnection(
        [
            {
                "run_id": "RUN_123",
                "pipeline_id": "pl-test",
                "pipeline_name": "customer_events",
                "status": "completed",
                "started_at": "2026-07-17 09:59:58+00:00",
                "completed_at": "2026-07-17 10:00:00+00:00",
                "duration_ms": 1755,
                "source_name": "kafka",
                "target_name": "presto_gold",
                "region": "IN-MH",
                "law": "DPDP",
                "fabric_tx": "TX_456",
                "logs": logs,
            }
        ]
    )
    patch_duplicate_handlers(
        monkeypatch, "ensure_pipeline_runs_table", lambda: True
    )
    patch_duplicate_handlers(monkeypatch, "get_conn", lambda: connection)
    patch_duplicate_handlers(
        monkeypatch, "now_iso", lambda: "2026-07-17T10:00:00+00:00"
    )

    response = await client.get(
        "/api/v1/dashboard/pipeline-runs/recent?limit=7"
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "online",
        "storage": "postgres",
        "count": 1,
        "runs": [
            {
                "run_id": "RUN_123",
                "pipeline_id": "pl-test",
                "pipeline_name": "customer_events",
                "status": "completed",
                "started_at": "2026-07-17 09:59:58+00:00",
                "completed_at": "2026-07-17 10:00:00+00:00",
                "duration_ms": 1755,
                "source": "kafka",
                "target": "presto_gold",
                "region": "IN-MH",
                "law": "DPDP",
                "fabric_tx": "TX_456",
                "logs": logs,
            }
        ],
        "timestamp": "2026-07-17T10:00:00+00:00",
    }
    select_statement, select_params = connection.recording_cursor.executions[0]
    assert "ORDER BY id DESC" in select_statement
    assert select_params == (7,)


@pytest.mark.asyncio
async def test_recent_pipeline_runs_uses_memory_fallback(client, monkeypatch):
    patch_duplicate_handlers(
        monkeypatch, "ensure_pipeline_runs_table", lambda: False
    )
    patch_duplicate_handlers(
        monkeypatch, "now_iso", lambda: "2026-07-17T10:00:00+00:00"
    )

    response = await client.get("/api/v1/dashboard/pipeline-runs/recent")

    assert response.status_code == 200
    assert response.json() == {
        "status": "online",
        "storage": "memory",
        "count": 0,
        "runs": [],
        "timestamp": "2026-07-17T10:00:00+00:00",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101])
async def test_recent_pipeline_runs_rejects_out_of_range_limits(
    client, limit
):
    response = await client.get(
        f"/api/v1/dashboard/pipeline-runs/recent?limit={limit}"
    )

    assert response.status_code == 422
