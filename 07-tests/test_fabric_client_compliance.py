"""Regression tests for the Fabric client's simulated compliance decisions."""

import pytest

from fabric_client import DataNexusFabricClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_region", "signature_count", "expected_decision"),
    [
        ("IN-TG", 0, "ALLOWED"),
        ("IN-MH", 2, "BLOCKED"),
        ("IN-MH", 3, "ALLOWED"),
    ],
)
async def test_dpdp_cross_region_transfer_requires_three_signatures(
    target_region,
    signature_count,
    expected_decision,
):
    client = DataNexusFabricClient()

    decision = await client.check_transfer(
        dataset_id="dpdp-signature-boundary",
        classification="PII",
        jurisdictions=["DPDP_2023"],
        target_region=target_region,
        purpose="analytics",
        has_consent=True,
        signature_count=signature_count,
    )

    assert decision.decision == expected_decision
    violation_ids = {violation["ruleId"] for violation in decision.violations}
    assert ("DPDP-004" in violation_ids) is (expected_decision == "BLOCKED")
