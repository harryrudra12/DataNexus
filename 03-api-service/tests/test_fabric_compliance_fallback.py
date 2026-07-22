"""Regression tests for compliance decisions when Fabric is unavailable."""

import pytest

from app.services.fabric import FabricService


def fallback_decision(
    *,
    target: str = "IN-MH",
    has_consent: bool = False,
    signature_count: int = 0,
) -> dict:
    return FabricService._fallback_compliance_decision(
        dataset_id="patient-records-test",
        target=target,
        jurisdictions=["DPDP_2023"],
        purpose="medical_treatment",
        has_consent=has_consent,
        signature_count=signature_count,
    )


def test_domestic_transfer_requires_consent_or_multisig():
    result = fallback_decision()

    assert result["decision"] == "BLOCKED"
    assert result["rules_evaluated"] == 1
    assert result["rules_passed"] == 0
    assert [violation["ruleId"] for violation in result["violations"]] == [
        "DPDP-002"
    ]
    assert "consent or multisig" in result["reason"].lower()


@pytest.mark.parametrize(
    ("has_consent", "signature_count"),
    [
        pytest.param(True, 0, id="consent-only"),
        pytest.param(False, 3, id="multisig-only"),
    ],
)
def test_domestic_transfer_accepts_either_approval(
    has_consent: bool,
    signature_count: int,
):
    result = fallback_decision(
        has_consent=has_consent,
        signature_count=signature_count,
    )

    assert result["decision"] == "ALLOWED"
    assert result["rules_evaluated"] == 1
    assert result["rules_passed"] == 1
    assert result["violations"] == []


def test_multisig_does_not_replace_cross_border_consent():
    result = fallback_decision(target="US", signature_count=3)

    assert result["decision"] == "BLOCKED"
    assert result["rules_passed"] == 0
    assert [violation["ruleId"] for violation in result["violations"]] == [
        "DPDP-001"
    ]
    assert "explicit consent" in result["reason"].lower()
