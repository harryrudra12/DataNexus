# DataNexus Fixed Project - Test Guide

## Windows PowerShell

```powershell
cd <project-folder>\datanexus-complete
python -m pip install pytest pytest-asyncio fastapi pydantic pydantic-settings httpx structlog python-jose[cryptography] passlib[bcrypt] prometheus-client uvicorn
python -m pytest -q 07-tests
cd 03-api-service
python -m pytest -q tests
```

## Linux / macOS

```bash
cd datanexus-complete
python -m pip install pytest pytest-asyncio fastapi pydantic pydantic-settings httpx structlog 'python-jose[cryptography]' 'passlib[bcrypt]' prometheus-client uvicorn
python -m pytest -q 07-tests
cd 03-api-service
python -m pytest -q tests
```

## Docker Compose

The main `docker-compose.yml` now parses as valid YAML and references the existing API Dockerfile and the new static dashboard Dockerfile.

```bash
docker compose config
docker compose up -d datanexus-api datanexus-ui
```

Note: the full big-data stack includes heavy services such as Hadoop, Kafka, Airflow, Trino, Atlas, Fabric, IPFS and MLflow. Bring those up gradually on a machine with enough RAM/disk.

## Go Chaincode

The Go chaincode modules reference Hyperledger Fabric dependencies. Generate `go.sum` after internet access is available:

```bash
cd 02-blockchain-chaincode/compliance-cc && go mod tidy
cd ../lineage-cc && go mod tidy
cd ../quality-cc && go mod tidy
```
