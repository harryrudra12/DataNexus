# DataNexus Fix Changelog

Fixed items:

1. `07-tests/conftest.py`
   - Corrected import paths so tests can import modules from `01-platform-modules` and API code from `03-api-service`.

2. Living Node module
   - Added backward-compatible `memory_mb` alias for `NodeCapability`.
   - Added backward-compatible `ledger_peers` alias for `DataNexusNode`.
   - Fixed peer health initialization when `fabric_peers` is omitted.
   - Added `is_online` in status response.

3. Conscious Compliance module
   - Added `LawCode.IN_DPDP_2023` alias.
   - Added safe default data/requester context values for rule evaluation.
   - Prevented demo auto-fix from silently unblocking blocked transfers unless explicitly allowed.

4. AI Operating System module
   - Added `classify_intent` helper.
   - Added `extract_schedule` helper.
   - Added `self_heal` helper.

5. API service
   - Fixed bad auth import.
   - Fixed async pytest fixtures for modern `pytest-asyncio` strict mode.
   - Added local simulation ledger fallback, so ingest -> lineage works without a real Fabric network.
   - Added deterministic local fallback compliance decisions for DPDP/GDPR tests.

6. Docker Compose
   - Fixed invalid `volumes:` YAML.
   - Pointed API build to existing `03-api-service/Dockerfile`.
   - Added `Dockerfile.ui` for the static dashboard.
   - Replaced missing `./era3/...` volume paths with actual project paths.

Validation performed:

- Python compile check passed.
- Platform module tests: 22 passed.
- API service tests: 21 passed.
- `docker-compose.yml` parses as valid YAML.

Remaining note:

- Go chaincode `go.sum` generation requires internet access to download Hyperledger Fabric modules. Run `go mod tidy` in each chaincode folder when online.
