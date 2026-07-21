"""Pure PII masking and quality-scoring helpers for the Spark masking job."""


def mask_aadhaar(value):
    """Mask Aadhaar: keep last 4 digits, replace rest with X."""
    if value is None or len(str(value)) < 4:
        return None
    normalized = str(value).replace(" ", "").replace("-", "")
    if len(normalized) != 12 or not normalized.isdigit():
        return "INVALID_AADHAAR"
    return "XXXX-XXXX-" + normalized[-4:]


def mask_phone(value):
    """Mask phone: keep last 4 digits, replace rest with X."""
    if value is None:
        return None
    normalized = str(value).replace("+", "").replace("-", "").replace(" ", "")
    if len(normalized) < 8:
        return "INVALID_PHONE"
    return "X" * (len(normalized) - 4) + normalized[-4:]


def mask_email(value):
    """Mask email: keep first letter and domain."""
    if value is None or "@" not in str(value):
        return None
    local, domain = str(value).split("@", 1)
    if len(local) <= 1:
        return "*@" + domain
    return local[0] + "***@" + domain


def mask_name(value):
    """Mask name: keep initials only."""
    if value is None:
        return None
    parts = str(value).split()
    return ". ".join(part[0].upper() for part in parts if part) + "."


def sigma_from_pass_rate(pass_rate: float) -> float:
    """Convert a quality-check pass rate to the pipeline's Six Sigma score."""
    if pass_rate >= 0.99999966:
        return 6.0
    if pass_rate >= 0.99999:
        return 5.5
    if pass_rate >= 0.99977:
        return 5.0
    if pass_rate >= 0.99865:
        return 4.5
    if pass_rate >= 0.99379:
        return 4.0
    if pass_rate >= 0.97725:
        return 3.5
    if pass_rate >= 0.93319:
        return 3.0
    return 2.0
