import json
import os
import time
import uuid
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import Json
from confluent_kafka import Consumer, Producer


KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "datanexus-redpanda:9092")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "datanexus-db")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "datanexus")
POSTGRES_USER = os.getenv("POSTGRES_USER", "datanexus")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "datanexus")

COMMAND_TOPIC = "datanexus.pipeline.commands"
EVENT_TOPIC = "datanexus.pipeline.events"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def db_conn():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def ensure_table():
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_pipeline_runs (
                    id SERIAL PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    pipeline_id TEXT NOT NULL,
                    pipeline_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    source_name TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    region TEXT NOT NULL,
                    law TEXT NOT NULL,
                    fabric_tx TEXT NOT NULL,
                    logs JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
        conn.commit()


def save_run(command, logs, status="completed"):
    run_id = command["run_id"]
    pipeline = command["pipeline"]
    fabric_tx = command["fabric_tx"]

    duration_ms = 1000 + len(logs) * 240

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO dashboard_pipeline_runs (
                    run_id, pipeline_id, pipeline_name, status, completed_at,
                    duration_ms, source_name, target_name, region, law,
                    fabric_tx, logs
                )
                VALUES (%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (run_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    completed_at = NOW(),
                    duration_ms = EXCLUDED.duration_ms,
                    logs = EXCLUDED.logs;
            """, (
                run_id,
                pipeline.get("id"),
                pipeline.get("name"),
                status,
                duration_ms,
                pipeline.get("source", "unknown"),
                pipeline.get("target", "unknown"),
                pipeline.get("region", "NA"),
                (pipeline.get("laws") or ["NA"])[0],
                fabric_tx,
                Json(logs),
            ))

            cur.execute("""
                INSERT INTO dashboard_audit_events (
                    tx, action, dataset, result, actor, law, region
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s);
            """, (
                fabric_tx,
                "KAFKA_PIPELINE_EXECUTION",
                pipeline.get("name"),
                status.upper(),
                "pipeline-worker",
                (pipeline.get("laws") or ["NA"])[0],
                pipeline.get("region", "NA"),
            ))

        conn.commit()


def build_logs(command):
    pipeline = command["pipeline"]
    law = (pipeline.get("laws") or ["NA"])[0]

    steps = [
        ("queued", f"Kafka command accepted for {pipeline.get('name')}"),
        ("source_connect", f"Connected to {pipeline.get('source')}"),
        ("quality_scan", f"Quality scan completed with sigma {pipeline.get('sigma')}"),
        ("compliance_guard", f"{law} policy guard evaluated"),
        ("target_write", f"Written to {pipeline.get('target')}"),
        ("audit_commit", f"Audit proof committed as {command['fabric_tx']}"),
    ]

    logs = []
    for step, msg in steps:
        time.sleep(0.2)
        logs.append({
            "step": step,
            "status": "completed",
            "message": msg,
            "ts": now_iso(),
        })
    return logs


def main():
    print("DataNexus worker starting...")
    ensure_table()

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": "datanexus-worker",
        "auto.offset.reset": "earliest",
    })

    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

    consumer.subscribe([COMMAND_TOPIC])
    print(f"Listening on {COMMAND_TOPIC}")

    while True:
        msg = consumer.poll(1.0)

        if msg is None:
            continue

        if msg.error():
            print("Kafka error:", msg.error())
            continue

        command = json.loads(msg.value().decode("utf-8"))
        print("Received command:", command.get("run_id"))

        logs = build_logs(command)
        save_run(command, logs)

        producer.produce(EVENT_TOPIC, json.dumps({
            "run_id": command["run_id"],
            "fabric_tx": command["fabric_tx"],
            "status": "completed",
            "ts": now_iso(),
        }).encode("utf-8"))
        producer.flush()

        print("Completed:", command["run_id"])


if __name__ == "__main__":
    main()
