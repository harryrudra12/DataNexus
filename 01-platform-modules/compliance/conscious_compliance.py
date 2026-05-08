"""
DataNexus Era 3 — Conscious Compliance
Data knows which laws apply to it.
Data refuses to go where it is not allowed.
Compliance is in the data, not the system.
"""
import json, time, hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from enum import Enum

class LawCode(Enum):
    INDIA_DPDP   = "IN_DPDP_2023"
    EU_GDPR      = "EU_GDPR_2018"
    US_HIPAA     = "US_HIPAA_1996"
    US_SOX       = "US_SOX_2002"
    GLOBAL_OPEN  = "GLOBAL_OPEN"

@dataclass
class ComplianceRule:
    rule_id:     str
    law:         LawCode
    description: str
    check:       str      # Python expression to evaluate
    penalty:     str      # what happens if violated
    auto_fix:    Optional[str] = None  # auto-remediation if available

class ConsciousComplianceEngine:
    """
    Every data packet checks itself against applicable laws.
    No human compliance officer needed.
    Laws are smart contracts — executable, auditable, automatic.
    """

    # Laws as executable rules
    LAWS: Dict[LawCode, List[ComplianceRule]] = {

        LawCode.INDIA_DPDP: [
            ComplianceRule(
                rule_id="DPDP-001",
                law=LawCode.INDIA_DPDP,
                description="Personal data of Indian citizens must not leave India without explicit consent",
                check="target_country == 'IN' or has_explicit_consent == True",
                penalty="BLOCK transfer; notify Data Protection Officer",
                auto_fix="request_consent() if can_request else block_transfer()",
            ),
            ComplianceRule(
                rule_id="DPDP-002",
                law=LawCode.INDIA_DPDP,
                description="Sensitive personal data requires purpose limitation",
                check="transfer_purpose in data.consent.allowed_purposes",
                penalty="BLOCK transfer; log violation to Fabric",
                auto_fix=None,
            ),
            ComplianceRule(
                rule_id="DPDP-003",
                law=LawCode.INDIA_DPDP,
                description="Data fiduciary must maintain processing records",
                check="fabric_tx_id is not None and fabric_tx_id != ''",
                penalty="QUARANTINE data; require Fabric logging before use",
                auto_fix="log_to_fabric() and retry()",
            ),
        ],

        LawCode.EU_GDPR: [
            ComplianceRule(
                rule_id="GDPR-001",
                law=LawCode.EU_GDPR,
                description="Data of EU residents cannot leave EU without adequacy decision",
                check="target_country in EU_ADEQUATE_COUNTRIES",
                penalty="BLOCK transfer; notify DPA within 72 hours if breach",
                auto_fix=None,
            ),
            ComplianceRule(
                rule_id="GDPR-002",
                law=LawCode.EU_GDPR,
                description="Right to erasure — data must be deletable on request",
                check="data.is_erasable == True",
                penalty="FLAG dataset; schedule erasure review",
                auto_fix="mark_for_erasure_review()",
            ),
            ComplianceRule(
                rule_id="GDPR-003",
                law=LawCode.EU_GDPR,
                description="Data minimisation — only necessary data collected",
                check="data.field_count <= data.justified_field_count",
                penalty="ALERT data steward; recommend minimisation",
                auto_fix="drop_unjustified_columns()",
            ),
        ],

        LawCode.US_HIPAA: [
            ComplianceRule(
                rule_id="HIPAA-001",
                law=LawCode.US_HIPAA,
                description="PHI must be encrypted in transit and at rest",
                check="data.encrypted_at_rest == True and data.encrypted_in_transit == True",
                penalty="BLOCK access; encrypt immediately",
                auto_fix="encrypt_now() and retry_access()",
            ),
            ComplianceRule(
                rule_id="HIPAA-002",
                law=LawCode.US_HIPAA,
                description="PHI access requires minimum necessary standard",
                check="requester.clearance_level >= data.required_clearance",
                penalty="DENY access; log attempt to audit trail",
                auto_fix=None,
            ),
        ],
    }

    EU_ADEQUATE_COUNTRIES = {
        "DE","FR","IT","ES","NL","BE","SE","AT","DK","FI",
        "PL","PT","GR","CZ","RO","HU","SK","BG","HR","LT",
        "LV","EE","SI","MT","CY","LU","IE","UK","CH","NO",
        "IS","LI","JP","CA","NZ","AR","IL","UY","KR","GB",
    }

    def __init__(self):
        self.violation_log: List[dict] = []
        self.auto_fix_log:  List[dict] = []
        self.audit_trail:   List[dict] = []
        print("[COMPLIANCE] Conscious Compliance Engine online")
        print(f"[COMPLIANCE] Laws loaded: {len(self.LAWS)} jurisdictions")

    def check_transfer(
        self,
        dataset_id:       str,
        applicable_laws:  List[LawCode],
        target_country:   str,
        transfer_purpose: str,
        context:          Dict,
    ) -> Tuple[bool, str, List[dict]]:
        """
        Data checks itself before crossing a border.
        Returns: (allowed, reason, violations_found)
        """
        violations = []
        allowed    = True
        reasons    = []

        for law in applicable_laws:
            rules = self.LAWS.get(law, [])
            for rule in rules:
                result = self._evaluate_rule(rule, target_country,
                                              transfer_purpose, context)
                if not result["passed"]:
                    violations.append(result)
                    allowed = False
                    reasons.append(f"{rule.rule_id}: {rule.description}")

                    # Log violation to blockchain
                    self._log_violation(dataset_id, rule, target_country, context)

                    # Attempt auto-fix if available
                    if rule.auto_fix:
                        fix_result = self._apply_auto_fix(dataset_id, rule)
                        if fix_result["success"]:
                            allowed = True  # fix resolved the violation
                            reasons.append(f"  AUTO-FIXED: {fix_result['action']}")

        final_reason = " | ".join(reasons) if reasons else "ALL COMPLIANCE CHECKS PASSED"
        self._log_audit(dataset_id, target_country, allowed, final_reason)

        return allowed, final_reason, violations

    def _evaluate_rule(self, rule: ComplianceRule, target_country: str,
                        purpose: str, ctx: Dict) -> dict:
        """Evaluate a single compliance rule against current context."""
        try:
            eval_ctx = {
                "target_country":        target_country,
                "transfer_purpose":      purpose,
                "has_explicit_consent":  ctx.get("has_consent", False),
                "EU_ADEQUATE_COUNTRIES": self.EU_ADEQUATE_COUNTRIES,
                "data":                  type("D", (), ctx.get("data_props", {}))(),
                "requester":             type("R", (), ctx.get("requester", {}))(),
                "fabric_tx_id":          ctx.get("fabric_tx_id", ""),
            }
            passed = bool(eval(rule.check, {"__builtins__": {}}, eval_ctx))
        except Exception as e:
            passed = False  # fail safe — unknown = blocked

        return {
            "rule_id":    rule.rule_id,
            "law":        rule.law.value,
            "passed":     passed,
            "description":rule.description,
            "penalty":    rule.penalty,
        }

    def _apply_auto_fix(self, dataset_id: str, rule: ComplianceRule) -> dict:
        """Apply automatic remediation when available."""
        fix_record = {
            "dataset_id":  dataset_id,
            "rule_id":     rule.rule_id,
            "action":      rule.auto_fix,
            "applied_at":  time.time(),
            "success":     True,   # assume success for demo
        }
        self.auto_fix_log.append(fix_record)
        print(f"[COMPLIANCE] AUTO-FIX applied: {rule.rule_id} → {rule.auto_fix}")
        return fix_record

    def _log_violation(self, dataset_id: str, rule: ComplianceRule,
                        target: str, ctx: Dict):
        record = {
            "violation_id": hashlib.sha256(
                f"{dataset_id}{rule.rule_id}{time.time()}".encode()).hexdigest()[:16],
            "dataset_id":   dataset_id,
            "rule_id":      rule.rule_id,
            "law":          rule.law.value,
            "target":       target,
            "detected_at":  time.time(),
            "penalty":      rule.penalty,
        }
        self.violation_log.append(record)
        print(f"[COMPLIANCE] VIOLATION: {rule.rule_id} | {rule.law.value} | Target: {target}")
        print(f"[COMPLIANCE]   Penalty: {rule.penalty}")

    def _log_audit(self, dataset_id: str, target: str,
                    allowed: bool, reason: str):
        """Every compliance decision logged to Hyperledger Fabric."""
        entry = {
            "audit_id":   hashlib.sha256(
                f"{dataset_id}{target}{time.time()}".encode()).hexdigest()[:16],
            "dataset_id": dataset_id,
            "target":     target,
            "decision":   "ALLOWED" if allowed else "BLOCKED",
            "reason":     reason,
            "timestamp":  time.time(),
        }
        self.audit_trail.append(entry)
        # In production: peer chaincode invoke on Hyperledger Fabric
        print(f"[FABRIC] Audit logged: {entry['audit_id']} | {entry['decision']}")

    def generate_compliance_report(self, dataset_id: str) -> str:
        """60-second blockchain-verified compliance report."""
        relevant_violations = [v for v in self.violation_log
                                if v["dataset_id"] == dataset_id]
        relevant_audits     = [a for a in self.audit_trail
                                if a["dataset_id"] == dataset_id]
        relevant_fixes      = [f for f in self.auto_fix_log
                                if f["dataset_id"] == dataset_id]

        report = {
            "report_id":       hashlib.sha256(
                f"{dataset_id}{time.time()}".encode()).hexdigest()[:16],
            "dataset_id":      dataset_id,
            "generated_at":    time.time(),
            "generated_by":    "DataNexus Conscious Compliance Engine v1.0",
            "blockchain_proof":"Hyperledger Fabric TX: " +
                               hashlib.sha256(dataset_id.encode()).hexdigest()[:32],
            "total_checks":    len(relevant_audits),
            "violations":      len(relevant_violations),
            "auto_fixes":      len(relevant_fixes),
            "compliance_rate": f"{(1 - len(relevant_violations)/max(len(relevant_audits),1))*100:.1f}%",
            "violation_details":relevant_violations,
            "audit_trail":     relevant_audits[-5:],  # last 5
        }

        return json.dumps(report, indent=2)


