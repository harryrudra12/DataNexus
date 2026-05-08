// SPDX-License-Identifier: Apache-2.0
// DataNexus Era 3 — Quality Chaincode
// Records every Six Sigma quality measurement permanently.
// Provides cryptographic proof of pipeline quality for SLAs and audits.

package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type QualityContract struct {
	contractapi.Contract
}

// QualityMeasurement — one Six Sigma measurement event
type QualityMeasurement struct {
	MeasurementID    string  `json:"measurementId"`
	PipelineID       string  `json:"pipelineId"`
	DatasetID        string  `json:"datasetId"`
	RunID            string  `json:"runId"`
	Timestamp        string  `json:"timestamp"`

	// DMAIC: Define, Measure, Analyse, Improve, Control
	DMAICPhase       string  `json:"dmaicPhase"`

	// Six Sigma metrics
	SigmaLevel       float64 `json:"sigmaLevel"`
	DefectsPerMillion float64 `json:"defectsPerMillion"`
	CompletenessPct  float64 `json:"completenessPct"`
	AccuracyPct      float64 `json:"accuracyPct"`
	TimelinessScore  float64 `json:"timelinessScore"`

	// Volume
	RecordsProcessed int64   `json:"recordsProcessed"`
	RecordsFailed    int64   `json:"recordsFailed"`

	// Test results from Great Expectations
	ExpectationsRun  int     `json:"expectationsRun"`
	ExpectationsPassed int   `json:"expectationsPassed"`

	// Identity and source
	NodeID           string  `json:"nodeId"`
	Region           string  `json:"region"`
	OperatorMSP      string  `json:"operatorMsp"`

	// Tamper detection
	MeasurementHash  string  `json:"measurementHash"`
	FabricTxID       string  `json:"fabricTxId"`
}

type SLATarget struct {
	PipelineID       string  `json:"pipelineId"`
	MinSigmaLevel    float64 `json:"minSigmaLevel"`     // contractual minimum
	TargetSigmaLevel float64 `json:"targetSigmaLevel"`  // aspirational
	BreachThreshold  float64 `json:"breachThreshold"`   // auto-quarantine below this
	CustomerOrg      string  `json:"customerOrg"`
	ContractStartDate string `json:"contractStartDate"`
	Active           bool    `json:"active"`
}

type SLABreachAlert struct {
	AlertID         string  `json:"alertId"`
	PipelineID      string  `json:"pipelineId"`
	BreachedAt      string  `json:"breachedAt"`
	ExpectedMin     float64 `json:"expectedMin"`
	ActualSigma     float64 `json:"actualSigma"`
	Severity        string  `json:"severity"`     // CRITICAL | HIGH | MEDIUM
	AutoQuarantined bool    `json:"autoQuarantined"`
	NotifiedOrgs    []string `json:"notifiedOrgs"`
}

// ─────────────────────────────────────────────────────────────
// LOG QUALITY MEASUREMENT
// ─────────────────────────────────────────────────────────────
func (s *QualityContract) LogMeasurement(
	ctx contractapi.TransactionContextInterface,
	measurementJSON string,
) (*QualityMeasurement, error) {

	var m QualityMeasurement
	if err := json.Unmarshal([]byte(measurementJSON), &m); err != nil {
		return nil, fmt.Errorf("invalid measurement: %v", err)
	}

	// Validation
	if m.PipelineID == "" || m.DatasetID == "" {
		return nil, fmt.Errorf("pipelineId and datasetId required")
	}
	if m.SigmaLevel < 1.0 || m.SigmaLevel > 6.0 {
		return nil, fmt.Errorf("sigmaLevel out of range 1.0–6.0")
	}

	// Auto-compute defects per million from sigma if not provided
	if m.DefectsPerMillion == 0 {
		m.DefectsPerMillion = sigmaToDpm(m.SigmaLevel)
	}

	// Get Fabric tx context
	txID := ctx.GetStub().GetTxID()
	txTime, _ := ctx.GetStub().GetTxTimestamp()
	clientMSP, _ := ctx.GetClientIdentity().GetMSPID()

	m.MeasurementID = fmt.Sprintf("M-%s-%s", m.PipelineID, txID[:12])
	m.FabricTxID    = txID
	m.OperatorMSP   = clientMSP
	m.Timestamp     = time.Unix(txTime.Seconds, int64(txTime.Nanos)).UTC().Format(time.RFC3339)
	m.MeasurementHash = computeMeasurementHash(&m)

	// Persist
	bytes, err := json.Marshal(m)
	if err != nil {
		return nil, err
	}

	// Composite key: pipelineId + timestamp
	key, err := ctx.GetStub().CreateCompositeKey(
		"measurement",
		[]string{m.PipelineID, m.Timestamp, txID[:12]},
	)
	if err != nil {
		return nil, err
	}
	if err := ctx.GetStub().PutState(key, bytes); err != nil {
		return nil, err
	}

	// Check SLA breach asynchronously
	if err := s.checkSLA(ctx, &m); err != nil {
		// Log but do not fail the measurement record
		fmt.Printf("SLA check failed: %v\n", err)
	}

	// Emit event
	eventPayload, _ := json.Marshal(map[string]interface{}{
		"measurementId": m.MeasurementID,
		"pipelineId":    m.PipelineID,
		"sigmaLevel":    m.SigmaLevel,
	})
	ctx.GetStub().SetEvent("QualityMeasured", eventPayload)

	return &m, nil
}

