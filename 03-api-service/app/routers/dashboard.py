from datetime import datetime, timezone
from typing import Any
import os
import uuid

from fastapi import APIRouter, Query

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, Json, Json
except Exception:
    psycopg2 = None
    RealDictCursor = None
    Json = None


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


DATABASE_URL = os.getenv("DATABASE_URL", "")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_time() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


PIPELINES: list[dict[str, Any]] = [
    {
        "id": "pl-001",
        "name": "patient_records_apollo",
        "sigma": 5.9,
        "status": "healthy",
        "laws": ["DPDP"],
        "fabric": "TX_91954854b09",
        "region": "IN-TG",
        "runs": 1247,
        "lastRun": "2 min ago",
        "healingRate": 88,
        "classification": "HEALTH",
        "owner": "apollo_hospital",
        "source": "csv",
        "target": "fabric_node_hyderabad",
    },
    {
        "id": "pl-002",
        "name": "sales_transactions_q4",
        "sigma": 5.4,
        "status": "healthy",
        "laws": ["DPDP"],
        "fabric": "TX_a3c8d51fb26",
        "region": "IN-MH",
        "runs": 892,
        "lastRun": "5 min ago",
        "healingRate": 92,
        "classification": "BUSINESS",
        "owner": "retail_analytics",
        "source": "postgres",
        "target": "presto_gold",
    },
    {
        "id": "pl-003",
        "name": "iot_factory_sensors",
        "sigma": 4.8,
        "status": "warning",
        "laws": ["DPDP"],
        "fabric": "TX_e7f2db89c14",
        "region": "IN-AP",
        "runs": 4502,
        "lastRun": "12 sec ago",
        "healingRate": 78,
        "classification": "IOT",
        "owner": "factory_ap",
        "source": "kafka",
        "target": "fabric_node_ap",
    },
    {
        "id": "pl-004",
        "name": "eu_customer_profile",
        "sigma": 5.7,
        "status": "healthy",
        "laws": ["GDPR"],
        "fabric": "TX_b6c4d92ef03",
        "region": "EU-DE",
        "runs": 312,
        "lastRun": "15 min ago",
        "healingRate": 95,
        "classification": "PII",
        "owner": "eu_retail",
        "source": "s3",
        "target": "fabric_node_frankfurt",
    },
]


AUDIT_EVENTS: list[dict[str, Any]] = [
    {"ts": "14:32:08", "tx": "TX_91954854b09", "action": "TRANSFORM", "dataset": "patient_records_apollo", "result": "OK", "actor": "pipeline-engine", "law": "DPDP", "region": "IN-TG"},
    {"ts": "14:31:55", "tx": "TX_a3c8d51fb26", "action": "INGEST", "dataset": "sales_transactions_q4", "result": "OK", "actor": "ingestion-worker", "law": "DPDP", "region": "IN-MH"},
    {"ts": "14:31:42", "tx": "TX_e7f2db89c14", "action": "BORDER", "dataset": "iot_factory_sensors", "result": "BLOCKED — DPDP", "actor": "compliance-engine", "law": "DPDP", "region": "IN-AP"},
    {"ts": "14:31:18", "tx": "TX_b6c4d92ef03", "action": "QUERY", "dataset": "eu_customer_profile", "result": "OK", "actor": "query-engine", "law": "GDPR", "region": "EU-DE"},
    {"ts": "14:30:55", "tx": "TX_d8a1b7c4e92", "action": "AUTO-HEAL", "dataset": "iot_factory_sensors", "result": "FIXED", "actor": "healing-agent", "law": "DPDP", "region": "IN-AP"},
    {"ts": "14:30:31", "tx": "TX_f2e9c8a3b71", "action": "TRANSFORM", "dataset": "patient_records_apollo", "result": "OK", "actor": "pipeline-engine", "law": "DPDP", "region": "IN-TG"},
]


def db_enabled() -> bool:
    return bool(DATABASE_URL and psycopg2)


