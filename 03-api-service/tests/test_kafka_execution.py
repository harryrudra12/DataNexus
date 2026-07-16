"""Contract tests for Kafka-backed pipeline execution."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from app.routers import kafka_runs


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


@pytest.fixture
def worker_module():
    worker_path = (
        Path(__file__).resolve().parents[2]
        / "10-execution"
        / "pipeline-worker"
        / "worker.py"
    )
    spec = importlib.util.spec_from_file_location("pipeline_worker", worker_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_execute_pipeline_publishes_complete_command(monkeypatch, pipeline):
    published: list[tuple[str, bytes]] = []

    class RecordingProducer:
        def __init__(self, config):
            assert config == {"bootstrap.servers": kafka_runs.KAFKA_BOOTSTRAP}

        def produce(self, topic, payload):
            published.append((topic, payload))

        def flush(self):
            return 0

    monkeypatch.setattr(kafka_runs, "get_pipelines_from_db", lambda: [pipeline])
    monkeypatch.setattr(kafka_runs, "Producer", RecordingProducer)
    monkeypatch.setattr(kafka_runs, "now_iso", lambda: "2026-07-16T10:00:00+00:00")

    response = await kafka_runs.execute_pipeline_via_kafka(pipeline["id"])

    assert response["status"] == "queued"
    assert response["topic"] == kafka_runs.COMMAND_TOPIC
    assert len(published) == 1

    topic, payload = published[0]
    command = json.loads(payload.decode("utf-8"))
    assert topic == kafka_runs.COMMAND_TOPIC
    assert command == {
        "command_type": "EXECUTE_PIPELINE",
        "run_id": response["run_id"],
        "fabric_tx": response["fabric_tx"],
        "pipeline": pipeline,
        "timestamp": "2026-07-16T10:00:00+00:00",
    }
    assert response["run_id"].startswith("RUN_")
    assert response["fabric_tx"].startswith("TX_")


@pytest.mark.asyncio
async def test_execute_pipeline_does_not_publish_unknown_pipeline(monkeypatch):
    def unexpected_producer(_config):
        pytest.fail("Kafka producer must not be created for an unknown pipeline")

    monkeypatch.setattr(kafka_runs, "get_pipelines_from_db", lambda: [])
    monkeypatch.setattr(kafka_runs, "Producer", unexpected_producer)
    monkeypatch.setattr(kafka_runs, "now_iso", lambda: "2026-07-16T10:00:00+00:00")

    response = await kafka_runs.execute_pipeline_via_kafka("missing")

    assert response == {
        "status": "not_found",
        "message": "Pipeline missing was not found",
        "timestamp": "2026-07-16T10:00:00+00:00",
    }


def test_worker_builds_ordered_completed_logs(monkeypatch, worker_module, pipeline):
    sleeps: list[float] = []
    monkeypatch.setattr(worker_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        worker_module, "now_iso", lambda: "2026-07-16T10:00:01+00:00"
    )
    command = {
        "run_id": "RUN_123",
        "fabric_tx": "TX_456",
        "pipeline": pipeline,
    }

    logs = worker_module.build_logs(command)

    assert [log["step"] for log in logs] == [
        "queued",
        "source_connect",
        "quality_scan",
        "compliance_guard",
        "target_write",
        "audit_commit",
    ]
    assert all(log["status"] == "completed" for log in logs)
    assert all(log["ts"] == "2026-07-16T10:00:01+00:00" for log in logs)
    assert "DPDP policy guard evaluated" in logs[3]["message"]
    assert "TX_456" in logs[-1]["message"]
    assert sleeps == [0.2] * 6


def test_worker_uses_fallbacks_for_missing_optional_pipeline_fields(
    monkeypatch, worker_module
):
    monkeypatch.setattr(worker_module.time, "sleep", lambda _delay: None)
    command = {
        "run_id": "RUN_123",
        "fabric_tx": "TX_456",
        "pipeline": {
            "id": "pl-minimal",
            "name": "minimal",
            "source": "source",
            "target": "target",
        },
    }

    logs = worker_module.build_logs(command)

    assert logs[3]["message"] == "NA policy guard evaluated"
    assert "None" in logs[2]["message"]


def test_worker_persists_run_and_audit_event(monkeypatch, worker_module, pipeline):
    executions: list[tuple[str, tuple[Any, ...] | None]] = []

    class RecordingCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, params=None):
            executions.append((statement, params))

    class RecordingConnection:
        commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return RecordingCursor()

        def commit(self):
            self.commits += 1

    connection = RecordingConnection()
    monkeypatch.setattr(worker_module, "db_conn", lambda: connection)
    command = {
        "run_id": "RUN_123",
        "fabric_tx": "TX_456",
        "pipeline": pipeline,
    }
    logs = [{"step": "audit_commit", "status": "completed"}]

    worker_module.save_run(command, logs)

    assert len(executions) == 2
    run_statement, run_params = executions[0]
    assert "ON CONFLICT (run_id) DO UPDATE" in run_statement
    assert run_params[:10] == (
        "RUN_123",
        "pl-test",
        "customer_events",
        "completed",
        1240,
        "kafka",
        "presto_gold",
        "IN-MH",
        "DPDP",
        "TX_456",
    )
    assert run_params[10].adapted == logs

    audit_statement, audit_params = executions[1]
    assert "INSERT INTO dashboard_audit_events" in audit_statement
    assert audit_params == (
        "TX_456",
        "KAFKA_PIPELINE_EXECUTION",
        "customer_events",
        "COMPLETED",
        "pipeline-worker",
        "DPDP",
        "IN-MH",
    )
    assert connection.commits == 1
