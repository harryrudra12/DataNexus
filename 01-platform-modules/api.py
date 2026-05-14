"""
DataNexus Era 3 — REST API
Single API gateway for all 6 Era 3 innovations.
FastAPI + async. Runs on port 8000.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio, hashlib, json, time, uuid
from typing import Optional, List
from dataclasses import asdict

# ── Minimal FastAPI-compatible implementation ─────────────────
# (In production install fastapi + uvicorn; shown here as plain HTTP)

from dna.data_dna import (
    DataDNAFactory, DataClassification, LegalJurisdiction, DataDNA
)
from nodes.living_node import DataNexusNode, NodeType, NodeCapability
from fabric.zero_gravity import ZeroGravityFabric
from compliance.conscious_compliance import ConsciousComplianceEngine, LawCode

# ── Singleton services (initialized at startup) ───────────────
class DataNexusAPI:

    def __init__(self):
        self.fabric     = ZeroGravityFabric("datanexus-prod-01")
        self.compliance = ConsciousComplianceEngine()
        self.nodes:     dict = {}
        self.dna_store: dict = {}   # dataset_id → DataDNA
        self._setup_demo_nodes()
        print("[API] DataNexus Era 3 API ready on :8000")

    def _setup_demo_nodes(self):
        regions = [
            ("dn-hyderabad-01", "IN-TG", NodeType.CORE_CLOUD,
             NodeCapability(32, 131072, 10_000_000)),
            ("dn-mumbai-01",    "IN-MH", NodeType.CORE_CLOUD,
             NodeCapability(32, 131072, 10_000_000)),
            ("dn-delhi-01",     "IN-DL", NodeType.CORE_CLOUD,
             NodeCapability(32, 131072, 10_000_000)),
        ]
        for nid, region, ntype, cap in regions:
            self.nodes[nid] = DataNexusNode(ntype, cap, region,
                                             ["dn-hyderabad-01"])
            self.fabric.register_node(nid, region, 50000.0, ntype.value)

    # ── ENDPOINTS ─────────────────────────────────────────────

    async def POST_ingest(self, body: dict) -> dict:
        """POST /api/v1/ingest — ingest data into fabric with DNA"""
        node_id = body.get("node_id", "dn-hyderabad-01")
        raw_data = body.get("data", "").encode()
        sigma = float(body.get("sigma", 5.0))
        dataset_name = body.get("name", "unnamed_dataset")
        creator_id = body.get("creator_id", "unknown")
        laws = [LegalJurisdiction(l) for l in
                body.get("laws", ["IN_DPDP_2023"])]
        allowed_regions = body.get("allowed_regions", ["IN"])

        # Create Data DNA
        dna = DataDNAFactory.create(
            dataset_name    = dataset_name,
            creator_id      = creator_id,
            raw_data        = raw_data,
            parent_ids      = [],
            transformation  = "raw_ingest",
            pipeline_id     = f"manual-ingest-{uuid.uuid4().hex[:6]}",
            sigma_level     = sigma,
            classification  = DataClassification.CONFIDENTIAL,
            jurisdictions   = laws,
            allowed_regions = allowed_regions,
            consent_purpose = body.get("purpose", "analytics"),
        )
        self.dna_store[dna.dataset_id] = dna

        # Put into zero gravity fabric
        node = self.nodes.get(node_id)
        if node:
            content_hash = await node.ingest(creator_id, raw_data,
                                              body.get("topic", "datanexus.raw"))
        else:
            content_hash = hashlib.sha256(raw_data).hexdigest()

        particle = self.fabric.put(raw_data, node_id, sigma)

        return {
            "status":        "ingested",
            "dataset_id":    dna.dataset_id,
            "content_hash":  content_hash,
            "ipfs_cid":      dna.ipfs_cid,
            "genome_hash":   dna.genome_hash,
            "sigma":         sigma,
            "fabric_nodes":  len(particle.home_nodes),
            "timestamp":     time.time(),
        }

    async def GET_dataset(self, dataset_id: str,
                           requester: str, region: str) -> dict:
        """GET /api/v1/dataset/{id} — retrieve dataset with DNA check"""
        dna = self.dna_store.get(dataset_id)
        if not dna:
            return {"error": "dataset_not_found", "id": dataset_id}

        # DNA access check
        ok, reason = dna.can_access(requester, "analytics")
        return {
            "dataset_id":   dataset_id,
            "dataset_name": dna.dataset_name,
            "access":       "ALLOWED" if ok else "DENIED",
            "reason":       reason,
            "sigma":        dna.quality.sigma_level,
            "genome_hash":  dna.genome_hash,
            "integrity_ok": dna.verify_integrity(),
            "ipfs_cid":     dna.ipfs_cid,
            "fabric_tx":    dna.fabric_tx_id,
        }

    async def POST_border_check(self, body: dict) -> dict:
        """POST /api/v1/compliance/border — check if transfer is allowed"""
        dataset_id = body.get("dataset_id", "")
        target     = body.get("target_country", "IN")
        purpose    = body.get("purpose", "analytics")
        laws       = [LawCode(l) for l in body.get("laws", ["IN_DPDP_2023"])]
        ctx        = body.get("context", {})

        allowed, reason, violations = self.compliance.check_transfer(
            dataset_id      = dataset_id,
            applicable_laws = laws,
            target_country  = target,
            transfer_purpose= purpose,
            context         = ctx,
        )
        return {
            "dataset_id":   dataset_id,
            "target":       target,
            "decision":     "ALLOWED" if allowed else "BLOCKED",
            "reason":       reason,
            "violations":   len(violations),
            "auto_fixes":   sum(1 for v in violations if v.get("auto_fixed")),
            "timestamp":    time.time(),
        }

    async def GET_compliance_report(self, dataset_id: str) -> dict:
        """GET /api/v1/compliance/report/{id}"""
        report_json = self.compliance.generate_compliance_report(dataset_id)
        return json.loads(report_json)

    async def POST_nlp_query(self, body: dict) -> dict:
        """POST /api/v1/query/nlp — ask data questions in any language"""
        text     = body.get("text", "")
        language = body.get("language", "en")
        tables   = body.get("tables", ["datanexus_default"])

        # Simple translation map
        translations = {
            "te": {
                "చివరి నెలలో అమ్మకాలు": "sales last month",
                "అత్యధిక ఆదాయం":        "highest revenue",
            },
            "hi": {
                "पिछले महीने की बिक्री": "sales last month",
            }
        }
        translated = text
        if language in translations:
            for native, eng in translations[language].items():
                translated = translated.replace(native, eng)

        # Generate SQL
        table = tables[0]
        if "sales" in translated.lower() and "month" in translated.lower():
            sql = f"""SELECT region, SUM(revenue) as total