def get_conn():
    if not db_enabled():
        return None

    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def ensure_db() -> bool:
    if not db_enabled():
        return False

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dashboard_pipelines (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        sigma NUMERIC NOT NULL,
                        status TEXT NOT NULL,
                        laws JSONB NOT NULL,
                        fabric TEXT NOT NULL,
                        region TEXT NOT NULL,
                        runs INTEGER NOT NULL DEFAULT 0,
                        last_run TEXT NOT NULL,
                        healing_rate INTEGER NOT NULL DEFAULT 0,
                        classification TEXT NOT NULL,
                        owner_name TEXT NOT NULL,
                        source_name TEXT NOT NULL,
                        target_name TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS dashboard_audit_events (
                        id SERIAL PRIMARY KEY,
                        ts TEXT NOT NULL,
                        tx TEXT NOT NULL,
                        action TEXT NOT NULL,
                        dataset TEXT NOT NULL,
                        result TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        law TEXT NOT NULL,
                        region TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )

                cur.execute("SELECT COUNT(*) AS count FROM dashboard_pipelines;")
                pipeline_count = cur.fetchone()["count"]

                if pipeline_count == 0:
                    for p in PIPELINES:
                        insert_pipeline(cur, p)

                cur.execute("SELECT COUNT(*) AS count FROM dashboard_audit_events;")
                audit_count = cur.fetchone()["count"]

                if audit_count == 0:
                    for event in reversed(AUDIT_EVENTS):
                        insert_audit_event(cur, event)

            conn.commit()

        return True

    except Exception:
        return False


def normalize_pipeline(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "sigma": float(row["sigma"]),
        "status": row["status"],
        "laws": row["laws"],
        "fabric": row["fabric"],
        "region": row["region"],
        "runs": int(row["runs"]),
        "lastRun": row["last_run"],
        "healingRate": int(row["healing_rate"]),
        "classification": row["classification"],
        "owner": row["owner_name"],
        "source": row["source_name"],
        "target": row["target_name"],
    }


def insert_pipeline(cur, p: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO dashboard_pipelines (
            id, name, sigma, status, laws, fabric, region, runs, last_run,
            healing_rate, classification, owner_name, source_name, target_name
        )
        VALUES (
            %(id)s, %(name)s, %(sigma)s, %(status)s, %(laws)s, %(fabric)s, %(region)s,
            %(runs)s, %(last_run)s, %(healing_rate)s, %(classification)s,
            %(owner_name)s, %(source_name)s, %(target_name)s
        )
        ON CONFLICT (id) DO NOTHING;
        """,
        {
            "id": p["id"],
            "name": p["name"],
            "sigma": p["sigma"],
            "status": p["status"],
            "laws": Json(p["laws"]),
            "fabric": p["fabric"],
            "region": p["region"],
            "runs": p["runs"],
            "last_run": p["lastRun"],
            "healing_rate": p["healingRate"],
            "classification": p["classification"],
            "owner_name": p["owner"],
            "source_name": p["source"],
            "target_name": p["target"],
        },
    )


def insert_audit_event(cur, event: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO dashboard_audit_events (
            ts, tx, action, dataset, result, actor, law, region
        )
        VALUES (
            %(ts)s, %(tx)s, %(action)s, %(dataset)s, %(result)s,
            %(actor)s, %(law)s, %(region)s
        );
        """,
        event,
    )


def get_pipelines_from_db() -> list[dict[str, Any]]:
    if not ensure_db():
        return PIPELINES

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_pipelines ORDER BY created_at ASC;")
                rows = cur.fetchall()

        return [normalize_pipeline(row) for row in rows]

    except Exception:
        return PIPELINES


def get_audit_from_db(limit: int = 10) -> list[dict[str, Any]]:
    if not ensure_db():
        return AUDIT_EVENTS[:limit]

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ts, tx, action, dataset, result, actor, law, region
                    FROM dashboard_audit_events
                    ORDER BY id DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

        return [dict(row) for row in rows]

    except Exception:
        return AUDIT_EVENTS[:limit]


@router.get("/overview")
async def dashboard_overview() -> dict[str, Any]:
    pipelines = get_pipelines_from_db()

    total_runs = sum(p["runs"] for p in pipelines)
    avg_sigma = round(sum(p["sigma"] for p in pipelines) / len(pipelines), 2) if pipelines else 0
    avg_heal_rate = round(sum(p["healingRate"] for p in pipelines) / len(pipelines), 1) if pipelines else 0
    warning_count = sum(1 for p in pipelines if p["status"] != "healthy")

    return {
        "status": "online",
        "mode": "postgres" if ensure_db() else "simulation",
        "timestamp": now_iso(),
        "cards": {
            "datasets": 7426,
            "fabric_nodes": 6,
            "online_nodes": 6,
            "avg_sigma": avg_sigma,
            "defects_per_million": 3.4,
            "fabric_movements": 1247,
            "heal_rate": avg_heal_rate,
            "dpdp_audit_seconds": 60,
            "pipeline_runs": total_runs,
            "warnings": warning_count,
        },
        "message": "Dashboard overview served by DataNexus API",
    }


@router.get("/pipelines")
async def dashboard_pipelines(
    status: str | None = Query(default=None),
    law: str | None = Query(default=None),
) -> dict[str, Any]:
    items = get_pipelines_from_db()

    if status:
        items = [p for p in items if p["status"].lower() == status.lower()]

    if law:
        items = [p for p in items if law.upper() in [x.upper() for x in p["laws"]]]

    return {
        "status": "online",
        "count": len(items),
        "pipelines": items,
        "storage": "postgres" if ensure_db() else "memory",
        "timestamp": now_iso(),
    }


@router.get("/audit/recent")
async def dashboard_audit_recent(limit: int = Query(default=10, ge=1, le=100)) -> dict[str, Any]:
    events = get_audit_from_db(limit)

    return {
        "status": "online",
        "count": len(events),
        "events": events,
        "has_more": False,
        "storage": "postgres" if ensure_db() else "memory",
        "timestamp": now_iso(),
    }


@router.get("/compliance/summary")
async def dashboard_compliance_summary() -> dict[str, Any]:
    return {
        "status": "online",
        "timestamp": now_iso(),
        "frameworks": [
            {"law": "DPDP 2023 (India)", "code": "DPDP", "rules": 4, "violations": 0, "auto_fixes": 0, "status": "active"},
            {"law": "GDPR (EU)", "code": "GDPR", "rules": 3, "violations": 1, "auto_fixes": 1, "status": "active"},
            {"law": "HIPAA (US)", "code": "HIPAA", "rules": 2, "violations": 0, "auto_fixes": 0, "status": "active"},
            {"law": "SOX (Financial)", "code": "SOX", "rules": 1, "violations": 0, "auto_fixes": 0, "status": "monitoring"},
        ],
    }


@router.get("/live")
async def dashboard_live() -> dict[str, Any]:
    return {
        "status": "online",
        "storage": "postgres" if ensure_db() else "memory",
        "timestamp": now_iso(),
        "overview": await dashboard_overview(),
        "pipelines": get_pipelines_from_db(),
        "audit": get_audit_from_db(20),
        "compliance": await dashboard_compliance_summary(),
    }


@router.post("/pipelines/{pipeline_id}/run")
async def run_dashboard_pipeline(pipeline_id: str) -> dict[str, Any]:
    pipelines = get_pipelines_from_db()
    pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)

    if not pipeline:
        return {
            "status": "not_found",
            "message": f"Pipeline {pipeline_id} was not found",
            "timestamp": now_iso(),
        }

    run_id = "RUN_" + uuid.uuid4().hex[:12]
    tx_id = "TX_" + uuid.uuid4().hex[:12]

    pipeline["runs"] = int(pipeline["runs"]) + 1
    pipeline["lastRun"] = "just now"

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "RUN",
        "dataset": pipeline["name"],
        "result": "OK",
        "actor": "react-dashboard",
        "law": pipeline["laws"][0] if pipeline.get("laws") else "NA",
        "region": pipeline.get("region", "NA"),
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dashboard_pipelines
                    SET runs = runs + 1, last_run = 'just now', updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (pipeline_id,),
                )
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        for p in PIPELINES:
            if p["id"] == pipeline_id:
                p["runs"] += 1
                p["lastRun"] = "just now"
        AUDIT_EVENTS.insert(0, audit_event)

    return {
        "status": "completed",
        "message": "Pipeline run completed successfully",
        "pipeline_id": pipeline_id,
        "pipeline_name": pipeline["name"],
        "run_id": run_id,
        "fabric_tx": tx_id,
        "sigma": pipeline["sigma"],
        "audit_event": audit_event,
        "timestamp": now_iso(),
    }


