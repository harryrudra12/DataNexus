#!/usr/bin/env bash
set -euo pipefail
python -m pip install pytest pytest-asyncio fastapi pydantic pydantic-settings httpx structlog 'python-jose[cryptography]' 'passlib[bcrypt]' prometheus-client uvicorn
python -m pytest -q 07-tests
(cd 03-api-service && python -m pytest -q tests)
