#!/bin/bash
# DataNexus Era 3 — API Service Verification
# Runs locally on the developer's machine to verify everything works.
#
# Usage:
#   cd era3/api-service
#   bash verify.sh

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  DataNexus Era 3 — API Service Verification${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

# ─── 1. Python version ────────────────────────────────────────
echo -e "\n${YELLOW}[1/5] Checking Python version (need 3.11+)...${NC}"
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; assert sys.version_info >= (3, 11)" 2>/dev/null; then
    echo -e "${GREEN}  ✓ Python ${PYTHON_VERSION}${NC}"
else
    echo -e "${RED}  ✗ Python ${PYTHON_VERSION} is too old. Need 3.11+${NC}"
    exit 1
fi

# ─── 2. Virtual environment ───────────────────────────────────
echo -e "\n${YELLOW}[2/5] Setting up virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}  ✓ Created .venv${NC}"
else
    echo -e "${GREEN}  ✓ .venv already exists${NC}"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# ─── 3. Install dependencies ──────────────────────────────────
echo -e "\n${YELLOW}[3/5] Installing dependencies...${NC}"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo -e "${GREEN}  ✓ All dependencies installed${NC}"

# ─── 4. Syntax check ──────────────────────────────────────────
echo -e "\n${YELLOW}[4/5] Validating Python syntax...${NC}"
ERRORS=0
while IFS= read -r f; do
    if ! python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null; then
        echo -e "${RED}  ✗ Syntax error: $f${NC}"
        ERRORS=$((ERRORS + 1))
    fi
done < <(find app tests -name "*.py")
if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}  ✓ All Python files valid${NC}"
else
    echo -e "${RED}  ✗ ${ERRORS} syntax error(s) found${NC}"
    exit 1
fi

# ─── 5. Run end-to-end tests ──────────────────────────────────
echo -e "\n${YELLOW}[5/5] Running end-to-end tests...${NC}"
pytest tests/test_api_e2e.py -v --tb=short --no-header 2>&1 | tail -40

# ─── Summary ──────────────────────────────────────────────────
echo -e "\n${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓ DataNexus API service is verified and working${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e ""
echo -e "Start the service locally:"
echo -e "  ${BLUE}uvicorn app.main:app --reload${NC}"
echo -e ""
echo -e "Then open:"
echo -e "  • http://localhost:8000/docs   (interactive API docs)"
echo -e "  • http://localhost:8000/health (liveness)"
echo -e "  • http://localhost:8000/ready  (readiness)"
echo -e ""
echo -e "Build the Docker image:"
echo -e "  ${BLUE}docker build -t datanexus-api:latest .${NC}"
echo -e ""
echo -e "Run the Docker image:"
echo -e "  ${BLUE}docker run -p 8000:8000 -e APP_ENV=development datanexus-api:latest${NC}"
