"""
DataNexus Era 3 — pytest conftest
Shared fixtures for Era 3 module tests.
"""
import sys
from pathlib import Path

# Add era3 root to path so tests can import the modules
PROJECT_ROOT = Path(__file__).parent.parent
MODULE_ROOT = PROJECT_ROOT / "01-platform-modules"
API_ROOT = PROJECT_ROOT / "03-api-service"
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(API_ROOT))

import pytest


@pytest.fixture
def sample_patient_data() -> bytes:
    """Realistic test data for ingestion tests."""
    return (
        b"patient_id,age,bp,diagnosis\n"
        b"P001,45,120/80,hypertension\n"
        b"P002,62,140/90,diabetes\n"
        b"P003,38,118/75,healthy\n"
    )


@pytest.fixture
def sample_factory_data() -> bytes:
    return (
        b"timestamp,sensor_id,temp,pressure\n"
        b"2025-05-07T08:00:00Z,S001,72.3,1.8\n"
        b"2025-05-07T08:01:00Z,S001,73.1,1.9\n"
        b"2025-05-07T08:02:00Z,S002,71.8,1.7\n"
    )


@pytest.fixture
def sample_sales_data() -> bytes:
    return (
        b"order_id,amount,region,date\n"
        b"O001,45000,Hyderabad,2025-05-01\n"
        b"O002,82000,Mumbai,2025-05-02\n"
        b"O003,31000,Delhi,2025-05-03\n"
    )
