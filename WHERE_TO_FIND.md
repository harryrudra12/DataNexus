# DataNexus — Where to Find What

A 60-second cheat sheet for navigating this repo.

## "I want to..."

### ...understand what DataNexus is
→ `08-docs/DataNexus_Era3_Technical_Spec.pdf`
→ `08-docs/DataNexus_Architecture.pdf`

### ...test that the code works
→ `10-execution/DataNexus_Execution_Guide.md`

### ...see the customer demo
→ Start API: `cd 03-api-service && bash verify.sh && source .venv/bin/activate && uvicorn app.main:app --reload`
→ Open: `04-dashboard/DataNexus_Dashboard_Wired.html`

### ...show investors
→ `08-docs/DataNexus_Investor_Pitch.pptx`
→ `08-docs/DataNexus_Manifest.docx`

### ...send LinkedIn outreach
→ Read first: `09-founder-kit/DataNexus_LinkedIn_Checklist.md`
→ Templates: `09-founder-kit/DataNexus_Outreach_Templates.docx`
→ Track: `09-founder-kit/DataNexus_Outreach_Tracker.xlsx`

### ...prepare for a customer call
→ `09-founder-kit/DataNexus_FirstCall_Worksheet.docx`
→ `09-founder-kit/DataNexus_OnePager.pdf` (send before the call)

### ...run the demo on a customer call
→ `09-founder-kit/DataNexus_Pilot_Demo_Script.pdf` (print and keep on desk)

### ...deploy to production Kubernetes
→ `06-kubernetes/README.md`
→ `helm install datanexus 06-kubernetes/`

### ...understand the blockchain layer
→ `02-blockchain-chaincode/README.md`
→ Run: `python3 02-blockchain-chaincode/client/fabric_client.py`

### ...read the actual code
→ Platform logic: `01-platform-modules/`
→ HTTP API: `03-api-service/app/`
→ Tests: `07-tests/` and `03-api-service/tests/`

## File-by-file inventory

| Folder | Files | Total Lines |
|---|---|---|
| 01-platform-modules | 6 Python files + __init__'s | ~1,650 |
| 02-blockchain-chaincode | 3 Go contracts, 1 Python client | ~1,750 |
| 03-api-service | 20 Python + Dockerfile + tests | ~2,400 |
| 04-dashboard | 2 HTML files, 1 README | ~1,250 |
| 05-data-layer | 2 Python files | ~700 |
| 06-kubernetes | 7 templates + values.yaml | ~600 |
| 07-tests | 3 pytest files | ~300 |
| 08-docs | 5 reference documents | (PDFs/Word) |
| 09-founder-kit | 6 outreach materials | (PDFs/Word) |
| 10-execution | 1 step-by-step guide | ~410 |

**Code total: about 8,650 lines of working source.**
**Plus 11 reference documents and 6 founder-kit materials.**

---

DataNexus · datanexus.io · 2025
