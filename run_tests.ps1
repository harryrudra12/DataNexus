$ErrorActionPreference = "Stop"
python -m pip install pytest pytest-asyncio fastapi pydantic pydantic-settings httpx structlog python-jose[cryptography] passlib[bcrypt] prometheus-client uvicorn
python -m pytest -q 07-tests
Push-Location 03-api-service
python -m pytest -q tests
Pop-Location
