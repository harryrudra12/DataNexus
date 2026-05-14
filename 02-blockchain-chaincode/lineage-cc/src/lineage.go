// SPDX-License-Identifier: Apache-2.0
// DataNexus Era 3 — Lineage Chaincode
// Records every data transformation as immutable Hyperledger Fabric transactions.
// Provides cryptographic proof of data provenance for regulators, courts, auditors.

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

// LineageContract handles all data lineage records
type LineageContract struct {
	contractapi.Contract
}

// TransformationRecord — one immutable lineage event
type TransformationRecord struct {
	TxID            string   `json:"txId"`
	JobID           string   `json:"jobId"`
	Timestamp       string   `json:"timestamp"`

	// Inputs and outputs (content-addressed)
	InputDatasetIDs []string `json:"inputDatasetIds"`
	InputHashes     []string `json:"inputHashes"`
	OutputDatasetID string   `json:"outputDatasetId"`
	OutputHash      string   `json:"outputHash"`

	// Lineage metadata
	TransformationType string `json:"transformationType"`  // SPARK | SQL | ML | FILTER | JOIN
	PipelineID         string `json:"pipelineId"`
	PipelineVersion    string `json:"pipelineVersion"`
	OperatorCode       string `json:"operatorCode"`        // Python/SQL hash

	// Quality and compliance
	SigmaLevel   float64           `json:"sigmaLevel"`
	Classification string          `json:"classification"`  // PII | HEALTH | FINANCIAL
	Jurisdictions  []string        `json:"jurisdictions"`   // DPDP | GDPR | HIPAA

	// Identity
	OwnerOrg     string `json:"ownerOrg"`
	OperatorMSP  string `json:"operatorMSP"`              // who triggered this
	NodeID       string `json:"nodeId"`                   // which fabric node
	Region       string `json:"region"`                   // IN-TG, IN-MH, EU-DE

	// IPFS storage
	IpfsCid      string `json:"ipfsCid,omitempty"`

	// Genome — hash of all above fields (tamper detection)
	GenomeHash   string `json:"genomeHash"`
}

// LineageQuery — pagination support
type LineageQuery struct {
	DatasetID  string `json:"datasetId,omitempty"`
	PipelineID string `json:"pipelineId,omitempty"`
	FromTime   string `json:"fromTime,omitempty"`
	ToTime     string `json:"toTime,omitempty"`
	Limit      int    `json:"limit,omitempty"`
}

// ─────────────────────────────────────────────────────────────
// CHAINCODE INITIALIZATION
// ─────────────────────────────────────────────────────────────
func (s *LineageContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	// Genesis lineage record — proves the chaincode itself is initialized
	genesis := TransformationRecord{
		TxID:               "GENESIS",
		JobID:              "datanexus-genesis",
		Timestamp:          time.Now().UTC().Format(time.RFC3339),
		OutputDatasetID:    "datanexus-genesis-block",
		OutputHash:         "0000000000000000000000000000000000000000000000000000000000000000",
		TransformationType: "GENESIS",
		PipelineID:         "system",
		PipelineVersion:    "1.0.0",
		SigmaLevel:         6.0,
		OwnerOrg:           "DataNexus",
		Region:             "GLOBAL",
	}
	genesis.GenomeHash = computeGenomeHash(genesis)

	bytes, _ := json.Marshal(genesis)
	return ctx.GetStub().PutState("LINEAGE_GENESIS", bytes)
}