FROM {table}
WHERE sale_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1' MONTH)
GROUP BY region ORDER BY total DESC"""
        else:
            sql = f"SELECT * FROM {table} LIMIT 100"

        return {
            "original_text": text,
            "language":      language,
            "translated":    translated,
            "sql":           sql,
            "table":         table,
            "status":        "ready_to_execute",
            "engine":        "presto",
        }

    async def GET_fabric_status(self) -> dict:
        """GET /api/v1/fabric/status"""
        status = self.fabric.fabric_status()
        status["nodes"] = {
            nid: {"region": n.region, "online": n.is_online,
                  "items": len(n.data_store)}
            for nid, n in self.nodes.items()
        }
        return status

    async def GET_health(self) -> dict:
        """GET /health"""
        return {
            "status":   "healthy",
            "version":  "3.0.0-era3",
            "fabric":   self.fabric.fabric_id,
            "nodes":    len(self.nodes),
            "datasets": len(self.dna_store),
            "uptime":   time.time(),
        }


# ── ROUTE TABLE ───────────────────────────────────────────────
ROUTES = {
    ("GET",  "/health"):                      "GET_health",
    ("POST", "/api/v1/ingest"):               "POST_ingest",
    ("GET",  "/api/v1/dataset/{id}"):         "GET_dataset",
    ("POST", "/api/v1/compliance/border"):    "POST_border_check",
    ("GET",  "/api/v1/compliance/report/{id}"):"GET_compliance_report",
    ("POST", "/api/v1/query/nlp"):            "POST_nlp_query",
    ("GET",  "/api/v1/fabric/status"):        "GET_fabric_status",
}


# ── DEMO ──────────────────────────────────────────────────────
async def demo():
    print("=== DataNexus Era 3 — API Demo ===\n")
    api = DataNexusAPI()

    print("\n--- POST /api/v1/ingest ---")
    result = await api.POST_ingest({
        "node_id":    "dn-hyderabad-01",
        "data":       "patient_id,age,bp\nP001,45,120\nP002,62,140",
        "name":       "patient_vitals_jan25",
        "creator_id": "apollo_hospital_hyd",
        "sigma":      5.8,
        "laws":       ["IN_DPDP_2023"],
        "allowed_regions": ["IN", "IN-TG"],
        "purpose":    "medical_treatment",
        "topic":      "datanexus.health.vitals",
    })
    dataset_id = result["dataset_id"]
    print(json.dumps(result, indent=2))

    print("\n--- GET /api/v1/dataset/{id} ---")
    r2 = await api.GET_dataset(dataset_id, "apollo_hospital_hyd", "IN-TG")
    print(json.dumps(r2, indent=2))

    print("\n--- POST /api/v1/compliance/border ---")
    r3 = await api.POST_border_check({
        "dataset_id":    dataset_id,
        "target_country":"US",
        "purpose":       "pharma_research",
        "laws":          ["IN_DPDP_2023"],
        "context":       {"has_consent": False, "fabric_tx_id": "TX_123"},
    })
    print(json.dumps(r3, indent=2))

    print("\n--- POST /api/v1/query/nlp (Telugu) ---")
    r4 = await api.POST_nlp_query({
        "text":     "చివరి నెలలో అత్యధిక అమ్మకాలు ఏ ప్రాంతంలో?",
        "language": "te",
        "tables":   ["patient_vitals"],
    })
    print(json.dumps(r4, indent=2))

    print("\n--- GET /api/v1/fabric/status ---")
    r5 = await api.GET_fabric_status()
    print(json.dumps(r5, indent=2))

    print("\n--- GET /health ---")
    r6 = await api.GET_health()
    print(json.dumps(r6, indent=2))

    print(f"\n--- Available API routes ---")
    for (method, path), handler in ROUTES.items():
        print(f"  {method:6s} {path}")

if __name__ == "__main__":
    asyncio.run(demo())
