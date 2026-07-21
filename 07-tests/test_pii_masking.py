"""Regression tests for PII redaction and the masking quality gate."""

import sys
from pathlib import Path

import pytest

DATA_LAYER_ROOT = Path(__file__).parent.parent / "05-data-layer"
sys.path.insert(0, str(DATA_LAYER_ROOT))

from pii_masking import (  # noqa: E402
    mask_aadhaar,
    mask_email,
    mask_name,
    mask_phone,
    sigma_from_pass_rate,
)


@pytest.mark.parametrize(
    ("raw_value", "masked_value"),
    [
        ("1234 5678 9012", "XXXX-XXXX-9012"),
        ("1234-5678-9012", "XXXX-XXXX-9012"),
        ("12345678901X", "INVALID_AADHAAR"),
        ("123456789", "INVALID_AADHAAR"),
        (None, None),
    ],
)
def test_mask_aadhaar_never_returns_a_complete_identifier(raw_value, masked_value):
    assert mask_aadhaar(raw_value) == masked_value


def test_mask_phone_removes_formatting_and_exposes_only_last_four_digits():
    masked = mask_phone("+91-98765-43210")

    assert masked == "XXXXXXXX3210"
    assert "98765" not in masked
    assert mask_phone("1234567") == "INVALID_PHONE"


@pytest.mark.parametrize(
    ("raw_value", "masked_value"),
    [
        ("ravi@apollo.com", "r***@apollo.com"),
        ("r@apollo.com", "*@apollo.com"),
        ("not-an-email", None),
        (None, None),
    ],
)
def test_mask_email_preserves_domain_without_exposing_local_part(
    raw_value, masked_value
):
    assert mask_email(raw_value) == masked_value


def test_mask_name_reduces_each_component_to_an_initial():
    assert mask_name("Ravi Kumar Sharma") == "R. K. S."
    assert mask_name(None) is None


@pytest.mark.parametrize(
    ("pass_rate", "sigma"),
    [
        (0.99999966, 6.0),
        (0.99999, 5.5),
        (0.99977, 5.0),
        (0.99865, 4.5),
        (0.99379, 4.0),
        (0.97725, 3.5),
        (0.93319, 3.0),
        (0.93318, 2.0),
    ],
)
def test_sigma_thresholds_define_the_pipeline_quarantine_boundary(pass_rate, sigma):
    assert sigma_from_pass_rate(pass_rate) == sigma