// ─────────────────────────────────────────────────────────────
// LOG TRANSFORMATION — main write entry point
// ─────────────────────────────────────────────────────────────
func (s *LineageContract) LogTransformation(
	ctx contractapi.TransactionContextInterface,
	jobID string,
	inputDatasetIDsJSON string,
	inputHashesJSON string,
	outputDatasetID string,
	outputHash string,
	transformationType string,
	pipelineID string,
	sigmaLevel float64,
	classification string,
	jurisdictionsJSON string,
	region string,
	ipfsCid string,
) (*TransformationRecord, error) {

	// Validate inputs
	if outputDatasetID == "" || outputHash == "" {
		return nil, fmt.Errorf("outputDatasetID and outputHash are required")
	}
	if len(outputHash) != 64 {
		return nil, fmt.Errorf("outputHash must be SHA-256 (64 hex chars), got %d", len(outputHash))
	}
	if sigmaLevel < 1.0 || sigmaLevel > 6.0 {
		return nil, fmt.Errorf("sigmaLevel must be 1.0–6.0, got %.2f", sigmaLevel)
	}

	// Parse JSON arrays
	var inputDatasetIDs []string
	if err := json.Unmarshal([]byte(inputDatasetIDsJSON), &inputDatasetIDs); err != nil {
		return nil, fmt.Errorf("invalid inputDatasetIDsJSON: %v", err)
	}
	var inputHashes []string
	if err := json.Unmarshal([]byte(inputHashesJSON), &inputHashes); err != nil {
		return nil, fmt.Errorf("invalid inputHashesJSON: %v", err)
	}
	var jurisdictions []string
	if err := json.Unmarshal([]byte(jurisdictionsJSON), &jurisdictions); err != nil {
		return nil, fmt.Errorf("invalid jurisdictionsJSON: %v", err)
	}

	// Get caller identity (who is invoking this chaincode)
	clientMSP, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return nil, fmt.Errorf("could not get client MSP ID: %v", err)
	}
	clientID, err := ctx.GetClientIdentity().GetID()
	if err != nil {
		return nil, fmt.Errorf("could not get client ID: %v", err)
	}

	// Get Fabric transaction ID and timestamp
	txID := ctx.GetStub().GetTxID()
	txTime, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return nil, fmt.Errorf("could not get tx timestamp: %v", err)
	}
	timestamp := time.Unix(txTime.Seconds, int64(txTime.Nanos)).UTC().Format(time.RFC3339)

	// Build the lineage record
	record := TransformationRecord{
		TxID:               txID,
		JobID:              jobID,
		Timestamp:          timestamp,
		InputDatasetIDs:    inputDatasetIDs,
		InputHashes:        inputHashes,
		OutputDatasetID:    outputDatasetID,
		OutputHash:         outputHash,
		TransformationType: transformationType,
		PipelineID:         pipelineID,
		SigmaLevel:         sigmaLevel,
		Classification:     classification,
		Jurisdictions:      jurisdictions,
		OperatorMSP:        clientMSP,
		NodeID:             clientID[:32], // truncated identity
		Region:             region,
		IpfsCid:            ipfsCid,
	}

	// Compute genome hash (tamper-detection)
	record.GenomeHash = computeGenomeHash(record)

	// Serialize and store
	recordJSON, err := json.Marshal(record)
	if err != nil {
		return nil, err
	}

	// Composite key: dataset_id + timestamp for fast lineage queries
	compositeKey, err := ctx.GetStub().CreateCompositeKey(
		"lineage",
		[]string{outputDatasetID, txID},
	)
	if err != nil {
		return nil, err
	}

	if err := ctx.GetStub().PutState(compositeKey, recordJSON); err != nil {
		return nil, fmt.Errorf("failed to write lineage record: %v", err)
	}

	// Also index by pipeline_id for pipeline-level queries
	pipelineKey, err := ctx.GetStub().CreateCompositeKey(
		"pipeline",
		[]string{pipelineID, txID},
	)
	if err != nil {
		return nil, err
	}
	if err := ctx.GetStub().PutState(pipelineKey, []byte(outputDatasetID)); err != nil {
		return nil, err
	}

	// Emit event for off-chain listeners (DataNexus API, Atlas catalog)
	eventPayload, _ := json.Marshal(map[string]string{
		"txId":            txID,
		"outputDatasetID": outputDatasetID,
		"sigma":           fmt.Sprintf("%.2f", sigmaLevel),
		"region":          region,
	})
	ctx.GetStub().SetEvent("LineageRecorded", eventPayload)

	return &record, nil
}

