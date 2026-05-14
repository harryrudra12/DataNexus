// SPDX-License-Identifier: Apache-2.0
// DataNexus Era 3 — Compliance Chaincode
// Encodes DPDP 2023, GDPR, HIPAA, SOX as executable smart contracts.
// Data refuses to cross illegal borders. Compliance is autonomous.

package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type ComplianceContract struct {
	contractapi.Contract
}

// ─────────────────────────────────────────────────────────────
// COMPLIANCE RULE — encoded law
// ─────────────────────────────────────────────────────────────
type ComplianceRule struct {
	RuleID         string   `json:"ruleId"`
	Law            string   `json:"law"`             // DPDP_2023, GDPR, HIPAA, SOX
	LawSection     string   `json:"lawSection"`      // e.g. "DPDP Sec 16(2)"
	Description    string   `json:"description"`
	AppliesTo      []string `json:"appliesTo"`       // PII, HEALTH, FINANCIAL
	BlockedRegions []string `json:"blockedRegions"`  // e.g. ["non-IN"] for DPDP
	AllowedRegions []string `json:"allowedRegions"`  // empty = no restriction
	RequiresConsent bool    `json:"requiresConsent"`
	RequiresMultisig bool   `json:"requiresMultisig"`
	MultisigCount  int      `json:"multisigCount"`
	AutoFix        string   `json:"autoFix"`         // optional remediation
	Penalty        string   `json:"penalty"`
	Active         bool     `json:"active"`
	EnactedAt      string   `json:"enactedAt"`
}

// TRANSFER REQUEST — what data wants to do
type TransferRequest struct {
	RequestID       string   `json:"requestId"`
	DatasetID       string   `json:"datasetId"`
	Classification  string   `json:"classification"`
	Jurisdictions   []string `json:"jurisdictions"`
	SourceRegion    string   `json:"sourceRegion"`
	TargetRegion    string   `json:"targetRegion"`
	Purpose         string   `json:"purpose"`
	HasConsent      bool     `json:"hasConsent"`
	ConsentID       string   `json:"consentId,omitempty"`
	RequesterMSP    string   `json:"requesterMsp"`
	Timestamp       string   `json:"timestamp"`
	SignatureCount  int      `json:"signatureCount"`
}

// COMPLIANCE DECISION — autonomous result
type ComplianceDecision struct {
	DecisionID      string              `json:"decisionId"`
	RequestID       string              `json:"requestId"`
	Decision        string              `json:"decision"`         // ALLOWED | BLOCKED | ALLOWED_WITH_FIX
	Reason          string              `json:"reason"`
	RulesEvaluated  int                 `json:"rulesEvaluated"`
	RulesPassed     int                 `json:"rulesPassed"`
	Violations      []*ViolationRecord  `json:"violations,omitempty"`
	AutoFixesApplied []string           `json:"autoFixesApplied,omitempty"`
	Timestamp       string              `json:"timestamp"`
	FabricTxID      string              `json:"fabricTxId"`
}

type ViolationRecord struct {
	ViolationID  string `json:"violationId"`
	RuleID       string `json:"ruleId"`
	Law          string `json:"law"`
	LawSection   string `json:"lawSection"`
	Description  string `json:"description"`
	Penalty      string `json:"penalty"`
	AutoFixed    bool   `json:"autoFixed"`
}

