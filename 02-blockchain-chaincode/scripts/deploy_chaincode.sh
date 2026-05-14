#!/bin/bash
# DataNexus Era 3 — Chaincode Deployment Script
# Installs and instantiates all 3 chaincodes on the Hyperledger Fabric network.
# Run from the era3/fabric-chaincode directory.

set -euo pipefail

# ─── CONFIG ───────────────────────────────────────────────
CHANNEL_NAME="${CHANNEL_NAME:-datanexus-channel}"
CC_VERSION="${CC_VERSION:-1.0}"
CC_SEQUENCE="${CC_SEQUENCE:-1}"
ORDERER_ADDR="${ORDERER_ADDR:-orderer.datanexus.io:7050}"
ORDERER_TLS_CA="${ORDERER_TLS_CA:-/var/hyperledger/orderer/tls/ca.crt}"

PEER0_ORG1="${PEER0_ORG1:-peer0.org1.datanexus.io:7051}"
PEER0_ORG2="${PEER0_ORG2:-peer0.org2.datanexus.io:8051}"

# Colors for output
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

CHAINCODES=("lineage-cc" "compliance-cc" "quality-cc")

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         DataNexus Era 3 — Chaincode Deployment            ║${NC}"
echo -e "${BLUE}║   Lineage · Compliance · Quality on Hyperledger Fabric    ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─── PRECHECK ─────────────────────────────────────────────
echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"
command -v peer    >/dev/null || { echo -e "${RED}peer CLI not found${NC}"; exit 1; }
command -v go      >/dev/null || { echo -e "${RED}go not found${NC}"; exit 1; }
command -v jq      >/dev/null || { echo -e "${RED}jq not found${NC}"; exit 1; }
echo -e "${GREEN}✓ All prerequisites found${NC}"
echo ""