// ─────────────────────────────────────────────────────────────
// QUERY LINEAGE FOR A DATASET
// ─────────────────────────────────────────────────────────────
func (s *LineageContract) GetLineage(
	ctx contractapi.TransactionContextInterface,
	datasetID string,
) ([]*TransformationRecord, error) {

	if datasetID == "" {
		return nil, fmt.Errorf("datasetID is required")
	}

	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey(
		"lineage",
		[]string{datasetID},
	)
	if err != nil {
		return nil, err
	}
	defer iterator.Close()

	var records []*TransformationRecord
	for iterator.HasNext() {
		queryResponse, err := iterator.Next()
		if err != nil {
			return nil, err
		}
		var record TransformationRecord
		if err := json.Unmarshal(queryResponse.Value, &record); err != nil {
			return nil, err
		}
		records = append(records, &record)
	}

	// Sort newest first
	sort.Slice(records, func(i, j int) bool {
		return records[i].Timestamp > records[j].Timestamp
	})

	return records, nil
}

// ─────────────────────────────────────────────────────────────
// VERIFY INTEGRITY — has the lineage been tampered with?
// ─────────────────────────────────────────────────────────────
func (s *LineageContract) VerifyIntegrity(
	ctx contractapi.TransactionContextInterface,
	datasetID string,
	expectedHash string,
) (bool, error) {

	records, err := s.GetLineage(ctx, datasetID)
	if err != nil {
		return false, err
	}
	if len(records) == 0 {
		return false, fmt.Errorf("no lineage found for dataset %s", datasetID)
	}

	// Check each record's genome hash matches re-computed hash
	for _, r := range records {
		recomputed := computeGenomeHash(*r)
		if recomputed != r.GenomeHash {
			return false, fmt.Errorf(
				"TAMPERING DETECTED in tx %s: stored=%s, recomputed=%s",
				r.TxID, r.GenomeHash, recomputed)
		}
	}

	// Check the latest output hash matches the expected hash (if provided)
	if expectedHash != "" && records[0].OutputHash != expectedHash {
		return false, fmt.Errorf(
			"output hash mismatch: ledger has %s, expected %s",
			records[0].OutputHash, expectedHash)
	}

	return true, nil
}

// ─────────────────────────────────────────────────────────────
// FULL LINEAGE GRAPH — recursive parent traversal
// ─────────────────────────────────────────────────────────────
func (s *LineageContract) GetLineageGraph(
	ctx contractapi.TransactionContextInterface,
	datasetID string,
	maxDepth int,
) (map[string][]*TransformationRecord, error) {

	if maxDepth <= 0 {
		maxDepth = 10
	}
	graph := make(map[string][]*TransformationRecord)
	visited := make(map[string]bool)

	var traverse func(id string, depth int) error
	traverse = func(id string, depth int) error {
		if depth >= maxDepth || visited[id] {
			return nil
		}
		visited[id] = true

		records, err := s.GetLineage(ctx, id)
		if err != nil {
			return err
		}
		graph[id] = records

		// Recurse into all parent datasets
		for _, r := range records {
			for _, parent := range r.InputDatasetIDs {
				if !visited[parent] {
					if err := traverse(parent, depth+1); err != nil {
						return err
					}
				}
			}
		}
		return nil
	}

	if err := traverse(datasetID, 0); err != nil {
		return nil, err
	}
	return graph, nil
}

// ─────────────────────────────────────────────────────────────
// AUDIT REPORT — for regulators, court-admissible evidence
// ─────────────────────────────────────────────────────────────
type AuditReport struct {
	ReportID         string                  `json:"reportId"`
	GeneratedAt      string                  `json:"generatedAt"`
	GeneratedBy      string                  `json:"generatedBy"`
	DatasetID        string                  `json:"datasetId"`
	TotalRecords     int                     `json:"totalRecords"`
	IntegrityOK      bool                    `json:"integrityOk"`
	AvgSigmaLevel    float64                 `json:"avgSigmaLevel"`
	JurisdictionList []string                `json:"jurisdictionList"`
	FullChain        []*TransformationRecord `json:"fullChain"`
	BlockchainProof  string                  `json:"blockchainProof"`
}