// ─────────────────────────────────────────────────────────────
// INITIALIZE — load all current laws into ledger
// ─────────────────────────────────────────────────────────────
func (s *ComplianceContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	// All rules active as of 2025
	rules := []ComplianceRule{
		// ─── DPDP 2023 (India) ─────────────────────────────
		{
			RuleID: "DPDP-001", Law: "DPDP_2023", LawSection: "Sec 16(2)",
			Description:     "Personal data of Indian citizens cannot leave India without explicit consent",
			AppliesTo:       []string{"PII", "HEALTH", "FINANCIAL", "BIOMETRIC"},
			BlockedRegions:  []string{"non-IN"},
			AllowedRegions:  []string{"IN", "IN-TG", "IN-MH", "IN-DL", "IN-KA", "IN-AP", "IN-TN"},
			RequiresConsent: true,
			AutoFix:         "request_consent_workflow",
			Penalty:         "₹250 crore or 4% of global turnover",
			Active:          true,
			EnactedAt:       "2023-08-11T00:00:00Z",
		},
		{
			RuleID: "DPDP-002", Law: "DPDP_2023", LawSection: "Sec 6",
			Description:     "Data use must match purpose declared in consent",
			AppliesTo:       []string{"PII", "HEALTH", "FINANCIAL", "BIOMETRIC"},
			RequiresConsent: true,
			Penalty:         "₹100 crore",
			Active:          true,
			EnactedAt:       "2023-08-11T00:00:00Z",
		},
		{
			RuleID: "DPDP-003", Law: "DPDP_2023", LawSection: "Sec 8(7)",
			Description:     "Data fiduciary must maintain processing records",
			AppliesTo:       []string{"PII", "HEALTH", "FINANCIAL"},
			AutoFix:         "log_to_fabric_lineage",
			Penalty:         "₹50 crore",
			Active:          true,
			EnactedAt:       "2023-08-11T00:00:00Z",
		},
		{
			RuleID: "DPDP-004", Law: "DPDP_2023", LawSection: "Sec 10",
			Description:     "Significant data fiduciary requires multi-sig for cross-border transfers",
			AppliesTo:       []string{"PII"},
			RequiresMultisig: true,
			MultisigCount:   3,
			Penalty:         "License revocation",
			Active:          true,
			EnactedAt:       "2023-08-11T00:00:00Z",
		},

		// ─── GDPR (EU) ─────────────────────────────────────
		{
			RuleID: "GDPR-001", Law: "GDPR", LawSection: "Art 45",
			Description:     "EU personal data cannot leave EU without adequacy decision",
			AppliesTo:       []string{"PII", "HEALTH"},
			AllowedRegions: []string{
				"EU-DE","EU-FR","EU-IT","EU-ES","EU-NL","EU-BE","EU-AT","EU-DK",
				"EU-FI","EU-SE","EU-PL","EU-PT","EU-IE","EU-CZ","EU-HU","EU-GR",
				// adequacy-decision countries
				"UK","CH","NO","JP","CA","NZ","AR","IL","UY","KR",
			},
			RequiresConsent: true,
			Penalty:         "€20M or 4% of global turnover",
			Active:          true,
			EnactedAt:       "2018-05-25T00:00:00Z",
		},
		{
			RuleID: "GDPR-002", Law: "GDPR", LawSection: "Art 17",
			Description: "Right to erasure — data must be deletable on request",
			AppliesTo:   []string{"PII"},
			AutoFix:     "mark_for_erasure_review",
			Penalty:     "€10M or 2% of global turnover",
			Active:      true,
			EnactedAt:   "2018-05-25T00:00:00Z",
		},
		{
			RuleID: "GDPR-003", Law: "GDPR", LawSection: "Art 5(1)(c)",
			Description: "Data minimisation — only fields necessary for the purpose",
			AppliesTo:   []string{"PII"},
			AutoFix:     "drop_unjustified_columns",
			Penalty:     "€10M or 2% of global turnover",
			Active:      true,
			EnactedAt:   "2018-05-25T00:00:00Z",
		},

		// ─── HIPAA (US Health) ─────────────────────────────
		{
			RuleID: "HIPAA-001", Law: "HIPAA", LawSection: "164.312(a)(2)(iv)",
			Description: "Protected Health Information must be encrypted in transit and at rest",
			AppliesTo:   []string{"HEALTH"},
			AutoFix:     "force_encryption_now",
			Penalty:     "$1.5M per violation per year",
			Active:      true,
			EnactedAt:   "2003-04-14T00:00:00Z",
		},
		{
			RuleID: "HIPAA-002", Law: "HIPAA", LawSection: "164.502(b)",
			Description: "PHI access requires minimum necessary standard",
			AppliesTo:   []string{"HEALTH"},
			Penalty:     "$1.5M per violation per year",
			Active:      true,
			EnactedAt:   "2003-04-14T00:00:00Z",
		},

		// ─── SOX (Financial) ───────────────────────────────
		{
			RuleID: "SOX-001", Law: "SOX", LawSection: "Sec 302",
			Description: "Financial data integrity requires immutable audit trail",
			AppliesTo:   []string{"FINANCIAL"},
			AutoFix:     "log_to_fabric_lineage",
			Penalty:     "$5M criminal, 20 years prison",
			Active:      true,
			EnactedAt:   "2002-07-30T00:00:00Z",
		},
	}

	// Store every rule on-chain
	for _, rule := range rules {
		ruleJSON, _ := json.Marshal(rule)
		key := fmt.Sprintf("RULE_%s", rule.RuleID)
		if err := ctx.GetStub().PutState(key, ruleJSON); err != nil {
			return fmt.Errorf("could not store rule %s: %v", rule.RuleID, err)
		}
	}

	return nil
}

