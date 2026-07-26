"""Regression tests for fail-closed compliance enforcement."""

from compliance.conscious_compliance import (
    ConsciousComplianceEngine,
    LawCode,
)


def test_dpdp_transfer_without_fabric_proof_is_quarantined():
    engine = ConsciousComplianceEngine()

    allowed, reason, violations = engine.check_transfer(
        dataset_id="ds-missing-proof",
        applicable_laws=[LawCode.IN_DPDP_2023],
        target_country="IN",
        transfer_purpose="medical_treatment",
        context={
            "has_consent": True,
            "fabric_tx_id": "",
        },
    )

    assert allowed is False
    assert [violation["rule_id"] for violation in violations] == ["DPDP-003"]
    assert violations[0]["auto_fixed"] is True
    assert "DPDP-003" in reason
    assert engine.violation_log[0]["rule_id"] == "DPDP-003"
    assert engine.audit_trail[0]["decision"] == "BLOCKED"


def test_hipaa_transfer_with_unencrypted_phi_is_blocked():
    engine = ConsciousComplianceEngine()

    allowed, reason, violations = engine.check_transfer(
        dataset_id="ds-unencrypted-phi",
        applicable_laws=[LawCode.US_HIPAA],
        target_country="US",
        transfer_purpose="medical_treatment",
        context={
            "data_props": {
                "encrypted_at_rest": False,
                "encrypted_in_transit": True,
            },
        },
    )

    assert allowed is False
    assert [violation["rule_id"] for violation in violations] == ["HIPAA-001"]
    assert violations[0]["auto_fixed"] is True
    assert "HIPAA-001" in reason
    assert engine.violation_log[0]["rule_id"] == "HIPAA-001"
    assert engine.audit_trail[0]["decision"] == "BLOCKED"