// ─────────────────────────────────────────────────────────────
// SLA MANAGEMENT
// ─────────────────────────────────────────────────────────────
func (s *QualityContract) SetSLATarget(
	ctx contractapi.TransactionContextInterface,
	slaJSON string,
) error {
	var sla SLATarget
	if err := json.Unmarshal([]byte(slaJSON), &sla); err != nil {
		return fmt.Errorf("invalid SLA: %v", err)
	}

	// SLA contracts must come from authorized orgs
	clientMSP, _ := ctx.GetClientIdentity().GetMSPID()
	if !strings.Contains(clientMSP, "DataNexus") && !strings.Contains(clientMSP, "Customer") {
		return fmt.Errorf("only DataNexus or Customer orgs can set SLAs")
	}

	if sla.MinSigmaLevel < 4.5 {
		return fmt.Errorf("minimum SLA must be at least 4.5σ — DataNexus does not contract below this")
	}

	bytes, _ := json.Marshal(sla)
	return ctx.GetStub().PutState("SLA_"+sla.PipelineID, bytes)
}

func (s *QualityContract) GetSLA(
	ctx contractapi.TransactionContextInterface,
	pipelineID string,
) (*SLATarget, error) {
	bytes, err := ctx.GetStub().GetState("SLA_" + pipelineID)
	if err != nil {
		return nil, err
	}
	if bytes == nil {
		return nil, nil // no SLA set is not an error
	}
	var sla SLATarget
	if err := json.Unmarshal(bytes, &sla); err != nil {
		return nil, err
	}
	return &sla, nil
}

func (s *QualityContract) checkSLA(
	ctx contractapi.TransactionContextInterface,
	m *QualityMeasurement,
) error {
	sla, err := s.GetSLA(ctx, m.PipelineID)
	if err != nil || sla == nil || !sla.Active {
		return err
	}

	if m.SigmaLevel < sla.BreachThreshold {
		// SLA breach!
		alert := SLABreachAlert{
			AlertID:         fmt.Sprintf("SLA-BREACH-%s-%s", m.PipelineID, m.FabricTxID[:8]),
			PipelineID:      m.PipelineID,
			BreachedAt:      m.Timestamp,
			ExpectedMin:     sla.MinSigmaLevel,
			ActualSigma:     m.SigmaLevel,
			Severity:        severityFromGap(sla.MinSigmaLevel - m.SigmaLevel),
			AutoQuarantined: m.SigmaLevel < sla.BreachThreshold,
			NotifiedOrgs:    []string{"DataNexus", sla.CustomerOrg},
		}
		alertJSON, _ := json.Marshal(alert)
		alertKey, _ := ctx.GetStub().CreateCompositeKey(
			"alert",
			[]string{m.PipelineID, m.Timestamp},
		)
		ctx.GetStub().PutState(alertKey, alertJSON)

		// Emit critical event
		eventPayload, _ := json.Marshal(alert)
		ctx.GetStub().SetEvent("SLABreach", eventPayload)
	}
	return nil
}

