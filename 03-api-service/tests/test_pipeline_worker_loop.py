"""Regression tests for the Kafka pipeline worker's consumer loop."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def worker_module():
    worker_path = (
        Path(__file__).resolve().parents[2]
        / "10-execution"
        / "pipeline-worker"
        / "worker.py"
    )
    spec = importlib.util.spec_from_file_location("pipeline_worker_loop", worker_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KafkaMessage:
    def __init__(self, value: dict[str, Any] | None = None, error: str | None = None):
        self._value = value
        self._error = error

    def error(self):
        return self._error

    def value(self):
        assert self._value is not None
        return json.dumps(self._value).encode("utf-8")


def test_worker_persists_command_before_publishing_completion(
    monkeypatch, worker_module
):
    command = {
        "command_type": "EXECUTE_PIPELINE",
        "run_id": "RUN_123",
        "fabric_tx": "TX_456",
        "pipeline": {"id": "pl-test", "name": "customer_events"},
    }
    logs = [{"step": "audit_commit", "status": "completed"}]
    operations: list[Any] = []
    consumer_configs: list[dict[str, Any]] = []
    producer_configs: list[dict[str, Any]] = []

    class RecordingConsumer:
        def __init__(self, config):
            consumer_configs.append(config)
            self.polls = iter([KafkaMessage(command)])

        def subscribe(self, topics):
            operations.append(("subscribe", topics))

        def poll(self, timeout):
            operations.append(("poll", timeout))
            try:
                return next(self.polls)
            except StopIteration:
                raise KeyboardInterrupt

    class RecordingProducer:
        def __init__(self, config):
            producer_configs.append(config)

        def produce(self, topic, payload):
            operations.append(("produce", topic, json.loads(payload.decode("utf-8"))))

        def flush(self):
            operations.append(("flush",))

    monkeypatch.setattr(worker_module, "Consumer", RecordingConsumer)
    monkeypatch.setattr(worker_module, "Producer", RecordingProducer)
    monkeypatch.setattr(worker_module, "ensure_table", lambda: operations.append(("ensure",)))
    monkeypatch.setattr(
        worker_module,
        "build_logs",
        lambda received: operations.append(("build", received)) or logs,
    )
    monkeypatch.setattr(
        worker_module,
        "save_run",
        lambda received, received_logs: operations.append(
            ("save", received, received_logs)
        ),
    )
    monkeypatch.setattr(
        worker_module, "now_iso", lambda: "2026-07-18T10:00:00+00:00"
    )

    with pytest.raises(KeyboardInterrupt):
        worker_module.main()

    assert consumer_configs == [
        {
            "bootstrap.servers": worker_module.KAFKA_BOOTSTRAP,
            "group.id": "datanexus-worker",
            "auto.offset.reset": "earliest",
        }
    ]
    assert producer_configs == [
        {"bootstrap.servers": worker_module.KAFKA_BOOTSTRAP}
    ]
    assert ("subscribe", [worker_module.COMMAND_TOPIC]) in operations

    save_index = operations.index(("save", command, logs))
    produce_operation = next(operation for operation in operations if operation[0] == "produce")
    produce_index = operations.index(produce_operation)
    assert save_index < produce_index
    assert produce_operation == (
        "produce",
        worker_module.EVENT_TOPIC,
        {
            "run_id": "RUN_123",
            "fabric_tx": "TX_456",
            "status": "completed",
            "ts": "2026-07-18T10:00:00+00:00",
        },
    )
    assert operations[produce_index + 1] == ("flush",)


def test_worker_ignores_empty_polls_and_kafka_errors(
    monkeypatch, worker_module, capsys
):
    operations: list[Any] = []

    class RecordingConsumer:
        def __init__(self, _config):
            self.polls = iter([None, KafkaMessage(error="broker unavailable")])

        def subscribe(self, _topics):
            pass

        def poll(self, _timeout):
            try:
                return next(self.polls)
            except StopIteration:
                raise KeyboardInterrupt

    class RecordingProducer:
        def __init__(self, _config):
            pass

        def produce(self, _topic, _payload):
            operations.append("produce")

        def flush(self):
            operations.append("flush")

    monkeypatch.setattr(worker_module, "Consumer", RecordingConsumer)
    monkeypatch.setattr(worker_module, "Producer", RecordingProducer)
    monkeypatch.setattr(worker_module, "ensure_table", lambda: None)
    monkeypatch.setattr(
        worker_module, "build_logs", lambda _command: operations.append("build")
    )
    monkeypatch.setattr(
        worker_module,
        "save_run",
        lambda _command, _logs: operations.append("save"),
    )

    with pytest.raises(KeyboardInterrupt):
        worker_module.main()

    assert operations == []
    assert "Kafka error: broker unavailable" in capsys.readouterr().out