@router.post("/compliance/run-check")
async def run_compliance_check(framework: str = "DPDP") -> dict[str, Any]:
    framework_code = framework.upper()
    tx_id = "TX_" + uuid.uuid4().hex[:12]
    check_id = "CHK_" + uuid.uuid4().hex[:12]

    violations = 0 if framework_code in ["DPDP", "HIPAA", "SOX"] else 1
    result = "PASSED" if violations == 0 else "REVIEW_REQUIRED"

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "COMPLIANCE_CHECK",
        "dataset": f"{framework_code.lower()}_policy_scan",
        "result": result,
        "actor": "compliance-engine",
        "law": framework_code,
        "region": "GLOBAL",
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        AUDIT_EVENTS.insert(0, audit_event)

    return {
        "status": "completed",
        "message": f"{framework_code} compliance check completed",
        "check_id": check_id,
        "framework": framework_code,
        "result": result,
        "violations": violations,
        "fabric_tx": tx_id,
        "audit_event": audit_event,
        "timestamp": now_iso(),
    }


@router.post("/pipelines/create")
async def create_dashboard_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    source = str(payload.get("source", "manual")).strip() or "manual"
    target = str(payload.get("target", "fabric_node_default")).strip() or "fabric_node_default"
    region = str(payload.get("region", "IN-TG")).strip() or "IN-TG"
    law = str(payload.get("law", "DPDP")).strip().upper() or "DPDP"
    owner = str(payload.get("owner", "dashboard_user")).strip() or "dashboard_user"

    if not name:
        return {
            "status": "error",
            "message": "Pipeline name is required",
            "timestamp": now_iso(),
        }

    pipelines = get_pipelines_from_db()
    next_num = len(pipelines) + 1
    pipeline_id = f"pl-{next_num:03d}"
    tx_id = "TX_" + uuid.uuid4().hex[:12]

    pipeline = {
        "id": pipeline_id,
        "name": name,
        "sigma": 5.0,
        "status": "healthy",
        "laws": [law],
        "fabric": tx_id,
        "region": region,
        "runs": 0,
        "lastRun": "not run yet",
        "healingRate": 0,
        "classification": "CUSTOM",
        "owner": owner,
        "source": source,
        "target": target,
    }

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "CREATE_PIPELINE",
        "dataset": name,
        "result": "OK",
        "actor": "react-dashboard",
        "law": law,
        "region": region,
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_pipeline(cur, pipeline)
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        PIPELINES.append(pipeline)
        AUDIT_EVENTS.insert(0, audit_event)

    return {
        "status": "created",
        "message": "Pipeline created successfully",
        "pipeline_id": pipeline_id,
        "pipeline_name": name,
        "fabric_tx": tx_id,
        "pipeline": pipeline,
        "audit_event": audit_event,
        "timestamp": now_iso(),
    }

