"""
DataNexus Era 3 — Data DNA tests
Verifies cryptographic genome, border autonomy, integrity verification.
"""
import pytest
from dna.data_dna import (
    DataDNAFactory, DataClassification, LegalJurisdiction,
)


class TestDataDNACreation:
    def test_creates_valid_dna(self, sample_patient_data):
        dna = DataDNAFactory.create(
            dataset_name    = "patient_records_test",
            creator_id      = "apollo_hyd",
            raw_data        = sample_patient_data,
            parent_ids      = [],
            transformation  = "raw_ingest",
            pipeline_id     = "test-pipeline",
            sigma_level     = 5.8,
            classification  = DataClassification.HEALTH,
            jurisdictions   = [LegalJurisdiction.INDIA_DPDP],
            allowed_regions = ["IN", "IN-TG"],
            consent_purpose = "medical_treatment",
        )
        assert dna.dataset_id
        assert dna.genome_hash
        assert len(dna.genome_hash) == 64  # SHA-256 hex
        assert dna.quality.sigma_level == 5.8
        assert DataClassification.HEALTH == dna.classification

    def test_genome_hash_is_deterministic(self, sample_patient_data):
        """Same inputs → same genome hash (until time-based field changes)."""
        common = dict(
            dataset_name    = "test",
            creator_id      = "alice",
            raw_data        = sample_patient_data,
            parent_ids      = [],
            transformation  = "ingest",
            pipeline_id     = "p1",
            sigma_level     = 5.5,
            classification  = DataClassification.PII,
            jurisdictions   = [LegalJurisdiction.INDIA_DPDP],
            allowed_regions = ["IN"],
            consent_purpose = "analytics",
        )
        dna1 = DataDNAFactory.create(**common)
        # Same data → same content_hash
        dna2 = DataDNAFactory.create(**common)
        assert dna1.content_hash == dna2.content_hash


class TestIntegrityVerification:
    def test_unmodified_dna_verifies(self, sample_patient_data):
        dna = DataDNAFactory.create(
            dataset_name="test", creator_id="alice",
            raw_data=sample_patient_data, parent_ids=[],
            transformation="ingest", pipeline_id="p1",
            sigma_level=5.5,
            classification=DataClassification.PII,
            jurisdictions=[LegalJurisdiction.INDIA_DPDP],
            allowed_regions=["IN"], consent_purpose="analytics",
        )
        assert dna.verify_integrity() is True

    def test_tampered_dna_fails_verification(self, sample_patient_data):
        dna = DataDNAFactory.create(
            dataset_name="test", creator_id="alice",
            raw_data=sample_patient_data, parent_ids=[],
            transformation="ingest", pipeline_id="p1",
            sigma_level=5.5,
            classification=DataClassification.PII,
            jurisdictions=[LegalJurisdiction.INDIA_DPDP],
            allowed_regions=["IN"], consent_purpose="analytics",
        )
        # Simulate tampering — change the creator
        dna.creator_id = "attacker"
        assert dna.verify_integrity() is False


class TestBorderAutonomy:
    def _make_dpdp_dna(self, raw_data):
        return DataDNAFactory.create(
            dataset_name="patient", creator_id="apollo_hyd",
            raw_data=raw_data, parent_ids=[],
            transformation="ingest", pipeline_id="patient_p1",
            sigma_level=5.9,
            classification=DataClassification.HEALTH,
            jurisdictions=[LegalJurisdiction.INDIA_DPDP],
            allowed_regions=["IN", "IN-TG"],
            consent_purpose="medical_treatment",
        )

    def test_dpdp_blocks_us_transfer(self, sample_patient_data):
        dna = self._make_dpdp_dna(sample_patient_data)
        allowed, reason = dna.can_cross_border("US")
        assert allowed is False
        assert "DPDP" in reason

    def test_dpdp_allows_within_india(self, sample_patient_data):
        dna = self._make_dpdp_dna(sample_patient_data)
        allowed, reason = dna.can_cross_border("IN-TG")
        assert allowed is True

    def test_dpdp_blocks_unspecified_indian_region(self, sample_patient_data):
        dna = self._make_dpdp_dna(sample_patient_data)
        # IN-MH not in allowed_regions
        allowed, reason = dna.can_cross_border("IN-MH")
        assert allowed is False


class TestAccessControl:
    def test_owner_access_allowed(self, sample_patient_data):
        dna = DataDNAFactory.create(
            dataset_name="patient", creator_id="apollo_hyd",
            raw_data=sample_patient_data, parent_ids=[],
            transformation="ingest", pipeline_id="p1",
            sigma_level=5.9,
            classification=DataClassification.HEALTH,
            jurisdictions=[LegalJurisdiction.INDIA_DPDP],
            allowed_regions=["IN"], consent_purpose="medical_treatment",
        )
        allowed, _ = dna.can_access("apollo_hyd", "medical_treatment")
        assert allowed is True

    def test_purpose_mismatch_blocked(self, sample_patient_data):
        dna = DataDNAFactory.create(
            dataset_name="patient", creator_id="apollo_hyd",
            raw_data=sample_patient_data, parent_ids=[],
            transformation="ingest", pipeline_id="p1",
            sigma_level=5.9,
            classification=DataClassification.HEALTH,
            jurisdictions=[LegalJurisdiction.INDIA_DPDP],
            allowed_regions=["IN"], consent_purpose="medical_treatment",
        )
        allowed, reason = dna.can_access("pharma_corp", "drug_marketing")
        assert allowed is False
        assert "purpose" in reason.lower() or "consent" in reason.lower()
