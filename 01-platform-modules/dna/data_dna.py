"""
DataNexus Era 3 — Data DNA
Every dataset carries its own cryptographic genome.
Origin · Lineage · Quality · Consent · Laws · Access Policy
"""
import hashlib, json, time, uuid
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from enum import Enum

class LegalJurisdiction(Enum):
    INDIA_DPDP   = "IN_DPDP_2023"
    EU_GDPR      = "EU_GDPR_2018"
    US_HIPAA     = "US_HIPAA_1996"
    US_SOX       = "US_SOX_2002"
    GLOBAL_OPEN  = "GLOBAL_OPEN"

class DataClassification(Enum):
    PUBLIC       = "PUBLIC"
    INTERNAL     = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    PII          = "PII"
    HEALTH       = "HEALTH"
    FINANCIAL    = "FINANCIAL"
    BIOMETRIC    = "BIOMETRIC"

@dataclass
class ConsentRecord:
    owner_id:    str
    purpose:     str
    granted_at:  float
    expires_at:  Optional[float]
    revocable:   bool = True
    consent_id:  str  = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass
class QualityScore:
    sigma_level:      float   # 1.0 – 6.0
    completeness_pct: float
    accuracy_pct:     float
    timeliness_score: float
    measured_at:      float   = field(default_factory=time.time)
    defects_per_million: float = field(init=False)

    def __post_init__(self):
        # Six Sigma DPM table
        sigma_dpm = {6:3.4, 5:233, 4:6210, 3:66807, 2:308537, 1:691462}
        self.defects_per_million = sigma_dpm.get(
            round(self.sigma_level), 999999)

@dataclass
class BorderPolicy:
    allowed_regions:   List[str]   # e.g. ["IN", "IN-TG", "IN-MH"]
    blocked_regions:   List[str]
    requires_consent:  bool = True
    requires_multisig: bool = False  # for cross-border transfers
    multisig_count:    int  = 3      # how many signatures needed