// ─────────────────────────────────────────────────────────────
// MAIN ENTRY: CHECK TRANSFER — autonomous compliance evaluation
// ─────────────────────────────────────────────────────────────
func (s *ComplianceContract) CheckTransfer(
	ctx contractapi.TransactionContextInterface,
	requestJSON string,
) (*ComplianceDecision, error) {

	var request TransferRequest
	if err := json.Unmarshal([]byte(requestJSON), &request); err != nil {
		return nil, fmt.Errorf("invalid transfer request: %v", err)
	}

	// Get Fabric tx ID
	txID := ctx.GetStub().GetTxID()
	txTime, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return nil, err
	}
	timestamp := time.Unix(txTime.Seconds, int64(txTime.Nanos)).UTC().Format(time.RFC3339)

	// Determine which rules apply
	applicableRules, err := s.findApplicableRules(ctx, &request)
	if err != nil {
		return nil, err
	}

	// Evaluate every applicable rule
	violations := []*ViolationRecord{}
	autoFixes := []string{}
	rulesPassed := 0

	for _, rule := range applicableRules {
		passed, autoFix := s.evaluateRule(rule, &request)
		if passed {
			rulesPassed++
			continue
		}

		// Rule violated — create violation record
		violation := &ViolationRecord{
			ViolationID: fmt.Sprintf("V-%s-%s", rule.RuleID, txID[:8]),
			RuleID:      rule.RuleID,
			Law:         rule.Law,
			LawSection:  rule.LawSection,
			Description: rule.Description,
			Penalty:     rule.Penalty,
			AutoFixed:   false,
		}

		// Try auto-fix
		if autoFix != "" {
			violation.AutoFixed = true
			autoFixes = append(autoFixes, autoFix)
			rulesPassed++ // auto-fix counts as passed
		}

		violations = append(violations, violation)
	}

	// Final decision
	decision := "ALLOWED"
	reason := "All compliance rules satisfied"
	allViolationsFixed := true
	for _, v := range violations {
		if !v.AutoFixed {
			allViolationsFixed = false
			break
		}
	}

	if len(violations) > 0 && !allViolationsFixed {
		decision = "BLOCKED"
		var causes []string
		for _, v := range violations {
			if !v.AutoFixed {
				causes = append(causes, fmt.Sprintf("%s (%s)", v.RuleID, v.LawSection))
			}
		}
		reason = "BLOCKED by: " + strings.Join(causes, ", ")
	} else if len(violations) > 0 {
		decision = "ALLOWED_WITH_FIX"
		reason = fmt.Sprintf("Allowed after %d auto-fixes applied", len(autoFixes))
	}

	// Build decision record
	result := &ComplianceDecision{
		DecisionID:       fmt.Sprintf("DEC-%s", txID[:12]),
		RequestID:        request.RequestID,
		Decision:         decision,
		Reason:           reason,
		RulesEvaluated:   len(applicableRules),
		RulesPassed:      rulesPassed,
		Violations:       violations,
		AutoFixesApplied: autoFixes,
		Timestamp:        timestamp,
		FabricTxID:       txID,
	}

	// Store decision permanently on-chain
	resultJSON, _ := json.Marshal(result)
	decisionKey, _ := ctx.GetStub().CreateCompositeKey(
		"decision",
		[]string{request.DatasetID, txID},
	)
	if err := ctx.GetStub().PutState(decisionKey, resultJSON); err != nil {
		return nil, err
	}

	// Emit event for off-chain monitors
	eventPayload, _ := json.Marshal(map[string]string{
		"decisionId": result.DecisionID,
		"datasetId":  request.DatasetID,
		"decision":   decision,
		"reason":     reason,
	})
	ctx.GetStub().SetEvent("ComplianceDecision", eventPayload)

	return result, nil
}