// ─────────────────────────────────────────────────────────────
// QUERY MEASUREMENTS
// ─────────────────────────────────────────────────────────────
func (s *QualityContract) GetMeasurementsForPipeline(
	ctx contractapi.TransactionContextInterface,
	pipelineID string,
) ([]*QualityMeasurement, error) {

	iter, err := ctx.GetStub().GetStateByPartialCompositeKey(
		"measurement",
		[]string{pipelineID},
	)
	if err != nil {
		return nil, err
	}
	defer iter.Close()

	var measurements []*QualityMeasurement
	for iter.HasNext() {
		entry, err := iter.Next()
		if err != nil {
			return nil, err
		}
		var m QualityMeasurement
		if err := json.Unmarshal(entry.Value, &m); err != nil {
			continue
		}
		measurements = append(measurements, &m)
	}

	// Sort newest first
	sort.Slice(measurements, func(i, j int) bool {
		return measurements[i].Timestamp > measurements[j].Timestamp
	})
	return measurements, nil
}

// ─────────────────────────────────────────────────────────────
// SIGMA TREND — last N measurements
// ─────────────────────────────────────────────────────────────
type SigmaTrendPoint struct {
	Timestamp  string  `json:"timestamp"`
	SigmaLevel float64 `json:"sigmaLevel"`
	RunID      string  `json:"runId"`
}

func (s *QualityContract) GetSigmaTrend(
	ctx contractapi.TransactionContextInterface,
	pipelineID string,
	limit int,
) ([]*SigmaTrendPoint, error) {

	if limit <= 0 || limit > 1000 {
		limit = 30
	}
	measurements, err := s.GetMeasurementsForPipeline(ctx, pipelineID)
	if err != nil {
		return nil, err
	}

	// Take most recent N
	if len(measurements) > limit {
		measurements = measurements[:limit]
	}

	trend := make([]*SigmaTrendPoint, len(measurements))
	for i, m := range measurements {
		trend[i] = &SigmaTrendPoint{
			Timestamp:  m.Timestamp,
			SigmaLevel: m.SigmaLevel,
			RunID:      m.RunID,
		}
	}
	// Sort oldest first for chart display
	sort.Slice(trend, func(i, j int) bool {
		return trend[i].Timestamp < trend[j].Timestamp
	})
	return trend, nil
}

// ─────────────────────────────────────────────────────────────
// QUALITY CERTIFICATE — for customer SLA proof
// ─────────────────────────────────────────────────────────────
type QualityCertificate struct {
	CertificateID    string  `json:"certificateId"`
	PipelineID       string  `json:"pipelineId"`
	CustomerOrg      string  `json:"customerOrg"`
	PeriodStart      string  `json:"periodStart"`
	PeriodEnd        string  `json:"periodEnd"`

	TotalMeasurements int     `json:"totalMeasurements"`
	AvgSigmaLevel    float64 `json:"avgSigmaLevel"`
	MinSigmaLevel    float64 `json:"minSigmaLevel"`
	MaxSigmaLevel    float64 `json:"maxSigmaLevel"`
	TotalDefects     int64   `json:"totalDefects"`
	TotalRecords     int64   `json:"totalRecords"`

	SLATarget        float64 `json:"slaTarget"`
	SLAMet           bool    `json:"slaMet"`
	BreachCount      int     `json:"breachCount"`

	BlockchainProof  string  `json:"blockchainProof"`
	IssuedAt         string  `json:"issuedAt"`
	IssuerSignature  string  `json:"issuerSignature"`
}