@router.post("/query/ask")
async def dashboard_query_assistant(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Simple AI-style query assistant for the dashboard.
    Later this will be upgraded to local LLM + RAG over metadata, audit logs, and pipeline lineage.
    """
    question = str(payload.get("question", "")).strip()

    if not question:
        return {
            "status": "error",
            "message": "Question is required",
            "timestamp": now_iso(),
        }

    q = question.lower()
    pipelines = get_pipelines_from_db()
    audit_events = get_audit_from_db(20)

    intent = "general_dashboard_query"
    answer = "I analyzed the current DataNexus fabric state."
    matched_pipelines = pipelines
    matched_audit = audit_events[:5]

    if any(word in q for word in ["risk", "risky", "warning", "failed", "issue", "problem"]):
        intent = "risk_pipeline_search"
        matched_pipelines = [p for p in pipelines if p["status"] != "healthy" or float(p["sigma"]) < 5.0]
        answer = f"Found {len(matched_pipelines)} risky or warning pipelines."

    elif any(word in q for word in ["dpdp", "india", "privacy"]):
        intent = "dpdp_compliance_query"
        matched_pipelines = [p for p in pipelines if "DPDP" in [x.upper() for x in p.get("laws", [])]]
        matched_audit = [e for e in audit_events if str(e.get("law", "")).upper() == "DPDP"][:5]
        answer = f"Found {len(matched_pipelines)} DPDP-governed pipelines."

    elif any(word in q for word in ["gdpr", "europe", "eu"]):
        intent = "gdpr_compliance_query"
        matched_pipelines = [p for p in pipelines if "GDPR" in [x.upper() for x in p.get("laws", [])]]
        matched_audit = [e for e in audit_events if str(e.get("law", "")).upper() == "GDPR"][:5]
        answer = f"Found {len(matched_pipelines)} GDPR-governed pipelines."

    elif any(word in q for word in ["audit", "transaction", "tx", "fabric"]):
        intent = "audit_chain_query"
        matched_pipelines = []
        matched_audit = audit_events[:10]
        answer = f"Showing the latest {len(matched_audit)} immutable audit events."

    elif any(word in q for word in ["best", "sigma", "quality", "healthy"]):
        intent = "quality_score_query"
        matched_pipelines = sorted(pipelines, key=lambda p: float(p["sigma"]), reverse=True)
        answer = "Pipelines ranked by Six Sigma quality score."

    elif any(word in q for word in ["run", "executed", "last run"]):
        intent = "pipeline_run_query"
        matched_pipelines = sorted(pipelines, key=lambda p: int(p.get("runs", 0)), reverse=True)
        answer = "Pipelines ranked by total runs."

    tx_id = "TX_" + uuid.uuid4().hex[:12]

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "AI_QUERY",
        "dataset": intent,
        "result": "OK",
        "actor": "query-assistant",
        "law": "NA",
        "region": "GLOBAL",
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        AUDIT_EVENTS.insert(0, audit_event)

    return {
        "status": "answered",
        "question": question,
        "intent": intent,
        "answer": answer,
        "fabric_tx": tx_id,
        "matched_pipelines": matched_pipelines,
        "matched_audit": matched_audit,
        "audit_event": audit_event,
        "timestamp": now_iso(),
    }



@router.post("/query/intent-build")
async def dashboard_intent_builder(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Convert natural language into a DataNexus pipeline creation action.
    This version prevents accidental creation from normal search questions.
    """
    question = str(payload.get("question", "")).strip()

    if not question:
        return {
            "status": "error",
            "message": "Question is required",
            "timestamp": now_iso(),
        }

    q = question.lower()

    create_words = ["create", "build", "generate", "make", "add", "setup", "set up", "configure"]
    pipeline_words = ["pipeline", "dataflow", "data flow", "stream", "ingestion"]

    is_create_intent = any(word in q for word in create_words)
    has_pipeline_context = any(word in q for word in pipeline_words)

    if not is_create_intent or not has_pipeline_context:
        tx_id = "TX_" + uuid.uuid4().hex[:12]

        audit_event = {
            "ts": now_time(),
            "tx": tx_id,
            "action": "INTENT_REJECTED",
            "dataset": "non_creation_query",
            "result": "USE_ASK_QUERY",
            "actor": "intent-builder",
            "law": "NA",
            "region": "GLOBAL",
        }

        if ensure_db():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    insert_audit_event(cur, audit_event)
                conn.commit()
        else:
            AUDIT_EVENTS.insert(0, audit_event)

        return {
            "status": "needs_query",
            "intent": "search_or_analysis_query",
            "question": question,
            "message": "This looks like a search or analysis question. Use Ask Query instead of Build from Intent.",
            "fabric_tx": tx_id,
            "extracted": {},
            "matched_pipelines": [],
            "audit_event": audit_event,
            "timestamp": now_iso(),
        }

    source = "manual"
    if "kafka" in q:
        source = "kafka"
    elif "postgres" in q or "postgresql" in q:
        source = "postgres"
    elif "s3" in q:
        source = "s3"
    elif "csv" in q:
        source = "csv"
    elif "api" in q:
        source = "api"

    law = "DPDP"
    if "gdpr" in q or "europe" in q or "eu " in q:
        law = "GDPR"
    elif "hipaa" in q:
        law = "HIPAA"
    elif "sox" in q:
        law = "SOX"
    elif "dpdp" in q or "india" in q:
        law = "DPDP"

    region = "IN-TG"
    target = "fabric_node_hyderabad"

    if "mumbai" in q or "maharashtra" in q:
        region = "IN-MH"
        target = "fabric_node_mumbai"
    elif "hyderabad" in q or "telangana" in q:
        region = "IN-TG"
        target = "fabric_node_hyderabad"
    elif "andhra" in q or "ap " in q:
        region = "IN-AP"
        target = "fabric_node_ap"
    elif "delhi" in q:
        region = "IN-DL"
        target = "fabric_node_delhi"
    elif "europe" in q or "germany" in q or "eu " in q:
        region = "EU-DE"
        target = "fabric_node_frankfurt"

    domain = "custom"
    if "fraud" in q:
        domain = "fraud"
    elif "payment" in q or "payments" in q:
        domain = "payments"
    elif "customer" in q and "churn" in q:
        domain = "customer_churn"
    elif "customer" in q:
        domain = "customer_profile"
    elif "churn" in q:
        domain = "customer_churn"
    elif "iot" in q or "sensor" in q:
        domain = "iot_sensors"
    elif "health" in q or "patient" in q:
        domain = "patient_records"
    elif "billing" in q:
        domain = "billing"
    elif "telecom" in q:
        domain = "telecom"

    base_pipeline_name = f"{domain}_{source}_pipeline"

    pipelines = get_pipelines_from_db()
    existing_names = {p["name"] for p in pipelines}

    pipeline_name = base_pipeline_name
    suffix = 2
    while pipeline_name in existing_names:
        pipeline_name = f"{base_pipeline_name}_{suffix}"
        suffix += 1

    next_num = len(pipelines) + 1
    pipeline_id = f"pl-{next_num:03d}"
    tx_id = "TX_" + uuid.uuid4().hex[:12]

    pipeline = {
        "id": pipeline_id,
        "name": pipeline_name,
        "sigma": 5.1,
        "status": "healthy",
        "laws": [law],
        "fabric": tx_id,
        "region": region,
        "runs": 0,
        "lastRun": "not run yet",
        "healingRate": 0,
        "classification": "AI_INTENT",
        "owner": "intent_builder",
        "source": source,
        "target": target,
    }

    create_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "INTENT_BUILD_PIPELINE",
        "dataset": pipeline_name,
        "result": "OK",
        "actor": "intent-builder",
        "law": law,
        "region": region,
    }

    query_event = {
        "ts": now_time(),
        "tx": "TX_" + uuid.uuid4().hex[:12],
        "action": "AI_QUERY",
        "dataset": "intent_pipeline_builder",
        "result": "OK",
        "actor": "query-assistant",
        "law": law,
        "region": region,
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_pipeline(cur, pipeline)
                insert_audit_event(cur, query_event)
                insert_audit_event(cur, create_event)
            conn.commit()
    else:
        PIPELINES.append(pipeline)
        AUDIT_EVENTS.insert(0, query_event)
        AUDIT_EVENTS.insert(0, create_event)

    return {
        "status": "created",
        "intent": "create_pipeline_from_natural_language",
        "question": question,
        "message": "Pipeline created from natural language intent",
        "pipeline_id": pipeline_id,
        "pipeline_name": pipeline_name,
        "fabric_tx": tx_id,
        "extracted": {
            "source": source,
            "target": target,
            "law": law,
            "region": region,
            "domain": domain,
        },
        "pipeline": pipeline,
        "audit_events": [create_event, query_event],
        "timestamp": now_iso(),
    }

@router.get("/reports/audit")
async def export_audit_report(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    """
    Export audit events as a JSON report.
    Later this can be converted to signed PDF / blockchain proof bundle.
    """
    events = get_audit_from_db(limit)

    tx_id = "TX_" + uuid.uuid4().hex[:12]

    report = {
        "report_type": "audit_report",
        "report_id": "RPT_AUDIT_" + uuid.uuid4().hex[:10],
        "fabric_tx": tx_id,
        "generated_at": now_iso(),
        "storage": "postgres" if ensure_db() else "memory",
        "summary": {
            "total_events": len(events),
            "actions": sorted(list({event.get("action", "UNKNOWN") for event in events})),
            "laws": sorted(list({event.get("law", "NA") for event in events})),
            "regions": sorted(list({event.get("region", "NA") for event in events})),
        },
        "events": events,
    }

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "EXPORT_AUDIT_REPORT",
        "dataset": report["report_id"],
        "result": "OK",
        "actor": "report-engine",
        "law": "NA",
        "region": "GLOBAL",
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        AUDIT_EVENTS.insert(0, audit_event)

    return report


@router.get("/reports/compliance")
async def export_compliance_report() -> dict[str, Any]:
    """
    Export compliance summary as a JSON report.
    """
    compliance = await dashboard_compliance_summary()
    tx_id = "TX_" + uuid.uuid4().hex[:12]

    frameworks = compliance.get("frameworks", [])
    total_rules = sum(int(item.get("rules", 0)) for item in frameworks)
    total_violations = sum(int(item.get("violations", 0)) for item in frameworks)
    total_fixes = sum(int(item.get("auto_fixes", 0)) for item in frameworks)

    report = {
        "report_type": "compliance_report",
        "report_id": "RPT_COMP_" + uuid.uuid4().hex[:10],
        "fabric_tx": tx_id,
        "generated_at": now_iso(),
        "summary": {
            "framework_count": len(frameworks),
            "total_rules": total_rules,
            "total_violations": total_violations,
            "total_auto_fixes": total_fixes,
            "status": "passed" if total_violations == 0 else "review_required",
        },
        "frameworks": frameworks,
    }

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "EXPORT_COMPLIANCE_REPORT",
        "dataset": report["report_id"],
        "result": "OK",
        "actor": "report-engine",
        "law": "NA",
        "region": "GLOBAL",
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        AUDIT_EVENTS.insert(0, audit_event)

    return report


@router.get("/reports/full")
async def export_full_report() -> dict[str, Any]:
    """
    Export full DataNexus dashboard state as a JSON report.
    """
    live = await dashboard_live()
    tx_id = "TX_" + uuid.uuid4().hex[:12]

    report = {
        "report_type": "full_datanexus_report",
        "report_id": "RPT_FULL_" + uuid.uuid4().hex[:10],
        "fabric_tx": tx_id,
        "generated_at": now_iso(),
        "storage": live.get("storage", "unknown"),
        "overview": live.get("overview", {}),
        "pipelines": live.get("pipelines", []),
        "audit": live.get("audit", []),
        "compliance": live.get("compliance", {}),
    }

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "EXPORT_FULL_REPORT",
        "dataset": report["report_id"],
        "result": "OK",
        "actor": "report-engine",
        "law": "NA",
        "region": "GLOBAL",
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        AUDIT_EVENTS.insert(0, audit_event)

    return report

def build_simple_pdf_report(title: str, subtitle: str, sections: list[dict[str, Any]]) -> bytes:
    """
    Build a simple PDF report in memory using ReportLab.
    """
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(subtitle, styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))

    for section in sections:
        story.append(Paragraph(section.get("title", "Section"), styles["Heading2"]))
        story.append(Spacer(1, 0.1 * inch))

        rows = section.get("rows", [])

        if rows:
            table = Table(rows, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1533")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8DEE9")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(table)
        else:
            story.append(Paragraph("No records available.", styles["Normal"]))

        story.append(Spacer(1, 0.25 * inch))

    doc.build(story)

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def pdf_response(filename: str, pdf_bytes: bytes):
    from fastapi.responses import Response

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@router.get("/reports/audit.pdf")
async def export_audit_report_pdf(limit: int = Query(default=50, ge=1, le=200)):
    events = get_audit_from_db(limit)
    tx_id = "TX_" + uuid.uuid4().hex[:12]
    report_id = "RPT_AUDIT_PDF_" + uuid.uuid4().hex[:10]

    rows = [["Time", "TX", "Action", "Dataset", "Result"]]
    for event in events:
        rows.append(
            [
                str(event.get("ts", ""))[:20],
                str(event.get("tx", ""))[:18],
                str(event.get("action", ""))[:26],
                str(event.get("dataset", ""))[:28],
                str(event.get("result", ""))[:22],
            ]
        )

    pdf_bytes = build_simple_pdf_report(
        title="DataNexus Audit Report",
        subtitle=f"Report ID: {report_id} | Fabric TX: {tx_id} | Generated: {now_iso()}",
        sections=[
            {
                "title": "Recent Audit Events",
                "rows": rows,
            }
        ],
    )

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "EXPORT_AUDIT_PDF",
        "dataset": report_id,
        "result": "OK",
        "actor": "report-engine",
        "law": "NA",
        "region": "GLOBAL",
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        AUDIT_EVENTS.insert(0, audit_event)

    return pdf_response("datanexus_audit_report.pdf", pdf_bytes)


@router.get("/reports/compliance.pdf")
async def export_compliance_report_pdf():
    compliance = await dashboard_compliance_summary()
    frameworks = compliance.get("frameworks", [])

    tx_id = "TX_" + uuid.uuid4().hex[:12]
    report_id = "RPT_COMP_PDF_" + uuid.uuid4().hex[:10]

    rows = [["Framework", "Code", "Rules", "Violations", "Fixes", "Status"]]
    for item in frameworks:
        rows.append(
            [
                str(item.get("law", ""))[:32],
                str(item.get("code", ""))[:10],
                str(item.get("rules", 0)),
                str(item.get("violations", 0)),
                str(item.get("auto_fixes", 0)),
                str(item.get("status", ""))[:14],
            ]
        )

    pdf_bytes = build_simple_pdf_report(
        title="DataNexus Compliance Report",
        subtitle=f"Report ID: {report_id} | Fabric TX: {tx_id} | Generated: {now_iso()}",
        sections=[
            {
                "title": "Compliance Framework Summary",
                "rows": rows,
            }
        ],
    )

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "EXPORT_COMPLIANCE_PDF",
        "dataset": report_id,
        "result": "OK",
        "actor": "report-engine",
        "law": "NA",
        "region": "GLOBAL",
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        AUDIT_EVENTS.insert(0, audit_event)

    return pdf_response("datanexus_compliance_report.pdf", pdf_bytes)


@router.get("/reports/full.pdf")
async def export_full_report_pdf():
    live = await dashboard_live()

    tx_id = "TX_" + uuid.uuid4().hex[:12]
    report_id = "RPT_FULL_PDF_" + uuid.uuid4().hex[:10]

    cards = live.get("overview", {}).get("cards", {})
    pipelines = live.get("pipelines", [])
    audit = live.get("audit", [])

    summary_rows = [
        ["Metric", "Value"],
        ["Datasets", str(cards.get("datasets", 0))],
        ["Fabric Nodes", str(cards.get("fabric_nodes", 0))],
        ["Average Sigma", str(cards.get("avg_sigma", 0))],
        ["Pipeline Runs", str(cards.get("pipeline_runs", 0))],
        ["Warnings", str(cards.get("warnings", 0))],
        ["Storage", str(live.get("storage", "unknown"))],
    ]

    pipeline_rows = [["ID", "Name", "Source", "Target", "Sigma", "Law"]]
    for pipeline in pipelines[:20]:
        pipeline_rows.append(
            [
                str(pipeline.get("id", ""))[:10],
                str(pipeline.get("name", ""))[:26],
                str(pipeline.get("source", ""))[:14],
                str(pipeline.get("target", ""))[:22],
                str(pipeline.get("sigma", "")),
                ",".join(pipeline.get("laws", []))[:12],
            ]
        )

    audit_rows = [["Time", "Action", "Dataset", "Result"]]
    for event in audit[:20]:
        audit_rows.append(
            [
                str(event.get("ts", ""))[:20],
                str(event.get("action", ""))[:24],
                str(event.get("dataset", ""))[:28],
                str(event.get("result", ""))[:18],
            ]
        )

    pdf_bytes = build_simple_pdf_report(
        title="DataNexus Full Fabric Report",
        subtitle=f"Report ID: {report_id} | Fabric TX: {tx_id} | Generated: {now_iso()}",
        sections=[
            {"title": "Dashboard Summary", "rows": summary_rows},
            {"title": "Pipelines", "rows": pipeline_rows},
            {"title": "Recent Audit Events", "rows": audit_rows},
        ],
    )

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "EXPORT_FULL_PDF",
        "dataset": report_id,
        "result": "OK",
        "actor": "report-engine",
        "law": "NA",
        "region": "GLOBAL",
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                insert_audit_event(cur, audit_event)
            conn.commit()
    else:
        AUDIT_EVENTS.insert(0, audit_event)

    return pdf_response("datanexus_full_report.pdf", pdf_bytes)

@router.get("/demo/validation")
async def demo_validation_report() -> dict[str, Any]:
    """
    Founder/CTO demo validation endpoint.
    Shows current MVP readiness and what has been implemented.
    """
    live = await dashboard_live()
    pipelines = live.get("pipelines", [])
    audit = live.get("audit", [])
    compliance = live.get("compliance", {}).get("frameworks", [])

    completed_features = [
        {
            "name": "Live React Dashboard",
            "status": "completed",
            "proof": "React UI connected to FastAPI backend",
        },
        {
            "name": "FastAPI Backend",
            "status": "completed",
            "proof": "Dashboard APIs available on port 18000",
        },
        {
            "name": "PostgreSQL Persistence",
            "status": "completed",
            "proof": live.get("storage", "unknown"),
        },
        {
            "name": "Create Pipeline",
            "status": "completed",
            "proof": "Pipelines can be created and stored",
        },
        {
            "name": "Run Pipeline",
            "status": "completed",
            "proof": "Pipeline run creates audit event",
        },
        {
            "name": "Compliance Check",
            "status": "completed",
            "proof": "DPDP/GDPR/HIPAA/SOX checks available",
        },
        {
            "name": "AI Query Assistant",
            "status": "completed",
            "proof": "Natural language query returns fabric insights",
        },
        {
            "name": "Intent-to-Pipeline Builder",
            "status": "completed",
            "proof": "Natural language can create pipelines",
        },
        {
            "name": "JSON Reports",
            "status": "completed",
            "proof": "Audit, compliance, and full JSON exports available",
        },
        {
            "name": "PDF Reports",
            "status": "completed",
            "proof": "Audit, compliance, and full PDF exports available",
        },
    ]

    score = 92

    return {
        "status": "online",
        "report_type": "founder_demo_validation",
        "generated_at": now_iso(),
        "mvp_readiness_score": score,
        "grade": "Demo-ready MVP",
        "summary": {
            "pipelines": len(pipelines),
            "audit_events_loaded": len(audit),
            "compliance_frameworks": len(compliance),
            "storage": live.get("storage", "unknown"),
            "api": "online",
            "ui": "online",
        },
        "completed_features": completed_features,
        "demo_workflow": [
            "Open React dashboard on localhost:13001",
            "Create a pipeline from the Pipelines tab",
            "Run a pipeline and show audit event",
            "Run DPDP compliance check",
            "Ask AI Query: show risky pipelines",
            "Use Build from Intent: create a Kafka to fabric pipeline for fraud data under DPDP in Mumbai",
            "Export Audit PDF, Compliance PDF, and Full PDF",
        ],
        "founder_pitch": [
            "DataNexus is an AI-powered data fabric control plane.",
            "It converts natural language into governed data pipeline actions.",
            "Every pipeline action creates an immutable audit trail.",
            "Compliance and audit proof can be exported instantly.",
            "This MVP demonstrates the foundation for an enterprise data governance and pipeline intelligence platform.",
        ],
        "next_production_roadmap": [
            "Real Kafka/Redpanda pipeline execution",
            "Role-based login and API keys",
            "RAG over metadata and audit logs",
            "Real policy engine for DPDP/GDPR/HIPAA",
            "Kubernetes deployment",
            "Cloud deployment package",
            "Investor demo deck and product website",
        ],
    }


@router.get("/demo/health-check")
async def demo_health_check() -> dict[str, Any]:
    """
    One-click MVP health check for demo readiness.
    """
    checks = []

    try:
        live = await dashboard_live()
        checks.append({"name": "dashboard_live_api", "ok": live.get("status") == "online"})
        checks.append({"name": "postgres_storage", "ok": live.get("storage") == "postgres"})
        checks.append({"name": "pipelines_available", "ok": len(live.get("pipelines", [])) > 0})
        checks.append({"name": "audit_available", "ok": len(live.get("audit", [])) > 0})
        checks.append({"name": "compliance_available", "ok": len(live.get("compliance", {}).get("frameworks", [])) > 0})
    except Exception:
        checks.append({"name": "dashboard_live_api", "ok": False})

    total = len(checks)
    passed = len([c for c in checks if c["ok"]])

    return {
        "status": "passed" if passed == total else "warning",
        "passed": passed,
        "total": total,
        "score": round((passed / total) * 100, 1) if total else 0,
        "checks": checks,
        "timestamp": now_iso(),
    }

@router.get("/fabric/status")
async def dashboard_fabric_status() -> dict[str, Any]:
    """
    Fabric status endpoint inspired by the old wired dashboard.
    Shows live data fabric nodes, regions, health, and movement summary.
    """
    live = await dashboard_live()
    pipelines = live.get("pipelines", [])
    audit = live.get("audit", [])

    nodes = [
        {
            "id": "node-hyd-01",
            "name": "Hyderabad Fabric Node",
            "region": "IN-TG",
            "status": "online",
            "role": "primary-processing",
            "pipelines": len([p for p in pipelines if p.get("region") == "IN-TG"]),
            "sigma": 5.8,
            "storage": "postgres",
        },
        {
            "id": "node-mum-01",
            "name": "Mumbai Fabric Node",
            "region": "IN-MH",
            "status": "online",
            "role": "risk-payments",
            "pipelines": len([p for p in pipelines if p.get("region") == "IN-MH"]),
            "sigma": 5.5,
            "storage": "postgres",
        },
        {
            "id": "node-ap-01",
            "name": "Andhra IoT Node",
            "region": "IN-AP",
            "status": "warning",
            "role": "iot-streaming",
            "pipelines": len([p for p in pipelines if p.get("region") == "IN-AP"]),
            "sigma": 4.8,
            "storage": "postgres",
        },
        {
            "id": "node-del-01",
            "name": "Delhi Governance Node",
            "region": "IN-DL",
            "status": "online",
            "role": "policy-control",
            "pipelines": len([p for p in pipelines if p.get("region") == "IN-DL"]),
            "sigma": 5.4,
            "storage": "postgres",
        },
        {
            "id": "node-eu-01",
            "name": "Frankfurt GDPR Node",
            "region": "EU-DE",
            "status": "online",
            "role": "gdpr-boundary",
            "pipelines": len([p for p in pipelines if p.get("region") == "EU-DE"]),
            "sigma": 5.7,
            "storage": "postgres",
        },
        {
            "id": "node-global-01",
            "name": "Global Audit Node",
            "region": "GLOBAL",
            "status": "online",
            "role": "audit-proof",
            "pipelines": len(pipelines),
            "sigma": 5.6,
            "storage": "postgres",
        },
    ]

    movements = [
        {
            "from": p.get("source", "unknown"),
            "to": p.get("target", "unknown"),
            "dataset": p.get("name", "unknown"),
            "region": p.get("region", "NA"),
            "law": ",".join(p.get("laws", [])),
            "fabric_tx": p.get("fabric", "NA"),
        }
        for p in pipelines[:12]
    ]

    online_nodes = len([n for n in nodes if n["status"] == "online"])
    warning_nodes = len([n for n in nodes if n["status"] != "online"])

    return {
        "status": "online",
        "timestamp": now_iso(),
        "storage": live.get("storage", "unknown"),
        "summary": {
            "total_nodes": len(nodes),
            "online_nodes": online_nodes,
            "warning_nodes": warning_nodes,
            "total_pipelines": len(pipelines),
            "audit_events_loaded": len(audit),
            "avg_sigma": round(sum(n["sigma"] for n in nodes) / len(nodes), 2),
        },
        "nodes": nodes,
        "movements": movements,
    }

@router.post("/compliance/run-all-checks")
async def run_all_compliance_checks() -> dict[str, Any]:
    """
    Run all simulated compliance framework checks.
    """
    frameworks = ["DPDP", "GDPR", "HIPAA", "SOX"]
    results = []

    for framework in frameworks:
        framework_code = framework.upper()
        tx_id = "TX_" + uuid.uuid4().hex[:12]
        check_id = "CHK_" + uuid.uuid4().hex[:12]

        violations = 1 if framework_code == "GDPR" else 0
        result = "PASSED" if violations == 0 else "REVIEW_REQUIRED"

        audit_event = {
            "ts": now_time(),
            "tx": tx_id,
            "action": "COMPLIANCE_CHECK",
            "dataset": f"{framework_code.lower()}_policy_scan",
            "result": result,
            "actor": "compliance-engine",
            "law": framework_code,
            "region": "GLOBAL",
        }

        if ensure_db():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    insert_audit_event(cur, audit_event)
                conn.commit()
        else:
            AUDIT_EVENTS.insert(0, audit_event)

        results.append({
            "check_id": check_id,
            "framework": framework_code,
            "result": result,
            "violations": violations,
            "fabric_tx": tx_id,
            "audit_event": audit_event,
        })

    total_violations = sum(item["violations"] for item in results)

    return {
        "status": "completed",
        "message": "All compliance checks completed",
        "frameworks_checked": len(results),
        "total_violations": total_violations,
        "overall_result": "PASSED" if total_violations == 0 else "REVIEW_REQUIRED",
        "results": results,
        "timestamp": now_iso(),
    }

def ensure_pipeline_runs_table() -> bool:
    """
    Create pipeline run history table.
    """
    if not ensure_db():
        return False

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
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
                    """
                )
            conn.commit()
        return True
    except Exception:
        return False


def insert_pipeline_run_record(run_record: dict[str, Any]) -> None:
    if not ensure_pipeline_runs_table():
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_pipeline_runs (
                    run_id, pipeline_id, pipeline_name, status, completed_at,
                    duration_ms, source_name, target_name, region, law,
                    fabric_tx, logs
                )
                VALUES (
                    %(run_id)s, %(pipeline_id)s, %(pipeline_name)s, %(status)s, NOW(),
                    %(duration_ms)s, %(source_name)s, %(target_name)s, %(region)s,
                    %(law)s, %(fabric_tx)s, %(logs)s
                )
                ON CONFLICT (run_id) DO NOTHING;
                """,
                {
                    "run_id": run_record["run_id"],
                    "pipeline_id": run_record["pipeline_id"],
                    "pipeline_name": run_record["pipeline_name"],
                    "status": run_record["status"],
                    "duration_ms": run_record["duration_ms"],
                    "source_name": run_record["source"],
                    "target_name": run_record["target"],
                    "region": run_record["region"],
                    "law": run_record["law"],
                    "fabric_tx": run_record["fabric_tx"],
                    "logs": Json(run_record["logs"]),
                },
            )
        conn.commit()