// ─────────────────────────────────────────────────────────────
// FIND APPLICABLE RULES
// ─────────────────────────────────────────────────────────────
func (s *ComplianceContract) findApplicableRules(
	ctx contractapi.TransactionContextInterface,
	req *TransferRequest,
) ([]*ComplianceRule, error) {

	var applicable []*ComplianceRule

	// Iterate through all rules in jurisdiction list
	for _, jurisdiction := range req.Jurisdictions {
		// Get rules for this jurisdiction (DPDP_2023, GDPR, HIPAA, SOX)
		iter, err := ctx.GetStub().GetStateByRange("RULE_", "RULE_z")
		if err != nil {
			return nil, err
		}
		for iter.HasNext() {
			entry, err := iter.Next()
			if err != nil {
				iter.Close()
				return nil, err
			}
			var rule ComplianceRule
			if err := json.Unmarshal(entry.Value, &rule); err != nil {
				continue
			}
			if !rule.Active || rule.Law != jurisdiction {
				continue
			}
			// Check if rule applies to this classification
			if len(rule.AppliesTo) > 0 {
				matches := false
				for _, classifier := range rule.AppliesTo {
					if classifier == req.Classification {
						matches = true
						break
					}
				}
				if !matches {
					continue
				}
			}
			applicable = append(applicable, &rule)
		}
		iter.Close()
	}

	return applicable, nil
}

// ─────────────────────────────────────────────────────────────
// EVALUATE A RULE — pure function, deterministic
// ─────────────────────────────────────────────────────────────
func (s *ComplianceContract) evaluateRule(
	rule *ComplianceRule,
	req *TransferRequest,
) (passed bool, autoFix string) {

	// CHECK 1: blocked regions
	for _, blocked := range rule.BlockedRegions {
		if blocked == "non-IN" && !strings.HasPrefix(req.TargetRegion, "IN") {
			return false, rule.AutoFix
		}
		if req.TargetRegion == blocked {
			return false, rule.AutoFix
		}
	}

	// CHECK 2: allowed regions whitelist
	if len(rule.AllowedRegions) > 0 {
		isAllowed := false
		for _, allowed := range rule.AllowedRegions {
			if req.TargetRegion == allowed {
				isAllowed = true
				break
			}
		}
		if !isAllowed {
			return false, rule.AutoFix
		}
	}

	// CHECK 3: consent requirement
	if rule.RequiresConsent && !req.HasConsent {
		return false, rule.AutoFix
	}

	// CHECK 4: multi-signature requirement
	if rule.RequiresMultisig && req.SignatureCount < rule.MultisigCount {
		return false, ""  // multi-sig cannot be auto-fixed
	}

	return true, ""
}

// ─────────────────────────────────────────────────────────────
// QUERY DECISIONS — audit trail of compliance choices
// ─────────────────────────────────────────────────────────────
func (s *ComplianceContract) GetDecisionsForDataset(
	ctx contractapi.TransactionContextInterface,
	datasetID string,
) ([]*ComplianceDecision, error) {

	iter, err := ctx.GetStub().GetStateByPartialCompositeKey(
		"decision",
		[]string{datasetID},
	)
	if err != nil {
		return nil, err
	}
	defer iter.Close()

	var decisions []*ComplianceDecision
	for iter.HasNext() {
		entry, err := iter.Next()
		if err != nil {
			return nil, err
		}
		var d ComplianceDecision
		if err := json.Unmarshal(entry.Value, &d); err != nil {
			continue
		}
		decisions = append(decisions, &d)
	}
	return decisions, nil
}

