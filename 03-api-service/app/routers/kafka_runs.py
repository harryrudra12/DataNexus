from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi import APIRouter
from confluent_kafka import Producer

from .dashboard import get_pipelines_from_db, now_iso

router = APIRouter(prefix="/api/v1/dashboard", tags=["kafka-execution"])

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "datanexus-redpanda:9092")
COMMAND_TOPIC = "datanexus.pipeline.commands"


@router.post("/pipelines/{pipeline_id}/execute-kafka")
async def execute_pipeline_via_kafka(pipeline_id: str) -> dict[str, Any]:
    pipelines = get_pipelines_from_db()
    pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)

    if not pipeline:
        return {
            "status": "not_found",
            "message": f"Pipeline {pipeline_id} was not found",
            "timestamp": now_iso(),
        }

    run_id = "RUN_" + uuid.uuid4().hex[:12]
    fabric_tx = "TX_" + uuid.uuid4().hex[:12]

    command = {
        "command_type": "EXECUTE_PIPELINE",
        "run_id": run_id,
        "fabric_tx": fabric_tx,
        "pipeline": pipeline,
        "timestamp": now_iso(),
    }

    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    producer.produce(COMMAND_TOPIC, json.dumps(command).encode("utf-8"))
    producer.flush()

    return {
        "status": "queued",
        "message": "Pipeline execution command published to Kafka",
        "run_id": run_id,
        "fabric_tx": fabric_tx,
        "topic": COMMAND_TOPIC,
        "pipeline": pipeline,
        "timestamp": now_iso(),
    }