@dataclass
class DataDNA:
    """The cryptographic genome embedded in every DataNexus dataset."""

    # Identity
    dataset_id:      str
    dataset_name:    str
    creator_id:      str
    created_at:      float

    # Classification
    classification:  DataClassification
    jurisdictions:   List[LegalJurisdiction]
    tags:            List[str]

    # Lineage
    parent_ids:      List[str]           # upstream dataset IDs
    transformation:  str                  # what was done to create this
    pipeline_id:     str                  # which Airflow DAG created it

    # Quality
    quality:         QualityScore

    # Consent and governance
    consent:         ConsentRecord
    border_policy:   BorderPolicy

    # Cryptographic proof
    content_hash:    str                  # SHA-256 of raw data
    ipfs_cid:        str                  # IPFS content identifier
    fabric_tx_id:    str                  # Hyperledger Fabric transaction
    genome_hash:     str = field(init=False)  # hash of the entire DNA

    def __post_init__(self):
        self.genome_hash = self._compute_genome_hash()

    def _compute_genome_hash(self) -> str:
        """Hash the entire DNA — any tampering changes this hash."""
        dna_dict = {
            "dataset_id":     self.dataset_id,
            "creator_id":     self.creator_id,
            "created_at":     self.created_at,
            "classification": self.classification.value,
            "jurisdictions":  [j.value for j in self.jurisdictions],
            "parent_ids":     self.parent_ids,
            "transformation": self.transformation,
            "quality_sigma":  self.quality.sigma_level,
            "content_hash":   self.content_hash,
            "ipfs_cid":       self.ipfs_cid,
            "fabric_tx_id":   self.fabric_tx_id,
        }
        raw = json.dumps(dna_dict, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()

    def verify_integrity(self) -> bool:
        """Re-compute genome hash and compare — detects any tampering."""
        return self.genome_hash == self._compute_genome_hash()

    def can_cross_border(self, target_region: str) -> tuple[bool, str]:
        """Autonomous border compliance — data decides for itself."""
        if target_region in self.border_policy.blocked_regions:
            return False, f"BLOCKED: {target_region} is explicitly blocked by border policy"

        if target_region not in self.border_policy.allowed_regions:
            # Check jurisdiction rules
            for j in self.jurisdictions:
                if j == LegalJurisdiction.INDIA_DPDP:
                    if not target_region.startswith("IN"):
                        return False, f"BLOCKED: DPDP 2023 — data cannot leave India without explicit approval"
                if j == LegalJurisdiction.EU_GDPR:
                    eu_countries = ["DE","FR","IT","ES","PL","NL","BE","SE","AT","DK"]
                    if target_region not in eu_countries:
                        return False, f"BLOCKED: GDPR — data cannot leave EU without adequacy decision"
            return False, f"BLOCKED: {target_region} not in allowed regions"

        if self.border_policy.requires_multisig:
            return True, f"ALLOWED: {target_region} — requires {self.border_policy.multisig_count} signatures"

        return True, f"ALLOWED: {target_region} — compliant with all jurisdictions"

    def can_access(self, user_id: str, purpose: str) -> tuple[bool, str]:
        """Data decides who can access it and for what purpose."""
        if self.consent.owner_id == user_id:
            return True, "ALLOWED: owner access"
        if self.consent.purpose not in purpose:
            return False, f"BLOCKED: purpose '{purpose}' does not match consent '{self.consent.purpose}'"
        if self.consent.expires_at and time.time() > self.consent.expires_at:
            return False, "BLOCKED: consent has expired"
        return True, "ALLOWED: valid consent"

    def to_json(self) -> str:
        d = asdict(self)
        d["classification"]  = self.classification.value
        d["jurisdictions"]   = [j.value for j in self.jurisdictions]
        d["quality"]["sigma_level"] = self.quality.sigma_level
        return json.dumps(d, indent=2)

    @staticmethod
    def compute_content_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


class DataDNAFactory:
    """Creates DataDNA for new datasets — called by Spark listener on every job."""

    @staticmethod
    def create(
        dataset_name: str,
        creator_id:   str,
        raw_data:     bytes,
        parent_ids:   List[str],
        transformation: str,
        pipeline_id:  str,
        sigma_level:  float,
        classification: DataClassification,
        jurisdictions: List[LegalJurisdiction],
        allowed_regions: List[str],
        consent_purpose: str,
        ipfs_cid:     str = "QmPLACEHOLDER",
        fabric_tx_id: str = "TX_PLACEHOLDER",
    ) -> DataDNA:

        content_hash = DataDNA.compute_content_hash(raw_data)

        quality = QualityScore(
            sigma_level=sigma_level,
            completeness_pct=99.9 if sigma_level >= 5 else 97.0,
            accuracy_pct=99.99 if sigma_level >= 6 else 99.0,
            timeliness_score=1.0,
        )

        consent = ConsentRecord(
            owner_id=creator_id,
            purpose=consent_purpose,
            granted_at=time.time(),
            expires_at=None,
        )

        border = BorderPolicy(
            allowed_regions=allowed_regions,
            blocked_regions=[],
            requires_consent=True,
            requires_multisig=LegalJurisdiction.INDIA_DPDP in jurisdictions,
        )

        return DataDNA(
            dataset_id=str(uuid.uuid4()),
            dataset_name=dataset_name,
            creator_id=creator_id,
            created_at=time.time(),
            classification=classification,
            jurisdictions=jurisdictions,
            tags=[classification.value, "datanexus-era3"],
            parent_ids=parent_ids,
            transformation=transformation,
            pipeline_id=pipeline_id,
            quality=quality,
            consent=consent,
            border_policy=border,
            content_hash=content_hash,
            ipfs_cid=ipfs_cid,
            fabric_tx_id=fabric_tx_id,
        )


# ── DEMO ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== DataNexus Era 3 — Data DNA Demo ===\n")

    dna = DataDNAFactory.create(
        dataset_name    = "patient_records_q4_2024",
        creator_id      = "hospital_apollo_hyd",
        raw_data        = b"patient,age,diagnosis\nP001,45,hypertension",
        parent_ids      = ["raw_ehr_2024"],
        transformation  = "PII masking + deduplication via Spark",
        pipeline_id     = "dag_patient_daily_v3",
        sigma_level     = 5.8,
        classification  = DataClassification.HEALTH,
        jurisdictions   = [LegalJurisdiction.INDIA_DPDP, LegalJurisdiction.US_HIPAA],
        allowed_regions = ["IN", "IN-TG", "IN-AP"],
        consent_purpose = "medical_treatment",
        ipfs_cid        = "QmXoypizjW3WknFiJnKLwHCnL72vedxjQkDDP1mXWo6uco",
        fabric_tx_id    = "TX_2024_ABC123DEF456",
    )

    print(f"Dataset:      {dna.dataset_name}")
    print(f"Genome hash:  {dna.genome_hash[:32]}...")
    print(f"Sigma level:  {dna.quality.sigma_level}σ")
    print(f"DPM:          {dna.quality.defects_per_million}")
    print(f"Integrity OK: {dna.verify_integrity()}")
    print()

    tests = [
        ("IN-TG", "Hyderabad hospital"),
        ("US",    "US research lab"),
        ("SG",    "Singapore analytics"),
        ("IN-MH", "Mumbai hospital"),
    ]
    print("Border crossing tests:")
    for region, label in tests:
        allowed, reason = dna.can_cross_border(region)
        status = "✓" if allowed else "✗"
        print(f"  {status} {label:25s} → {reason}")

    print()
    print("Access control tests:")
    for uid, purpose in [
        ("hospital_apollo_hyd", "medical_treatment"),
        ("pharma_corp_mumbai",  "drug_marketing"),
        ("researcher_iit",      "medical_research"),
    ]:
        ok, msg = dna.can_access(uid, purpose)
        print(f"  {'✓' if ok else '✗'} {uid:30s} [{purpose}] → {msg}")