func (s *LineageContract) GenerateAuditReport(
	ctx contractapi.TransactionContextInterface,
	datasetID string,
) (*AuditReport, error) {

	records, err := s.GetLineage(ctx, datasetID)
	if err != nil {
		return nil, err
	}
	if len(records) == 0 {
		return nil, fmt.Errorf("no lineage found for %s", datasetID)
	}

	// Verify integrity of all records
	integrityOK := true
	for _, r := range records {
		if computeGenomeHash(*r) != r.GenomeHash {
			integrityOK = false
			break
		}
	}

	// Compute summary stats
	var sigmaSum float64
	jurisdictionSet := make(map[string]bool)
	for _, r := range records {
		sigmaSum += r.SigmaLevel
		for _, j := range r.Jurisdictions {
			jurisdictionSet[j] = true
		}
	}
	jurisdictions := make([]string, 0, len(jurisdictionSet))
	for j := range jurisdictionSet {
		jurisdictions = append(jurisdictions, j)
	}
	sort.Strings(jurisdictions)

	// Generate report ID and blockchain proof
	reportID := fmt.Sprintf("AUDIT-%s-%d",
		datasetID[:min(8, len(datasetID))],
		time.Now().Unix())

	proofData := strings.Join([]string{
		datasetID,
		records[0].TxID,
		records[len(records)-1].TxID,
		fmt.Sprintf("%d", len(records)),
	}, "|")
	proof := sha256.Sum256([]byte(proofData))
	blockchainProof := hex.EncodeToString(proof[:])

	report := &AuditReport{
		ReportID:         reportID,
		GeneratedAt:      time.Now().UTC().Format(time.RFC3339),
		GeneratedBy:      "DataNexus Lineage Chaincode v1.0",
		DatasetID:        datasetID,
		TotalRecords:     len(records),
		IntegrityOK:      integrityOK,
		AvgSigmaLevel:    sigmaSum / float64(len(records)),
		JurisdictionList: jurisdictions,
		FullChain:        records,
		BlockchainProof:  blockchainProof,
	}

	// Store the report on-chain so it is itself auditable
	reportJSON, _ := json.Marshal(report)
	ctx.GetStub().PutState("REPORT_"+reportID, reportJSON)

	return report, nil
}

// ─────────────────────────────────────────────────────────────
// RICH QUERY — uses CouchDB indexes (production deployment)
// ─────────────────────────────────────────────────────────────
func (s *LineageContract) QueryByPipeline(
	ctx contractapi.TransactionContextInterface,
	pipelineID string,
) ([]*TransformationRecord, error) {

	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey(
		"pipeline",
		[]string{pipelineID},
	)
	if err != nil {
		return nil, err
	}
	defer iterator.Close()

	var records []*TransformationRecord
	for iterator.HasNext() {
		entry, err := iterator.Next()
		if err != nil {
			return nil, err
		}
		// The pipeline index stores datasetID as value
		datasetID := string(entry.Value)
		datasetRecords, err := s.GetLineage(ctx, datasetID)
		if err != nil {
			continue
		}
		records = append(records, datasetRecords...)
	}
	return records, nil
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────
func computeGenomeHash(r TransformationRecord) string {
	// Hash all fields except GenomeHash itself
	parts := []string{
		r.TxID, r.JobID, r.Timestamp,
		strings.Join(r.InputDatasetIDs, ","),
		strings.Join(r.InputHashes, ","),
		r.OutputDatasetID, r.OutputHash,
		r.TransformationType, r.PipelineID, r.PipelineVersion,
		fmt.Sprintf("%.4f", r.SigmaLevel),
		r.Classification,
		strings.Join(r.Jurisdictions, ","),
		r.OwnerOrg, r.OperatorMSP, r.NodeID, r.Region, r.IpfsCid,
	}
	combined := strings.Join(parts, "|")
	hash := sha256.Sum256([]byte(combined))
	return hex.EncodeToString(hash[:])
}

func min(a, b int) int {
	if a < b { return a }
	return b
}

// ─────────────────────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────────────────────
func main() {
	chaincode, err := contractapi.NewChaincode(&LineageContract{})
	if err != nil {
		fmt.Printf("Error creating Lineage chaincode: %v\n", err)
		return
	}
	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting Lineage chaincode: %v\n", err)
	}
}