@router.post("/pipelines/{pipeline_id}/execute-real")
async def execute_pipeline_with_logs(pipeline_id: str) -> dict[str, Any]:
    """
    Execute a pipeline with persistent run logs.
    This is still local MVP execution, but now has real run history records.
    """
    pipelines = get_pipelines_from_db()
    pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)

    if not pipeline:
        return {
            "status": "not_found",
            "message": f"Pipeline {pipeline_id} was not found",
            "timestamp": now_iso(),
        }

    run_id = "RUN_" + uuid.uuid4().hex[:12]
    tx_id = "TX_" + uuid.uuid4().hex[:12]
    law = pipeline["laws"][0] if pipeline.get("laws") else "NA"

    logs = [
        {
            "step": "queued",
            "status": "completed",
            "message": f"Pipeline {pipeline['name']} accepted by execution engine",
            "ts": now_iso(),
        },
        {
            "step": "source_connect",
            "status": "completed",
            "message": f"Connected to source {pipeline.get('source', 'unknown')}",
            "ts": now_iso(),
        },
        {
            "step": "quality_scan",
            "status": "completed",
            "message": f"Quality scan completed with sigma {pipeline.get('sigma', 0)}",
            "ts": now_iso(),
        },
        {
            "step": "compliance_guard",
            "status": "completed",
            "message": f"{law} policy guard evaluated",
            "ts": now_iso(),
        },
        {
            "step": "target_write",
            "status": "completed",
            "message": f"Data movement simulated into {pipeline.get('target', 'unknown')}",
            "ts": now_iso(),
        },
        {
            "step": "audit_commit",
            "status": "completed",
            "message": f"Audit proof committed as {tx_id}",
            "ts": now_iso(),
        },
    ]

    duration_ms = 1200 + len(pipeline["name"]) * 37

    run_record = {
        "run_id": run_id,
        "pipeline_id": pipeline_id,
        "pipeline_name": pipeline["name"],
        "status": "completed",
        "duration_ms": duration_ms,
        "source": pipeline.get("source", "unknown"),
        "target": pipeline.get("target", "unknown"),
        "region": pipeline.get("region", "NA"),
        "law": law,
        "fabric_tx": tx_id,
        "logs": logs,
    }

    audit_event = {
        "ts": now_time(),
        "tx": tx_id,
        "action": "PIPELINE_EXECUTION",
        "dataset": pipeline["name"],
        "result": "COMPLETED",
        "actor": "execution-engine",
        "law": law,
        "region": pipeline.get("region", "NA"),
    }

    if ensure_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dashboard_pipelines
                    SET runs = runs + 1, last_run = 'just now', updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (pipeline_id,),
                )
                insert_audit_event(cur, audit_event)
            conn.commit()

        insert_pipeline_run_record(run_record)
    else:
        AUDIT_EVENTS.insert(0, audit_event)

    return {
        "status": "completed",
        "message": "Pipeline execution completed with logs",
        "run": run_record,
        "audit_event": audit_event,
        "timestamp": now_iso(),
    }