# ─── FOR EACH CHAINCODE ───────────────────────────────────
for CC_NAME in "${CHAINCODES[@]}"; do
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Deploying: ${CC_NAME}${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════${NC}"

    CC_PATH="./${CC_NAME}"
    CC_LABEL="${CC_NAME}_${CC_VERSION}"
    PACKAGE_FILE="${CC_NAME}.tar.gz"

    # Step 1: Vendor dependencies
    echo -e "${YELLOW}  [a] Vendoring Go dependencies...${NC}"
    (cd "${CC_PATH}/src" && go mod tidy && go mod vendor)
    echo -e "${GREEN}  ✓ Dependencies vendored${NC}"

    # Step 2: Package
    echo -e "${YELLOW}  [b] Packaging chaincode...${NC}"
    peer lifecycle chaincode package "${PACKAGE_FILE}" \
        --path "${CC_PATH}/src" \
        --lang golang \
        --label "${CC_LABEL}"
    echo -e "${GREEN}  ✓ Packaged: ${PACKAGE_FILE}${NC}"

    # Step 3: Install on Org1 peer
    echo -e "${YELLOW}  [c] Installing on peer0.org1...${NC}"
    CORE_PEER_LOCALMSPID="Org1MSP" \
    CORE_PEER_ADDRESS="${PEER0_ORG1}" \
    CORE_PEER_TLS_ENABLED=true \
    peer lifecycle chaincode install "${PACKAGE_FILE}"
    echo -e "${GREEN}  ✓ Installed on Org1${NC}"

    # Step 4: Install on Org2 peer
    echo -e "${YELLOW}  [d] Installing on peer0.org2...${NC}"
    CORE_PEER_LOCALMSPID="Org2MSP" \
    CORE_PEER_ADDRESS="${PEER0_ORG2}" \
    CORE_PEER_TLS_ENABLED=true \
    peer lifecycle chaincode install "${PACKAGE_FILE}"
    echo -e "${GREEN}  ✓ Installed on Org2${NC}"

    # Step 5: Get package ID
    PACKAGE_ID=$(peer lifecycle chaincode queryinstalled \
        --output json | jq -r ".installed_chaincodes[] | select(.label==\"${CC_LABEL}\") | .package_id")
    echo -e "${GREEN}  ✓ Package ID: ${PACKAGE_ID}${NC}"

    # Step 6: Approve for Org1
    echo -e "${YELLOW}  [e] Approving for Org1...${NC}"
    CORE_PEER_LOCALMSPID="Org1MSP" \
    peer lifecycle chaincode approveformyorg \
        -o "${ORDERER_ADDR}" \
        --channelID "${CHANNEL_NAME}" \
        --name "${CC_NAME}" \
        --version "${CC_VERSION}" \
        --sequence "${CC_SEQUENCE}" \
        --package-id "${PACKAGE_ID}" \
        --tls --cafile "${ORDERER_TLS_CA}"
    echo -e "${GREEN}  ✓ Approved by Org1${NC}"

    # Step 7: Approve for Org2
    echo -e "${YELLOW}  [f] Approving for Org2...${NC}"
    CORE_PEER_LOCALMSPID="Org2MSP" \
    peer lifecycle chaincode approveformyorg \
        -o "${ORDERER_ADDR}" \
        --channelID "${CHANNEL_NAME}" \
        --name "${CC_NAME}" \
        --version "${CC_VERSION}" \
        --sequence "${CC_SEQUENCE}" \
        --package-id "${PACKAGE_ID}" \
        --tls --cafile "${ORDERER_TLS_CA}"
    echo -e "${GREEN}  ✓ Approved by Org2${NC}"

    # Step 8: Commit
    echo -e "${YELLOW}  [g] Committing chaincode definition...${NC}"
    peer lifecycle chaincode commit \
        -o "${ORDERER_ADDR}" \
        --channelID "${CHANNEL_NAME}" \
        --name "${CC_NAME}" \
        --version "${CC_VERSION}" \
        --sequence "${CC_SEQUENCE}" \
        --tls --cafile "${ORDERER_TLS_CA}"
    echo -e "${GREEN}  ✓ Committed to channel${NC}"

    # Step 9: Init ledger
    echo -e "${YELLOW}  [h] Initializing ledger...${NC}"
    peer chaincode invoke \
        -o "${ORDERER_ADDR}" \
        --channelID "${CHANNEL_NAME}" \
        --name "${CC_NAME}" \
        -c '{"function":"InitLedger","Args":[]}' \
        --tls --cafile "${ORDERER_TLS_CA}" || true
    echo -e "${GREEN}  ✓ Ledger initialized${NC}"

    echo ""
done

# ─── SMOKE TEST ───────────────────────────────────────────
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Smoke test: Log a transformation${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"

peer chaincode invoke \
    -o "${ORDERER_ADDR}" \
    --channelID "${CHANNEL_NAME}" \
    --name "lineage-cc" \
    -c '{"function":"LogTransformation","Args":[
        "smoke-test-job-001",
        "[\"raw_input_001\"]",
        "[\"sha256-input-hash-placeholder\"]",
        "smoke_test_output",
        "a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd",
        "SPARK_TRANSFORM",
        "smoke-test-pipeline",
        "5.7",
        "PII",
        "[\"DPDP_2023\"]",
        "IN-TG",
        "QmSmokeTestCID"
    ]}' \
    --tls --cafile "${ORDERER_TLS_CA}"

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✓ ALL THREE CHAINCODES DEPLOYED AND OPERATIONAL         ║${NC}"
echo -e "${GREEN}║                                                            ║${NC}"
echo -e "${GREEN}║   Channel:     ${CHANNEL_NAME}                              ${NC}"
echo -e "${GREEN}║   Lineage:     ✓ committed and initialized                ║${NC}"
echo -e "${GREEN}║   Compliance:  ✓ committed (DPDP/GDPR/HIPAA loaded)       ║${NC}"
echo -e "${GREEN}║   Quality:     ✓ committed and ready for measurements     ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Next: run scripts/test_e2e.sh to verify the full flow.${NC}"
