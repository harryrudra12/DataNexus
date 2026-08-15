import pytest

from app.routers.query import detect_language, text_to_sql, translate


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("show sales", "en"),
        ("అమ్మకాలు", "te"),
        ("बिक्री", "hi"),
        ("விற்பனை", "ta"),
    ],
)
def test_detect_language_recognizes_supported_scripts(text, expected):
    assert detect_language(text) == expected


def test_translation_drives_last_month_revenue_query():
    translated = translate(
        "చివరి నెలలో అత్యధిక అమ్మకాలు ఏ ప్రాంతంలో",
        "te",
    )

    sql = text_to_sql(translated, "sales_transactions", limit=25)

    assert translated == "last month highest sales in which region"
    assert "FROM sales_transactions" in sql
    assert "CURRENT_DATE - INTERVAL '1' MONTH" in sql
    assert "GROUP BY region" in sql
    assert sql.endswith("LIMIT 25")


def test_quality_query_uses_only_numeric_threshold():
    sql = text_to_sql(
        "show quality below 3.75; drop table audit_log",
        "ignored_for_quality_queries",
        limit=10,
    )

    assert "FROM datanexus_quality_log" in sql
    assert "HAVING AVG(sigma_level) < 3.75" in sql
    assert "drop table" not in sql.lower()
    assert sql.endswith("LIMIT 10")


def test_default_query_sanitizes_untrusted_table_identifier():
    sql = text_to_sql(
        "show all records",
        "sales; drop table audit_log --",
        limit=50,
    )

    assert sql == "SELECT *\nFROM salesdroptableaudit_log\nLIMIT 50"
    assert ";" not in sql
    assert "--" not in sql