// ─────────────────────────────────────────────────────────────
// COMPLIANCE REPORT — court-admissible PDF data
// ─────────────────────────────────────────────────────────────
type ComplianceReport struct {
	ReportID          string                  `json:"reportId"`
	DatasetID         string                  `json:"datasetId"`
	GeneratedAt       string                  `json:"generatedAt"`
	TotalDecisions    int                     `json:"totalDecisions"`
	Allowed           int                     `json:"allowed"`
	Blocked           int                     `json:"blocked"`
	AutoFixed         int                     `json:"autoFixed"`
	ComplianceRate    float64                 `json:"complianceRate"`
	RecentDecisions   []*ComplianceDecision   `json:"recentDecisions"`
	BlockchainProof   string                  `json:"blockchainProof"`
}

func (s *ComplianceContract) GenerateComplianceReport(
	ctx contractapi.TransactionContextInterface,
	datasetID string,
) (*ComplianceReport, error) {

	decisions, err := s.GetDecisionsForDataset(ctx, datasetID)
	if err != nil {
		return nil, err
	}

	allowed, blocked, autoFixed := 0, 0, 0
	for _, d := range decisions {
		switch d.Decision {
		case "ALLOWED":          allowed++
		case "BLOCKED":          blocked++
		case "ALLOWED_WITH_FIX": autoFixed++
		}
	}

	total := len(decisions)
	rate := 100.0
	if total > 0 {
		rate = float64(allowed+autoFixed) / float64(total) * 100.0
	}

	// Take last 10 decisions
	recent := decisions
	if len(decisions) > 10 {
		recent = decisions[len(decisions)-10:]
	}

	// Blockchain proof: hash of dataset ID + decision count + first/last tx IDs
	proofParts := []string{datasetID, fmt.Sprintf("%d", total)}
	if total > 0 {
		proofParts = append(proofParts, decisions[0].FabricTxID, decisions[len(decisions)-1].FabricTxID)
	}
	proofRaw := strings.Join(proofParts, "|")
	proof := sha256.Sum256([]byte(proofRaw))

	report := &ComplianceReport{
		ReportID:        fmt.Sprintf("CR-%s-%d", datasetID[:min(8, len(datasetID))], time.Now().Unix()),
		DatasetID:       datasetID,
		GeneratedAt:     time.Now().UTC().Format(time.RFC3339),
		TotalDecisions:  total,
		Allowed:         allowed,
		Blocked:         blocked,
		AutoFixed:       autoFixed,
		ComplianceRate:  rate,
		RecentDecisions: recent,
		BlockchainProof: hex.EncodeToString(proof[:]),
	}

	// Store report on-chain so it itself is auditable
	reportJSON, _ := json.Marshal(report)
	ctx.GetStub().PutState("COMPLIANCE_REPORT_"+report.ReportID, reportJSON)

	return report, nil
}

// ─────────────────────────────────────────────────────────────
// ADMIN: ADD/UPDATE A LAW (governance-controlled)
// ─────────────────────────────────────────────────────────────
func (s *ComplianceContract) AddRule(
	ctx contractapi.TransactionContextInterface,
	ruleJSON string,
) error {
	// Only admin org can add rules
	clientMSP, _ := ctx.GetClientIdentity().GetMSPID()
	if clientMSP != "DataNexusAdminMSP" && clientMSP != "GovernmentMSP" {
		return fmt.Errorf("only admin org can add compliance rules, got %s", clientMSP)
	}

	var rule ComplianceRule
	if err := json.Unmarshal([]byte(ruleJSON), &rule); err != nil {
		return err
	}
	rule.EnactedAt = time.Now().UTC().Format(time.RFC3339)
	bytes, _ := json.Marshal(rule)
	return ctx.GetStub().PutState("RULE_"+rule.RuleID, bytes)
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
func min(a, b int) int {
	if a < b { return a }
	return b
}

// ─────────────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────────────
func main() {
	chaincode, err := contractapi.NewChaincode(&ComplianceContract{})
	if err != nil {
		fmt.Printf("Error creating Compliance chaincode: %v\n", err)
		return
	}
	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting Compliance chaincode: %v\n", err)
	}
}