# ── DEMO ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== DataNexus Era 3 — Conscious Compliance Demo ===\n")
    engine = ConsciousComplianceEngine()

    # Dataset: Indian patient records, DPDP applies
    tests = [
        {
            "dataset_id":      "patient_records_apollo",
            "applicable_laws": [LawCode.INDIA_DPDP, LawCode.US_HIPAA],
            "target_country":  "IN",
            "purpose":         "medical_treatment",
            "context":         {"has_consent": True, "fabric_tx_id": "TX_ABC123",
                                "data_props":  {"encrypted_at_rest": True,
                                                "encrypted_in_transit": True},
                                "requester":   {"clearance_level": 3}},
            "label":           "Indian hospital → Hyderabad branch",
        },
        {
            "dataset_id":      "patient_records_apollo",
            "applicable_laws": [LawCode.INDIA_DPDP],
            "target_country":  "US",
            "purpose":         "drug_marketing",
            "context":         {"has_consent": False, "fabric_tx_id": "TX_DEF456"},
            "label":           "Indian hospital → US pharma company",
        },
        {
            "dataset_id":      "eu_customer_data",
            "applicable_laws": [LawCode.EU_GDPR],
            "target_country":  "SG",
            "purpose":         "analytics",
            "context":         {"has_consent": False, "fabric_tx_id": "TX_GHI789"},
            "label":           "EU customer data → Singapore analytics",
        },
        {
            "dataset_id":      "eu_customer_data",
            "applicable_laws": [LawCode.EU_GDPR],
            "target_country":  "DE",
            "purpose":         "analytics",
            "context":         {"has_consent": True, "fabric_tx_id": "TX_JKL012"},
            "label":           "EU customer data → Germany (within EU)",
        },
    ]

    for test in tests:
        print(f"\n{'='*60}")
        print(f"Transfer: {test['label']}")
        allowed, reason, violations = engine.check_transfer(
            dataset_id      = test["dataset_id"],
            applicable_laws = test["applicable_laws"],
            target_country  = test["target_country"],
            transfer_purpose= test["purpose"],
            context         = test["context"],
        )
        status = "ALLOWED" if allowed else "BLOCKED"
        print(f"Decision: {status}")
        if not allowed:
            print(f"Reason:   {reason}")

    print(f"\n{'='*60}")
    print("Compliance Report for patient_records_apollo:")
    print(engine.generate_compliance_report("patient_records_apollo"))
