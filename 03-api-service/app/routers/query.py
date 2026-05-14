"""
DataNexus Era 3 — NLP Query Router
Translates Telugu, Hindi, Tamil, English to Presto SQL.
"""
import re
import time
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from ..core.auth import CurrentUser, Permission, require_permission
from ..core.logging import get_logger
from ..models.schemas import NLPQueryRequest, NLPQueryResponse

router = APIRouter(prefix="/api/v1", tags=["query"])
logger = get_logger(__name__)


# ─── Translation map (LLM in production) ──────────────────────
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "te": {  # Telugu
        "చివరి నెలలో":          "last month",
        "అమ్మకాలు":               "sales",
        "అత్యధిక":                 "highest",
        "ఆదాయం":                   "revenue",
        "ఏ ప్రాంతంలో":             "in which region",
        "నాణ్యత":                   "quality",
        "నివేదిక":                  "report",
        "పైప్‌లైన్":                 "pipeline",
        "ఈ వారం":                  "this week",
        "ప్రాంతం వారీగా":          "by region",
        "ఎగువ":                     "top",
        "క్రింది":                  "below",
    },
    "hi": {  # Hindi
        "पिछले महीने":             "last month",
        "बिक्री":                    "sales",
        "सर्वोच्च":                  "highest",
        "राजस्व":                    "revenue",
        "किस क्षेत्र में":            "in which region",
        "गुणवत्ता":                  "quality",
        "रिपोर्ट":                   "report",
        "इस सप्ताह":                "this week",
        "क्षेत्र के अनुसार":          "by region",
        "शीर्ष":                     "top",
    },
}


def translate(text: str, language: str) -> str:
    """Replace native phrases with English equivalents."""
    if language == "en":
        return text
    if language not in TRANSLATIONS:
        return text
    out = text
    for native, english in TRANSLATIONS[language].items():
        out = out.replace(native, english)
    return out


def detect_language(text: str) -> str:
    """Auto-detect language from Unicode ranges."""
    if any("\u0c00" <= c <= "\u0c7f" for c in text):  # Telugu
        return "te"
    if any("\u0900" <= c <= "\u097f" for c in text):  # Devanagari (Hindi/Marathi)
        return "hi"
    if any("\u0b80" <= c <= "\u0bff" for c in text):  # Tamil
        return "ta"
    return "en"


def text_to_sql(translated: str, table: str, limit: int = 100) -> str:
    """Convert English natural language to Presto SQL.
    Production version uses an LLM with schema context."""
    t = translated.lower()
    safe_table = re.sub(r"[^a-z0-9_]", "", table)

    # Pattern 1: "top regions by revenue" / "highest revenue by region"
    if ("top" in t or "highest" in t) and "region" in t:
        period = "last month" if "last month" in t else "this month"
        date_filter = (
            "WHERE sale_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1' MONTH) "
            "AND sale_date < DATE_TRUNC('month', CURRENT_DATE)"
            if period == "last month" else
            "WHERE sale_date >= DATE_TRUNC('month', CURRENT_DATE)"
        )
        return (
            f"SELECT region, SUM(revenue) AS total_revenue\n"
            f"FROM {safe_table}\n{date_filter}\n"
            f"GROUP BY region\nORDER BY total_revenue DESC\nLIMIT {limit}"
        )

    # Pattern 2: "pipelines below 4.5 sigma"
    if "sigma" in t or "quality" in t:
        m = re.search(r"(\d\.?\d*)", t)
        threshold = m.group(1) if m else "4.5"
        return (
            f"SELECT pipeline_id, AVG(sigma_level) AS avg_sigma, COUNT(*) AS runs\n"
            f"FROM datanexus_quality_log\n"
            f"GROUP BY pipeline_id\n"
            f"HAVING AVG(sigma_level) < {threshold}\n"
            f"ORDER BY avg_sigma ASC\nLIMIT {limit}"
        )

    # Pattern 3: "sales last month"
    if "sales" in t or "revenue" in t:
        return (
            f"SELECT DATE_TRUNC('day', sale_date) AS day, SUM(revenue) AS revenue\n"
            f"FROM {safe_table}\n"
            f"WHERE sale_date >= CURRENT_DATE - INTERVAL '30' DAY\n"
            f"GROUP BY DATE_TRUNC('day', sale_date)\n"
            f"ORDER BY day DESC\nLIMIT {limit}"
        )

    # Default: scan with limit
    return f"SELECT *\nFROM {safe_table}\nLIMIT {limit}"


def execute_demo(sql: str) -> List[Dict[str, Any]]:
    """Demo result generator. Production calls Presto via prestodb client."""
    if "region" in sql and "total_revenue" in sql:
        return [
            {"region": "Hyderabad",  "total_revenue": 4_580_000},
            {"region": "Mumbai",     "total_revenue": 3_920_000},
            {"region": "Delhi",      "total_revenue": 3_140_000},
            {"region": "Bangalore",  "total_revenue": 2_780_000},
            {"region": "Chennai",    "total_revenue": 2_410_000},
        ]
    if "sigma_level" in sql:
        return [
            {"pipeline_id": "iot_factory_sensors", "avg_sigma": 4.32, "runs": 4502},
            {"pipeline_id": "legacy_etl_jobs",     "avg_sigma": 3.91, "runs": 312},
        ]
    if "sale_date" in sql:
        return [
            {"day": "2025-05-05", "revenue": 487_300},
            {"day": "2025-05-04", "revenue": 512_100},
            {"day": "2025-05-03", "revenue": 463_800},
        ]
    return []


@router.post("/query/nlp",
             response_model=NLPQueryResponse,
             summary="Ask the data anything in any Indian language")
async def nlp_query(
    body: NLPQueryRequest,
    user: CurrentUser = Depends(require_permission(Permission.QUERY_DATA)),
) -> NLPQueryResponse:
    start = time.time()
    log = logger.bind(user_id=user.user_id, language=body.language)

    # Auto-detect language if requested
    language = detect_language(body.text) if body.language == "auto" else body.language

    # Translate to English
    translated = translate(body.text, language)

    # Generate SQL
    table = body.tables[0]
    sql = text_to_sql(translated, table, body.limit)

    log.info("nlp_query_translated",
             original=body.text[:64], translated=translated[:64],
             detected_lang=language)

    # Execute (demo mode returns sample data)
    rows: List[Dict[str, Any]] | None = None
    row_count = None
    if body.execute:
        rows = execute_demo(sql)
        row_count = len(rows)

    elapsed_ms = int((time.time() - start) * 1000)

    return NLPQueryResponse(
        original_text = body.text,
        language      = language,
        translated    = translated,
        sql           = sql,
        table         = table,
        engine        = "presto",
        status        = "executed" if body.execute else "translated",
        rows          = rows,
        row_count     = row_count,
        elapsed_ms    = elapsed_ms,
    )