func (s *QualityContract) GenerateCertificate(
	ctx contractapi.TransactionContextInterface,
	pipelineID string,
	periodStart string,
	periodEnd string,
) (*QualityCertificate, error) {

	measurements, err := s.GetMeasurementsForPipeline(ctx, pipelineID)
	if err != nil {
		return nil, err
	}

	// Filter to period
	periodMeasurements := []*QualityMeasurement{}
	for _, m := range measurements {
		if m.Timestamp >= periodStart && m.Timestamp <= periodEnd {
			periodMeasurements = append(periodMeasurements, m)
		}
	}

	if len(periodMeasurements) == 0 {
		return nil, fmt.Errorf("no measurements in period %s to %s", periodStart, periodEnd)
	}

	// Compute stats
	var sumSigma float64
	var totalDefects, totalRecords int64
	minS := periodMeasurements[0].SigmaLevel
	maxS := periodMeasurements[0].SigmaLevel
	for _, m := range periodMeasurements {
		sumSigma += m.SigmaLevel
		totalDefects += m.RecordsFailed
		totalRecords += m.RecordsProcessed
		if m.SigmaLevel < minS { minS = m.SigmaLevel }
		if m.SigmaLevel > maxS { maxS = m.SigmaLevel }
	}
	avgSigma := sumSigma / float64(len(periodMeasurements))

	// Get SLA
	sla, _ := s.GetSLA(ctx, pipelineID)
	slaMet := true
	customerOrg := "Unknown"
	slaTarget := 5.0
	breaches := 0
	if sla != nil {
		slaTarget   = sla.MinSigmaLevel
		customerOrg = sla.CustomerOrg
		for _, m := range periodMeasurements {
			if m.SigmaLevel < sla.MinSigmaLevel {
				breaches++
				slaMet = false
			}
		}
	}

	// Generate certificate
	certID := fmt.Sprintf("CERT-%s-%d", pipelineID, time.Now().Unix())
	proofRaw := fmt.Sprintf("%s|%s|%s|%.2f|%d|%d",
		pipelineID, periodStart, periodEnd, avgSigma, totalRecords, totalDefects)
	proof := sha256.Sum256([]byte(proofRaw))

	cert := &QualityCertificate{
		CertificateID:     certID,
		PipelineID:        pipelineID,
		CustomerOrg:       customerOrg,
		PeriodStart:       periodStart,
		PeriodEnd:         periodEnd,
		TotalMeasurements: len(periodMeasurements),
		AvgSigmaLevel:     avgSigma,
		MinSigmaLevel:     minS,
		MaxSigmaLevel:     maxS,
		TotalDefects:      totalDefects,
		TotalRecords:      totalRecords,
		SLATarget:         slaTarget,
		SLAMet:            slaMet,
		BreachCount:       breaches,
		BlockchainProof:   hex.EncodeToString(proof[:]),
		IssuedAt:          time.Now().UTC().Format(time.RFC3339),
		IssuerSignature:   "DataNexus Quality Chaincode v1.0",
	}

	// Persist on-chain so the certificate itself is auditable
	bytes, _ := json.Marshal(cert)
	ctx.GetStub().PutState("CERT_"+certID, bytes)
	return cert, nil
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
func sigmaToDpm(sigma float64) float64 {
	switch {
	case sigma >= 6.0: return 3.4
	case sigma >= 5.5: return 32.0
	case sigma >= 5.0: return 233.0
	case sigma >= 4.5: return 1350.0
	case sigma >= 4.0: return 6210.0
	case sigma >= 3.5: return 22750.0
	case sigma >= 3.0: return 66807.0
	default: return 308537.0
	}
}

func severityFromGap(gap float64) string {
	switch {
	case gap >= 1.5: return "CRITICAL"
	case gap >= 0.5: return "HIGH"
	default: return "MEDIUM"
	}
}

func computeMeasurementHash(m *QualityMeasurement) string {
	parts := []string{
		m.PipelineID, m.DatasetID, m.RunID, m.Timestamp,
		fmt.Sprintf("%.4f", m.SigmaLevel),
		fmt.Sprintf("%d", m.RecordsProcessed),
		fmt.Sprintf("%d", m.RecordsFailed),
		m.NodeID, m.Region,
	}
	combined := strings.Join(parts, "|")
	hash := sha256.Sum256([]byte(combined))
	return hex.EncodeToString(hash[:])
}

// ─────────────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────────────
func main() {
	chaincode, err := contractapi.NewChaincode(&QualityContract{})
	if err != nil {
		fmt.Printf("Error creating Quality chaincode: %v\n", err)
		return
	}
	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting Quality chaincode: %v\n", err)
	}
}
