# DataNexus Dashboard — Quick Start

The wired dashboard (`DataNexus_Dashboard_Wired.html`) is a single HTML file that talks to your real FastAPI service. It works in three modes automatically:

1. **API online + signed in** — full live data, every action calls the real backend
2. **API online, not signed in** — public endpoints (health, fabric status) work; protected ones prompt to sign in
3. **API offline** — falls back to demo data and shows a clear "API offline" banner

You don't need to configure anything to switch modes. The dashboard health-checks the API every 30 seconds and adapts.

---

## How to run it locally

### Step 1 — Start the API service
```bash
unzip DataNexus_API_Service.zip
cd api-service
bash verify.sh                # one-time setup + tests
source .venv/bin/activate
uvicorn app.main:app --reload
```

The API now runs at `http://localhost:8000`. Open `http://localhost:8000/docs` to see the auto-generated Swagger UI.

### Step 2 — Open the dashboard
Just double-click `DataNexus_Dashboard_Wired.html` in your file manager. It opens in your browser. No build step. No npm install.

The dashboard will detect the API at `http://localhost:8000` automatically and switch from the orange "demo" banner to the green "live" indicator.

### Step 3 — Sign in
Click the gear icon in the top-right corner. A settings panel slides in.

Demo credentials:
- `admin` / `admin123` (super admin — sees everything)
- `apollo_admin` / `apollo2025` (tenant admin — Apollo Hospital)
- `auditor_dpdp` / `audit2025` (auditor only)

After you sign in, the protected tabs (Compliance, Query, Intent) become interactive.

---

## What each tab does (live)

| Tab | What it shows | API endpoints called |
|-----|---------------|----------------------|
| **Overview** | Hero card, KPIs, fabric health | `GET /api/v1/fabric/status` |
| **Pipelines** | Pipeline cards with sigma gauges | (uses demo data — pipeline endpoint coming next) |
| **Fabric** | All living data nodes, regions, sigma | `GET /api/v1/fabric/status` (with refresh) |
| **Audit** | Hyperledger Fabric audit chain | (uses demo data — audit endpoint coming next) |
| **Compliance** | Border check simulator — runs 4 real checks | `POST /api/v1/compliance/border` × 4 |
| **Query** | NLP query in Telugu/Hindi/English | `POST /api/v1/query/nlp` |
| **Intent** | Natural language → deployed Airflow DAG | `POST /api/v1/pipeline/intent` |

---

## The demo flow that closes a CTO

This is the 60-second sequence:

1. Open the dashboard. Point at the green pulsing dot in the header. Say: *"This is a live connection to a Hyperledger Fabric network. Every transaction is permanent."*
2. Click **Compliance**. Click **Run all 4 checks**.
3. Watch all 4 border checks complete in under 2 seconds. The Apollo → Mumbai check is ALLOWED. The Apollo → US pharma check is BLOCKED with reason "DPDP-001". Each check has a real Fabric transaction ID.
4. Say: *"This is what no cloud vendor can do. AWS cannot prove your DPDP compliance to a regulator. We just did it in 2 seconds."*
5. Click **Query** tab. Click the Telugu sample. Click **Run query**.
6. Watch a Telugu sentence become Presto SQL. Real result rows appear.
7. Say: *"Five hundred million Indians can use this in their language. No SQL knowledge required."*

That's the demo. Practice it 50 times before showing to a real CTO.

---

## Production deployment notes

When you deploy this to a customer:

1. Host the HTML file behind nginx or any static file server
2. Set the API URL via the settings panel — point it at your real API (e.g., `https://api.datanexus.io`)
3. The settings persist in localStorage so the user doesn't have to re-enter it
4. Set up CORS in the FastAPI service: add the dashboard's domain to `CORS_ORIGINS` env var
5. Use HTTPS only for the API in production — JWTs leak over HTTP

---

## What to build next

This dashboard is wired but two endpoints are still demo data:
- `/api/v1/pipelines` — list of all pipelines with live sigma scores
- `/api/v1/audit` — recent audit chain with pagination

These are 30-minute additions to the FastAPI service when you're ready.

The bigger remaining piece is the **pilot demo script** — the exact words and clicks for that 60-second sequence above, formatted as a printable single-page document a founder can rehearse 50 times. Tell me when you want to build that.

---

DataNexus · datanexus.io · Apache 2.0 · 2025
*Built on Hadoop · Guided by the Gita · Six Sigma enforced*