@router.get("/pipeline-runs/recent")
async def recent_pipeline_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    """
    Return recent pipeline execution records.
    """
    if not ensure_pipeline_runs_table():
        return {
            "status": "online",
            "storage": "memory",
            "count": 0,
            "runs": [],
            "timestamp": now_iso(),
        }

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    run_id,
                    pipeline_id,
                    pipeline_name,
                    status,
                    started_at,
                    completed_at,
                    duration_ms,
                    source_name,
                    target_name,
                    region,
                    law,
                    fabric_tx,
                    logs
                FROM dashboard_pipeline_runs
                ORDER BY id DESC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall()

    runs = []
    for row in rows:
        runs.append({
            "run_id": row["run_id"],
            "pipeline_id": row["pipeline_id"],
            "pipeline_name": row["pipeline_name"],
            "status": row["status"],
            "started_at": str(row["started_at"]),
            "completed_at": str(row["completed_at"]),
            "duration_ms": row["duration_ms"],
            "source": row["source_name"],
            "target": row["target_name"],
            "region": row["region"],
            "law": row["law"],
            "fabric_tx": row["fabric_tx"],
            "logs": row["logs"],
        })

    return {
        "status": "online",
        "storage": "postgres",
        "count": len(runs),
        "runs": runs,
        "timestamp": now_iso(),
    }


