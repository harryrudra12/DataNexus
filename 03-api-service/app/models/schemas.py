"""
DataNexus Era 3 — API Schemas
Pydantic models for request validation and response serialization.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ─── Enums ────────────────────────────────────────────────────
class Classification(str, Enum):
    PUBLIC       = "PUBLIC"
    INTERNAL     = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    PII          = "PII"
    HEALTH       = "HEALTH"
    FINANCIAL    = "FINANCIAL"
    BIOMETRIC    = "BIOMETRIC"


class Jurisdiction(str, Enum):
    DPDP_2023 = "DPDP_2023"
    GDPR      = "GDPR"
    HIPAA     = "HIPAA"
    SOX       = "SOX"
    PCI_DSS   = "PCI_DSS"


class TransformationType(str, Enum):
    INGEST           = "INGEST"
    SPARK_TRANSFORM  = "SPARK_TRANSFORM"
    SPARK_PII_MASKING = "SPARK_PII_MASKING"
    SPARK_JOIN       = "SPARK_JOIN"
    SQL_QUERY        = "SQL_QUERY"
    ML_TRAIN         = "ML_TRAIN"
    ML_INFER         = "ML_INFER"
    EXPORT           = "EXPORT"


# ─── Common ───────────────────────────────────────────────────
class ErrorResponse(BaseModel):
    error:      str
    detail:     Optional[str] = None
    request_id: Optional[str] = None
    timestamp:  datetime = Field(default_factory=datetime.utcnow)


class PaginatedResponse(BaseModel):
    items:      List[Any]
    total:      int
    page:       int = 1
    page_size:  int = 50
    has_next:   bool = False


# ─── Health & status ──────────────────────────────────────────
class HealthCheck(BaseModel):
    status:       str  # "healthy" | "degraded" | "unhealthy"
    version:      str
    environment:  str
    checks:       Dict[str, Dict[str, Any]]
    timestamp:    datetime = Field(default_factory=datetime.utcnow)


# ─── Auth ─────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username:  str = Field(..., min_length=3, max_length=64)
    password:  str = Field(..., min_length=8, max_length=256)
    tenant_id: Optional[str] = None


# ─── Ingest ───────────────────────────────────────────────────
class IngestRequest(BaseModel):
    """Request to ingest data into DataNexus."""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "dataset_name": "patient_vitals_jan_2025",
            "data": "patient_id,age,bp\nP001,45,120\nP002,62,140",
            "data_format": "csv",
            "classification": "HEALTH",
            "jurisdictions": ["DPDP_2023", "HIPAA"],
            "allowed_regions": ["IN", "IN-TG"],
            "purpose": "medical_treatment",
            "pipeline_id": "patient_daily_pipeline",
            "node_id": "dn-hyderabad-01",
            "topic": "datanexus.health.vitals",
        }
    })

    dataset_name:    str = Field(..., min_length=3, max_length=128, pattern=r"^[a-z0-9_]+$")
    data:            str = Field(..., min_length=1, max_length=10_000_000)
    data_format:     str = Field(default="csv", pattern=r"^(csv|json|parquet|avro)$")
    classification:  Classification
    jurisdictions:   List[Jurisdiction] = Field(..., min_length=1)
    allowed_regions: List[str] = Field(..., min_length=1)
    purpose:         str = Field(..., min_length=3, max_length=128)
    pipeline_id:     Optional[str] = None
    node_id:         str = "dn-hyderabad-01"
    topic:           str = "datanexus.raw.ingest"
    tags:            List[str] = Field(default_factory=list, max_length=20)

    @field_validator("allowed_regions")
    @classmethod
    def validate_regions(cls, v: List[str]) -> List[str]:
        for region in v:
            if not region or len(region) > 16:
                raise ValueError(f"Invalid region: {region}")
        return v


class IngestResponse(BaseModel):
    status:        str = "ingested"
    dataset_id:    str
    content_hash:  str
    ipfs_cid:      str
    genome_hash:   str
    fabric_tx_id:  str
    sigma:         float
    region:        str
    fabric_nodes:  int
    timestamp:     datetime


# ─── Dataset ──────────────────────────────────────────────────
class DatasetResponse(BaseModel):
    dataset_id:     str
    dataset_name:   str
    classification: Classification
    jurisdictions:  List[Jurisdiction]
    sigma:          float
    genome_hash:    str
    integrity_ok:   bool
    ipfs_cid:       str
    fabric_tx:      str
    creator_id:     str
    created_at:     datetime
    parent_ids:     List[str] = Field(default_factory=list)


# ─── Lineage ──────────────────────────────────────────────────
class LineageRecord(BaseModel):
    tx_id:                str
    timestamp:            datetime
    output_dataset_id:    str
    output_hash:          str
    transformation_type:  str
    pipeline_id:          str
    sigma_level:          float
    classification:       str
    region:               str
    operator_msp:         str


class LineageResponse(BaseModel):
    dataset_id:  str
    records:     List[LineageRecord]
    total:       int
    integrity:   bool


# ─── Compliance ───────────────────────────────────────────────
class BorderCheckRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "dataset_id": "patient_records_curated",
            "target_country": "US",
            "purpose": "pharma_research",
            "jurisdictions": ["DPDP_2023"],
            "has_consent": False,
            "signature_count": 0,
        }
    })
    dataset_id:      str
    target_country:  str
    purpose:         str
    jurisdictions:   List[Jurisdiction]
    classification:  Classification = Classification.PII
    has_consent:     bool = False
    consent_id:      Optional[str] = None
    signature_count: int = Field(default=0, ge=0, le=10)


class ViolationDetail(BaseModel):
    rule_id:     str
    law:         str
    law_section: str
    description: str
    penalty:     str
    auto_fixed:  bool


class BorderCheckResponse(BaseModel):
    decision_id:        str
    dataset_id:         str
    target:             str
    decision:           str   # ALLOWED | BLOCKED | ALLOWED_WITH_FIX
    reason:             str
    rules_evaluated:    int
    rules_passed:       int
    violations:         List[ViolationDetail] = Field(default_factory=list)
    auto_fixes_applied: List[str] = Field(default_factory=list)
    fabric_tx_id:       str
    timestamp:          datetime


class ComplianceReport(BaseModel):
    report_id:        str
    dataset_id:       str
    generated_at:     datetime
    total_decisions:  int
    allowed:          int
    blocked:          int
    auto_fixed:       int
    compliance_rate:  float
    blockchain_proof: str
    recent_decisions: List[BorderCheckResponse]


# ─── Quality / Six Sigma ──────────────────────────────────────
class QualityMeasurement(BaseModel):
    pipeline_id:        str
    dataset_id:         str
    run_id:             str
    sigma_level:        float = Field(..., ge=1.0, le=6.0)
    completeness_pct:   float = Field(..., ge=0, le=100)
    accuracy_pct:       float = Field(..., ge=0, le=100)
    records_processed:  int = Field(..., ge=0)
    records_failed:     int = Field(..., ge=0)
    expectations_run:   int = Field(default=0, ge=0)
    expectations_passed: int = Field(default=0, ge=0)
    region:             str = "IN-TG"
    node_id:            str = "dn-hyderabad-01"


class SigmaTrendPoint(BaseModel):
    timestamp:   datetime
    sigma_level: float
    run_id:      str


class PipelineStatus(BaseModel):
    pipeline_id:       str
    status:            str   # healthy | warning | critical
    current_sigma:     float
    avg_sigma_24h:     float
    last_run:          datetime
    runs_today:        int
    heal_rate:         float
    sla_target:        float
    sla_met:           bool


# ─── NLP Query ────────────────────────────────────────────────
class NLPQueryRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "text": "చివరి నెలలో అత్యధిక అమ్మకాలు ఏ ప్రాంతంలో?",
            "language": "te",
            "tables": ["sales_transactions"],
        }
    })
    text:     str = Field(..., min_length=2, max_length=2000)
    language: str = Field(default="auto", pattern=r"^(auto|en|te|hi|ta|kn|ml|bn|mr)$")
    tables:   List[str] = Field(..., min_length=1, max_length=10)
    execute:  bool = Field(default=True, description="Run the SQL or just translate?")
    limit:    int = Field(default=100, ge=1, le=10000)


class NLPQueryResponse(BaseModel):
    original_text: str
    language:      str
    translated:    str
    sql:           str
    table:         str
    engine:        str = "presto"
    status:        str
    rows:          Optional[List[Dict[str, Any]]] = None
    row_count:     Optional[int] = None
    elapsed_ms:    Optional[int] = None


# ─── Fabric ───────────────────────────────────────────────────
class FabricNode(BaseModel):
    node_id:    str
    region:     str
    node_type:  str
    online:     bool
    items:      int
    avg_sigma:  float


class FabricStatus(BaseModel):
    fabric_id:        str
    total_datasets:   int
    total_nodes:      int
    online_nodes:     int
    avg_sigma:        float
    total_movements:  int
    nodes:            List[FabricNode]


# ─── Pipeline intent (AI OS) ──────────────────────────────────
class IntentRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "intent": "Send daily sales reports for top 5 regions every morning at 6am",
            "language": "en",
            "tables": ["sales_transactions"],
        }
    })
    intent:   str = Field(..., min_length=10, max_length=500)
    language: str = "en"
    tables:   List[str] = Field(default_factory=list)


class IntentResponse(BaseModel):
    pipeline_id:       str
    intent_id:         str
    intent_type:       str
    schedule:          str
    sql:               Optional[str] = None
    sigma_target:      float
    auto_heal:         bool = True
    blockchain_logged: bool = True
    status:            str = "DEPLOYED"
    dag_url:           Optional[str] = None
