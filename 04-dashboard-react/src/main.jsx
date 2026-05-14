import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = localStorage.getItem("dn_api_url") || "http://localhost:18000";

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }

  return res.json();
}

async function apiPost(path, body = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }

  return res.json();
}


function downloadJsonReport(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();

  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function downloadBinaryReport(filename, blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();

  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

async function apiBlob(path) {
  const res = await fetch(`${API_BASE}${path}`);

  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }

  return res.blob();
}
function StatusBadge({ online }) {
  return (
    <div className="status">
      <span className={`dot ${online === true ? "online" : online === false ? "offline" : ""}`} />
      <span>
        {online === null
          ? "Connecting..."
          : online
          ? "Fabric operational"
          : "API offline"}
      </span>
    </div>
  );
}

function KPICard({ label, value, sub, tone }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="value" style={{ color: tone || "var(--navy)" }}>
        {value}
      </div>
      {sub && <div className="small">{sub}</div>}
    </div>
  );
}

const inputStyle = {
  width: "100%",
  border: "1px solid var(--line)",
  borderRadius: 14,
  padding: "11px 13px",
  background: "rgba(255,255,255,0.74)",
  color: "var(--navy)",
  outline: "none",
  fontSize: 13,
};

const primaryButtonStyle = {
  border: "none",
  borderRadius: 999,
  padding: "10px 16px",
  background: "var(--navy)",
  color: "var(--paper)",
  cursor: "pointer",
  fontWeight: 700,
};


function safeText(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  return String(value);
}

function safeNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}
function Overview({ live, online }) {
  const cards = live?.overview?.cards || {};

  return (
    <div className="page">
      <div className="grid" style={{ gridTemplateColumns: "1.35fr 1fr", marginBottom: 16 }}>
        <div className="hero">
          <span className={`badge ${online ? "green" : "amber"}`}>
            {online ? "Live API Online" : "Demo fallback"}
          </span>
          <h1>
            The data fabric
            <br />
            <span style={{ color: "var(--amber)", fontStyle: "italic" }}>
              that knows itself.
            </span>
          </h1>
          <p style={{ color: "#C4BFAF", maxWidth: 650, lineHeight: 1.65 }}>
            DataNexus verifies pipelines, audits compliance decisions, and exposes
            live fabric intelligence through APIs. This React dashboard is reading
            backend data from {API_BASE}.
          </p>
        </div>

        <div className="grid kpi" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <KPICard label="Datasets" value={(cards.datasets || 0).toLocaleString()} sub="across fabric" />
          <KPICard label="Nodes" value={cards.fabric_nodes || 0} sub={`${cards.online_nodes || 0} online`} tone="var(--green)" />
          <KPICard label="Avg sigma" value={`${cards.avg_sigma || 0}σ`} sub="quality score" tone="var(--purple)" />
          <KPICard label="Warnings" value={cards.warnings || 0} sub="active alerts" tone="var(--amber)" />
        </div>
      </div>

      <div className="grid kpi">
        <KPICard label="Pipeline runs" value={(cards.pipeline_runs || 0).toLocaleString()} sub="total processed" />
        <KPICard label="Heal rate" value={`${cards.heal_rate || 0}%`} sub="auto resolved" tone="var(--purple)" />
        <KPICard label="DPMO" value={cards.defects_per_million || 0} sub="defects per million" tone="var(--green)" />
        <KPICard label="DPDP audit" value={`${cards.dpdp_audit_seconds || 0}s`} sub="time to proof" tone="var(--amber)" />
      </div>
    </div>
  );
}

function CreatePipelineForm({
  form,
  setForm,
  onCreatePipeline,
  creatingPipeline,
}) {
  const update = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div className="label">Create new pipeline</div>
          <h2 style={{ margin: "6px 0 0" }}>Fabric pipeline builder</h2>
          <div className="small">
            Add a simulated pipeline. Backend will create a fabric transaction and audit event.
          </div>
        </div>

        <span className="badge green">Live API</span>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
        <div>
          <div className="label" style={{ marginBottom: 6 }}>Pipeline name</div>
          <input
            style={inputStyle}
            value={form.name}
            placeholder="payments_fraud_stream"
            onChange={(e) => update("name", e.target.value)}
          />
        </div>

        <div>
          <div className="label" style={{ marginBottom: 6 }}>Source</div>
          <input
            style={inputStyle}
            value={form.source}
            placeholder="kafka"
            onChange={(e) => update("source", e.target.value)}
          />
        </div>

        <div>
          <div className="label" style={{ marginBottom: 6 }}>Target</div>
          <input
            style={inputStyle}
            value={form.target}
            placeholder="fabric_node_mumbai"
            onChange={(e) => update("target", e.target.value)}
          />
        </div>

        <div>
          <div className="label" style={{ marginBottom: 6 }}>Region</div>
          <input
            style={inputStyle}
            value={form.region}
            placeholder="IN-MH"
            onChange={(e) => update("region", e.target.value)}
          />
        </div>

        <div>
          <div className="label" style={{ marginBottom: 6 }}>Law</div>
          <select
            style={inputStyle}
            value={form.law}
            onChange={(e) => update("law", e.target.value)}
          >
            <option value="DPDP">DPDP</option>
            <option value="GDPR">GDPR</option>
            <option value="HIPAA">HIPAA</option>
            <option value="SOX">SOX</option>
          </select>
        </div>

        <div>
          <div className="label" style={{ marginBottom: 6 }}>Owner</div>
          <input
            style={inputStyle}
            value={form.owner}
            placeholder="risk_team"
            onChange={(e) => update("owner", e.target.value)}
          />
        </div>
      </div>

      <div style={{ marginTop: 18, display: "flex", gap: 10, alignItems: "center" }}>
        <button
          onClick={onCreatePipeline}
          disabled={creatingPipeline}
          style={{
            ...primaryButtonStyle,
            opacity: creatingPipeline ? 0.65 : 1,
            cursor: creatingPipeline ? "not-allowed" : "pointer",
          }}
        >
          {creatingPipeline ? "Creating..." : "Create Pipeline"}
        </button>

        <span className="small">
          Creates pipeline + immutable audit event
        </span>
      </div>
    </div>
  );
}

function Pipelines({
  pipelines,
  onRunPipeline,
  runningPipelineId,
  form,
  setForm,
  onCreatePipeline,
  creatingPipeline,
}) {
  return (
    <div className="page">
      <CreatePipelineForm
        form={form}
        setForm={setForm}
        onCreatePipeline={onCreatePipeline}
        creatingPipeline={creatingPipeline}
      />

      <div className="label">Live pipeline registry</div>
      <h2 style={{ marginTop: 6 }}>All pipelines</h2>

      <div className="grid two">
        {pipelines.map((p) => (
          <div className="card pipeline" key={safeText(p.id)}>
            <div>
              <h3>{p.name}</h3>

              <div className="meta">
                {safeText(p.id)} · {safeText(p.region)} · {safeText(p.source)} → {safeText(p.target)}
              </div>

              <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
                {safeArray(p.laws).map((law) => (
                  <span className="badge purple" key={law}>
                    {law}
                  </span>
                ))}

                <span className={`badge ${p.status === "healthy" ? "green" : "amber"}`}>
                  {p.status}
                </span>
              </div>

              <div className="small" style={{ marginTop: 14 }}>
                Runs: {safeNumber(p.runs).toLocaleString()} · Heal rate: {safeNumber(p.healingRate)}% · Last run: {safeText(p.lastRun, "not run yet")}
              </div>

              <div className="meta" style={{ marginTop: 8 }}>
                Fabric TX: {safeText(p.fabric)}
              </div>

              <button
                onClick={() => onRunPipeline(p.id)}
                disabled={runningPipelineId === p.id}
                style={{
                  ...primaryButtonStyle,
                  marginTop: 16,
                  opacity: runningPipelineId === p.id ? 0.65 : 1,
                  cursor: runningPipelineId === p.id ? "not-allowed" : "pointer",
                }}
              >
                {runningPipelineId === p.id ? "Running..." : "Run Now"}
              </button>
            </div>

            <div
              className="sigma"
              style={{ color: safeNumber(p.sigma) >= 5.5 ? "var(--green)" : "var(--amber)" }}
            >
              {safeNumber(p.sigma).toFixed(1)}σ
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Audit({ events, onExportReport, onExportPdfReport, exportingReport }) {
  return (
    <div className="page">
      <div className="label">Hyperledger audit chain</div>
      <h2 style={{ marginTop: 6 }}>Recent audit events</h2>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", margin: "14px 0 18px" }}>
        <button
          onClick={() => onExportReport("audit")}
          disabled={exportingReport === "audit"}
          style={{
            ...primaryButtonStyle,
            opacity: exportingReport === "audit" ? 0.65 : 1,
            cursor: exportingReport === "audit" ? "not-allowed" : "pointer",
          }}
        >
          {exportingReport === "audit" ? "Exporting..." : "Download Audit JSON"}
        </button>

        <button
          onClick={() => onExportReport("compliance")}
          disabled={exportingReport === "compliance"}
          style={{
            ...primaryButtonStyle,
            background: "var(--purple)",
            opacity: exportingReport === "compliance" ? 0.65 : 1,
            cursor: exportingReport === "compliance" ? "not-allowed" : "pointer",
          }}
        >
          {exportingReport === "compliance" ? "Exporting..." : "Download Compliance JSON"}
        </button>

        <button
          onClick={() => onExportReport("full")}
          disabled={exportingReport === "full"}
          style={{
            ...primaryButtonStyle,
            background: "var(--green)",
            opacity: exportingReport === "full" ? 0.65 : 1,
            cursor: exportingReport === "full" ? "not-allowed" : "pointer",
          }}
        >
          {exportingReport === "full" ? "Exporting..." : "Download Full JSON"}
        </button>

        <button
          onClick={() => onExportPdfReport("audit")}
          disabled={exportingReport === "audit-pdf"}
          style={{
            ...primaryButtonStyle,
            background: "var(--amber)",
            opacity: exportingReport === "audit-pdf" ? 0.65 : 1,
            cursor: exportingReport === "audit-pdf" ? "not-allowed" : "pointer",
          }}
        >
          {exportingReport === "audit-pdf" ? "Exporting..." : "Download Audit PDF"}
        </button>

        <button
          onClick={() => onExportPdfReport("compliance")}
          disabled={exportingReport === "compliance-pdf"}
          style={{
            ...primaryButtonStyle,
            background: "var(--amber)",
            opacity: exportingReport === "compliance-pdf" ? 0.65 : 1,
            cursor: exportingReport === "compliance-pdf" ? "not-allowed" : "pointer",
          }}
        >
          {exportingReport === "compliance-pdf" ? "Exporting..." : "Download Compliance PDF"}
        </button>

        <button
          onClick={() => onExportPdfReport("full")}
          disabled={exportingReport === "full-pdf"}
          style={{
            ...primaryButtonStyle,
            background: "var(--amber)",
            opacity: exportingReport === "full-pdf" ? 0.65 : 1,
            cursor: exportingReport === "full-pdf" ? "not-allowed" : "pointer",
          }}
        >
          {exportingReport === "full-pdf" ? "Exporting..." : "Download Full PDF"}
        </button>
      </div>

      <div className="card">
        <div className="audit-row label">
          <div>Time</div>
          <div>TX</div>
          <div>Action</div>
          <div>Dataset</div>
          <div>Result</div>
        </div>

        {events.map((e, idx) => (
          <div className="audit-row" key={`${safeText(e.tx)}-${idx}`}>
            <div className="mono">{safeText(e.ts)}</div>
            <div className="mono">{safeText(e.tx)}</div>
            <div>
              <span className="badge purple">{safeText(e.action)}</span>
            </div>
            <div>{safeText(e.dataset)}</div>
            <div>
              <span
                className={`badge ${
                  safeText(e.result).startsWith("OK") || e.result === "PASSED"
                    ? "green"
                    : e.result === "FIXED"
                    ? "purple"
                    : "red"
                }`}
              >
                {safeText(e.result)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}




function SettingsPanel({ apiStatus, onTestApi, testingApi }) {
  return (
    <div className="page">
      <div className="label">Runtime settings</div>
      <h2 style={{ marginTop: 6 }}>DataNexus settings</h2>

      <div className="grid two" style={{ marginBottom: 18 }}>
        <KPICard
          label="API base"
          value={API_BASE}
          sub="React backend endpoint"
          tone="var(--purple)"
        />

        <KPICard
          label="Connection"
          value={apiStatus?.status || "not tested"}
          sub={apiStatus?.message || "click Test API"}
          tone={apiStatus?.status === "online" ? "var(--green)" : "var(--amber)"}
        />
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="label">API connection</div>
        <h3>Backend health test</h3>
        <p className="small">
          This checks whether the FastAPI backend is reachable at {API_BASE}.
        </p>

        <button
          onClick={onTestApi}
          disabled={testingApi}
          style={{
            ...primaryButtonStyle,
            opacity: testingApi ? 0.65 : 1,
            cursor: testingApi ? "not-allowed" : "pointer",
          }}
        >
          {testingApi ? "Testing..." : "Test API"}
        </button>
      </div>

      <div className="card">
        <div className="label">Local MVP commands</div>
        <h3>Useful run commands</h3>

        <div className="small" style={{ lineHeight: 1.9 }}>
          <div><strong>Start:</strong> .\START_DATANEXUS.ps1</div>
          <div><strong>Validate:</strong> .\validate_mvp.ps1</div>
          <div><strong>Stop:</strong> .\STOP_DATANEXUS.ps1</div>
          <div><strong>Clean Restart:</strong> .\CLEAN_RESTART_DATANEXUS.ps1</div>
        </div>
      </div>
    </div>
  );
}
function DemoValidation({ demo, health, onRunHealthCheck, checkingHealth }) {
  const features = demo?.completed_features || [];
  const workflow = demo?.demo_workflow || [];
  const pitch = demo?.founder_pitch || [];
  const roadmap = demo?.next_production_roadmap || [];

  return (
    <div className="page">
      <div className="label">Founder demo validation</div>
      <h2 style={{ marginTop: 6 }}>DataNexus MVP readiness</h2>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", marginBottom: 18 }}>
        <KPICard
          label="MVP score"
          value={`${demo?.mvp_readiness_score || 0}%`}
          sub={demo?.grade || "validation pending"}
          tone="var(--green)"
        />
        <KPICard
          label="Health check"
          value={`${health?.score || 0}%`}
          sub={health?.status || "not checked"}
          tone={health?.status === "passed" ? "var(--green)" : "var(--amber)"}
        />
        <KPICard
          label="Storage"
          value={demo?.summary?.storage || "unknown"}
          sub="backend persistence"
          tone="var(--purple)"
        />
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center" }}>
          <div>
            <div className="label">One-click health check</div>
            <h3>Validate demo readiness</h3>
            <div className="small">Checks live API, PostgreSQL, pipelines, audit, and compliance.</div>
          </div>

          <button
            onClick={onRunHealthCheck}
            disabled={checkingHealth}
            style={{
              ...primaryButtonStyle,
              opacity: checkingHealth ? 0.65 : 1,
              cursor: checkingHealth ? "not-allowed" : "pointer",
            }}
          >
            {checkingHealth ? "Checking..." : "Run Health Check"}
          </button>
        </div>

        {health?.checks?.length > 0 && (
          <div className="grid two" style={{ marginTop: 16 }}>
            {health.checks.map((c) => (
              <div className="card" key={c.name}>
                <div className="label">{c.name}</div>
                <h3 style={{ color: c.ok ? "var(--green)" : "var(--red)" }}>
                  {c.ok ? "Passed" : "Failed"}
                </h3>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid two">
        <div className="card">
          <div className="label">Completed modules</div>
          <h3>Implemented MVP capabilities</h3>

          <div style={{ marginTop: 14 }}>
            {features.map((f) => (
              <div key={f.name} style={{ padding: "12px 0", borderBottom: "1px solid var(--line)" }}>
                <strong>{f.name}</strong>
                <div className="small">{f.proof}</div>
                <span className="badge green">{f.status}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="label">Founder demo script</div>
          <h3>Show this workflow</h3>

          <ol style={{ lineHeight: 1.8, paddingLeft: 20 }}>
            {workflow.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </div>

        <div className="card">
          <div className="label">Investor / CTO pitch</div>
          <h3>Talking points</h3>

          <ul style={{ lineHeight: 1.8, paddingLeft: 20 }}>
            {pitch.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="label">Production roadmap</div>
          <h3>Next build targets</h3>

          <ul style={{ lineHeight: 1.8, paddingLeft: 20 }}>
            {roadmap.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function Fabric({ fabric, onRefreshFabric, loadingFabric }) {
  const nodes = safeArray(fabric?.nodes);
  const movements = safeArray(fabric?.movements);
  const summary = fabric?.summary || {};

  return (
    <div className="page">
      <div className="label">Living data fabric</div>
      <h2 style={{ marginTop: 6 }}>Fabric control plane</h2>

      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
        <div className="small">
          Nodes, regions, storage, Sigma health, and movement proof.
        </div>

        <button
          onClick={onRefreshFabric}
          disabled={loadingFabric}
          style={{
            ...primaryButtonStyle,
            opacity: loadingFabric ? 0.65 : 1,
            cursor: loadingFabric ? "not-allowed" : "pointer",
          }}
        >
          {loadingFabric ? "Refreshing..." : "Refresh Fabric"}
        </button>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", marginBottom: 18 }}>
        <KPICard label="Nodes" value={summary.total_nodes || 0} sub={`${summary.online_nodes || 0} online`} tone="var(--green)" />
        <KPICard label="Warnings" value={summary.warning_nodes || 0} sub="fabric alerts" tone="var(--amber)" />
        <KPICard label="Pipelines" value={summary.total_pipelines || 0} sub="registered" />
        <KPICard label="Avg Sigma" value={`${summary.avg_sigma || 0}σ`} sub={fabric?.storage || "storage"} tone="var(--purple)" />
      </div>

      <div className="grid two" style={{ marginBottom: 18 }}>
        {nodes.map((node) => (
          <div className="card pipeline" key={node.id}>
            <div>
              <h3>{node.name}</h3>
              <div className="meta">
                {node.id} · {node.region} · {node.role}
              </div>

              <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span className={`badge ${node.status === "online" ? "green" : "amber"}`}>
                  {node.status}
                </span>
                <span className="badge purple">{node.storage}</span>
                <span className="badge green">{node.pipelines} pipelines</span>
              </div>
            </div>

            <div className="sigma" style={{ color: safeNumber(node.sigma) >= 5.5 ? "var(--green)" : "var(--amber)" }}>
              {safeNumber(node.sigma).toFixed(1)}σ
            </div>
          </div>
        ))}
      </div>

      <div className="label">Fabric movements</div>
      <h2 style={{ marginTop: 6 }}>Recent pipeline movement map</h2>

      <div className="card">
        <div className="audit-row label">
          <div>Dataset</div>
          <div>Source</div>
          <div>Target</div>
          <div>Law</div>
          <div>TX</div>
        </div>

        {movements.map((m, idx) => (
          <div className="audit-row" key={`${m.fabric_tx}-${idx}`}>
            <div>{safeText(m.dataset)}</div>
            <div className="mono">{safeText(m.from)}</div>
            <div className="mono">{safeText(m.to)}</div>
            <div><span className="badge purple">{safeText(m.law)}</span></div>
            <div className="mono">{safeText(m.fabric_tx)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
function QueryAssistant({
  question,
  setQuestion,
  queryResult,
  onAskQuery,
  querying,
  onBuildIntent,
  intentBuilding,
}) {
  return (
    <div className="page">
      <div className="label">AI query assistant</div>
      <h2 style={{ marginTop: 6 }}>Ask DataNexus</h2>

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="label" style={{ marginBottom: 8 }}>Natural language query</div>

        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Example: show risky pipelines, show DPDP pipelines in India, show latest audit events"
          rows={4}
          style={{
            width: "100%",
            border: "1px solid var(--line)",
            borderRadius: 16,
            padding: "13px 14px",
            background: "rgba(255,255,255,0.74)",
            color: "var(--navy)",
            outline: "none",
            fontSize: 14,
            resize: "vertical",
          }}
        />

        <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[
            "show risky pipelines",
            "show DPDP pipelines in India",
            "rank pipelines by sigma quality",
            "latest audit events",
            "create a Kafka to fabric pipeline for fraud data under DPDP in Mumbai",
            "जोखिम वाले pipelines दिखाओ",
            "DPDP pipelines भारत में दिखाओ",
            "రిస్క్ ఉన్న pipelines చూపించు"
          ].map((sample) => (
            <button
              key={sample}
              onClick={() => setQuestion(sample)}
              style={{
                border: "1px solid var(--line)",
                background: "rgba(255,255,255,0.7)",
                borderRadius: 999,
                padding: "8px 12px",
                cursor: "pointer",
                fontSize: 12,
              }}
            >
              {sample}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "center" }}>
          <button
            onClick={onAskQuery}
            disabled={querying}
            style={{
              ...primaryButtonStyle,
              opacity: querying ? 0.65 : 1,
              cursor: querying ? "not-allowed" : "pointer",
            }}
          >
            {querying ? "Thinking..." : "Ask Query"}
          </button>

          <button
            onClick={onBuildIntent}
            disabled={intentBuilding}
            style={{
              ...primaryButtonStyle,
              background: "var(--purple)",
              opacity: intentBuilding ? 0.65 : 1,
              cursor: intentBuilding ? "not-allowed" : "pointer",
            }}
          >
            {intentBuilding ? "Building..." : "Build from Intent"}
          </button>

          <span className="small">
            Ask searches the fabric. Build creates a real pipeline from intent.
          </span>
        </div>
      </div>

      {queryResult && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div className="label">Answer</div>

          <h3 style={{ marginBottom: 8 }}>{queryResult.answer}</h3>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
            <span className="badge purple">Intent: {queryResult.intent}</span>
            <span className="badge green">TX: {queryResult.fabric_tx}</span>
          </div>

          <div className="small">
            Question: {queryResult.question}
          </div>
        </div>
      )}

      {queryResult?.matched_pipelines?.length > 0 && (
        <>
          <div className="label">Matched pipelines</div>
          <div className="grid two" style={{ marginTop: 10, marginBottom: 18 }}>
            {queryResult.matched_pipelines.map((p) => (
              <div className="card pipeline" key={safeText(p.id)}>
                <div>
                  <h3>{p.name}</h3>
                  <div className="meta">
                    {safeText(p.id)} · {safeText(p.region)} · {safeText(p.source)} → {safeText(p.target)}
                  </div>

                  <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {safeArray(p.laws).map((law) => (
                      <span className="badge purple" key={law}>{law}</span>
                    ))}
                    <span className={`badge ${p.status === "healthy" ? "green" : "amber"}`}>
                      {p.status}
                    </span>
                  </div>

                  <div className="small" style={{ marginTop: 12 }}>
                    Runs: {safeNumber(p.runs).toLocaleString()} · Heal rate: {safeNumber(p.healingRate)}% · Last run: {safeText(p.lastRun, "not run yet")}
                  </div>
                </div>

                <div className="sigma" style={{ color: safeNumber(p.sigma) >= 5.5 ? "var(--green)" : "var(--amber)" }}>
                  {safeNumber(p.sigma).toFixed(1)}σ
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {queryResult?.matched_audit?.length > 0 && (
        <>
          <div className="label">Matched audit events</div>
          <div className="card" style={{ marginTop: 10 }}>
            <div className="audit-row label">
              <div>Time</div>
              <div>TX</div>
              <div>Action</div>
              <div>Dataset</div>
              <div>Result</div>
            </div>

            {queryResult.matched_audit.map((e, idx) => (
              <div className="audit-row" key={`${safeText(e.tx)}-${idx}`}>
                <div className="mono">{safeText(e.ts)}</div>
                <div className="mono">{safeText(e.tx)}</div>
                <div><span className="badge purple">{safeText(e.action)}</span></div>
                <div>{safeText(e.dataset)}</div>
                <div>
                  <span className={`badge ${
                    safeText(e.result).startsWith("OK") || e.result === "PASSED"
                      ? "green"
                      : e.result === "FIXED"
                      ? "purple"
                      : "red"
                  }`}>
                    {safeText(e.result)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
function Compliance({ compliance, onRunCompliance, runningCompliance , onRunAllComplianceChecks}) {
  const frameworks = compliance?.frameworks || [];

  return (
    <div className="page">
      <div className="label">Compliance intelligence</div>
      <h2 style={{ marginTop: 6 }}>Framework summary</h2>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", margin: "14px 0 18px" }}>
        <button
          type="button"
          onClick={() => {
            if (typeof onRunAllComplianceChecks === "function") {
              onRunAllComplianceChecks();
            } else {
              console.error("onRunAllComplianceChecks is not wired");
            }
          }}
          style={primaryButtonStyle}
        >
          Run All Checks
        </button>
      </div>

      <div className="grid two">
        {frameworks.map((f) => (
          <div className="card" key={f.code}>
            <div className="label">{f.code}</div>
            <h3>{f.law}</h3>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
              <span className={`badge ${f.violations > 0 ? "amber" : "green"}`}>
                {f.status}
              </span>
              <span className="badge purple">{f.rules} rules</span>
            </div>

            <div className="grid kpi" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
              <KPICard label="Rules" value={f.rules} />
              <KPICard label="Violations" value={f.violations} tone={f.violations ? "var(--red)" : "var(--green)"} />
              <KPICard label="Fixes" value={f.auto_fixes} tone="var(--purple)" />
            </div>

            <button
              onClick={() => onRunCompliance(f.code)}
              disabled={runningCompliance === f.code}
              style={{
                ...primaryButtonStyle,
                marginTop: 18,
                opacity: runningCompliance === f.code ? 0.65 : 1,
                cursor: runningCompliance === f.code ? "not-allowed" : "pointer",
              }}
            >
              {runningCompliance === f.code ? "Checking..." : `Run ${f.code} Check`}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function App() {
  const [tab, setTab] = useState("Overview");
  const [online, setOnline] = useState(null);
  const [live, setLive] = useState(null);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [runningPipelineId, setRunningPipelineId] = useState("");
  const [runningCompliance, setRunningCompliance] = useState("");
  const [creatingPipeline, setCreatingPipeline] = useState(false);
  const [question, setQuestion] = useState("create a Kafka to fabric pipeline for fraud data under DPDP in Mumbai");
  const [queryResult, setQueryResult] = useState(null);
  const [querying, setQuerying] = useState(false);
  const [intentBuilding, setIntentBuilding] = useState(false);
  const [exportingReport, setExportingReport] = useState("");
  const [demo, setDemo] = useState(null);
  const [health, setHealth] = useState(null);
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [apiStatus, setApiStatus] = useState(null);
  const [testingApi, setTestingApi] = useState(false);
  const [fabric, setFabric] = useState(null);
  const [loadingFabric, setLoadingFabric] = useState(false);

  const [createForm, setCreateForm] = useState({
    name: "payments_fraud_stream",
    source: "kafka",
    target: "fabric_node_mumbai",
    region: "IN-MH",
    law: "DPDP",
    owner: "risk_team",
  });

  const refresh = async () => {
    try {
      setError("");
      const data = await apiGet("/api/v1/dashboard/live");
      setLive(data);
      setOnline(true);
    } catch (e) {
      setError(e.message || "API unavailable");
      setOnline(false);
    }
  };

  const runPipeline = async (pipelineId) => {
    try {
      setRunningPipelineId(pipelineId);
      setToast("");

      const result = await apiPost(`/api/v1/dashboard/pipelines/${pipelineId}/run`);

      setToast(
        `Pipeline ${result.pipeline_name} completed · ${result.run_id} · ${result.fabric_tx}`
      );

      await refresh();
      setTab("Audit");
    } catch (e) {
      setError(e.message || "Pipeline run failed");
    } finally {
      setRunningPipelineId("");
    }
  };

  const runCompliance = async (frameworkCode) => {
    try {
      setRunningCompliance(frameworkCode);
      setToast("");

      const result = await apiPost(
        `/api/v1/dashboard/compliance/run-check?framework=${encodeURIComponent(frameworkCode)}`
      );

      setToast(
        `${result.framework} compliance check ${result.result} · ${result.check_id} · ${result.fabric_tx}`
      );

      await refresh();
      setTab("Audit");
    } catch (e) {
      setError(e.message || "Compliance check failed");
    } finally {
      setRunningCompliance("");
    }
  };

  const createPipeline = async () => {
    try {
      setCreatingPipeline(true);
      setToast("");
      setError("");

      if (!createForm.name.trim()) {
        setError("Pipeline name is required");
        return;
      }

      const result = await apiPost("/api/v1/dashboard/pipelines/create", createForm);

      setToast(
        `Pipeline ${result.pipeline_name} created · ${result.pipeline_id} · ${result.fabric_tx}`
      );

      await refresh();
      setTab("Pipelines");
    } catch (e) {
      setError(e.message || "Pipeline creation failed");
    } finally {
      setCreatingPipeline(false);
    }
  };


  const askQuery = async () => {
    try {
      setQuerying(true);
      setToast("");
      setError("");

      if (!question.trim()) {
        setError("Question is required");
        return;
      }

      const result = await apiPost("/api/v1/dashboard/query/ask", {
        question,
      });

      setQueryResult(result);
      setToast(`Query answered · ${result.intent} · ${result.fabric_tx}`);

      await refresh();
    } catch (e) {
      setError(e.message || "Query failed");
    } finally {
      setQuerying(false);
    }
  };

  const buildFromIntent = async () => {
    try {
      setIntentBuilding(true);
      setToast("");
      setError("");

      if (!question.trim()) {
        setError("Question is required");
        return;
      }

      const result = await apiPost("/api/v1/dashboard/query/intent-build", {
        question,
      });

      if (result.status === "needs_query") {
        setToast(result.message);

        setQueryResult({
          status: "answered",
          question,
          intent: result.intent,
          answer: result.message,
          fabric_tx: result.fabric_tx,
          matched_pipelines: [],
          matched_audit: result.audit_event ? [result.audit_event] : [],
        });

        await refresh();
        setTab("Query");
        return;
      }

      if (result.status === "created") {
        setToast(
          `Pipeline created: ${result.pipeline_name} · ${result.pipeline_id} · ${result.fabric_tx}`
        );

        setQueryResult({
          status: "answered",
          question,
          intent: result.intent,
          answer: result.message,
          fabric_tx: result.fabric_tx,
          matched_pipelines: result.pipeline ? [result.pipeline] : [],
          matched_audit: result.audit_events || [],
        });

        // Optimistic UI update: show the new pipeline immediately
        setLive((prev) => {
          if (!prev || !result.pipeline) return prev;

          const existing = Array.isArray(prev.pipelines) ? prev.pipelines : [];
          const alreadyExists = existing.some((p) => p.id === result.pipeline.id);

          return {
            ...prev,
            pipelines: alreadyExists ? existing : [result.pipeline, ...existing],
            audit: Array.isArray(prev.audit)
              ? [...(result.audit_events || []), ...prev.audit]
              : result.audit_events || [],
          };
        });

        // Move immediately to Pipelines
        setTab("Pipelines");

        // Then refresh from PostgreSQL
        await refresh();
        setTab("Pipelines");
        return;
      }

      setError(result.message || "Intent build did not create a pipeline");
    } catch (e) {
      setError(e.message || "Intent build failed");
    } finally {
      setIntentBuilding(false);
    }
  };

  const exportReport = async (type) => {
    try {
      setExportingReport(type);
      setToast("");
      setError("");

      const endpointMap = {
        audit: "/api/v1/dashboard/reports/audit",
        compliance: "/api/v1/dashboard/reports/compliance",
        full: "/api/v1/dashboard/reports/full",
      };

      const result = await apiGet(endpointMap[type]);

      const stamp = new Date().toISOString().replaceAll(":", "-").slice(0, 19);
      downloadJsonReport(`datanexus_${type}_report_${stamp}.json`, result);

      setToast(`${type.toUpperCase()} report exported · ${result.report_id} · ${result.fabric_tx}`);

      await refresh();
    } catch (e) {
      setError(e.message || "Report export failed");
    } finally {
      setExportingReport("");
    }
  };

  const exportPdfReport = async (type) => {
    try {
      setExportingReport(`${type}-pdf`);
      setToast("");
      setError("");

      const endpointMap = {
        audit: "/api/v1/dashboard/reports/audit.pdf",
        compliance: "/api/v1/dashboard/reports/compliance.pdf",
        full: "/api/v1/dashboard/reports/full.pdf",
      };

      const blob = await apiBlob(endpointMap[type]);

      const stamp = new Date().toISOString().replaceAll(":", "-").slice(0, 19);
      downloadBinaryReport(`datanexus_${type}_report_${stamp}.pdf`, blob);

      setToast(`${type.toUpperCase()} PDF report exported`);

      await refresh();
    } catch (e) {
      setError(e.message || "PDF export failed");
    } finally {
      setExportingReport("");
    }
  };

  const loadDemoValidation = async () => {
    try {
      const result = await apiGet("/api/v1/dashboard/demo/validation");
      setDemo(result);
    } catch (e) {
      setError(e.message || "Demo validation failed");
    }
  };

  const runHealthCheck = async () => {
    try {
      setCheckingHealth(true);
      setToast("");
      setError("");

      const result = await apiGet("/api/v1/dashboard/demo/health-check");
      setHealth(result);
      setToast(`Health check ${result.status} · ${result.score}%`);

      await loadDemoValidation();
    } catch (e) {
      setError(e.message || "Health check failed");
    } finally {
      setCheckingHealth(false);
    }
  };

  const loadFabricStatus = async () => {
    try {
      setLoadingFabric(true);
      const result = await apiGet("/api/v1/dashboard/fabric/status");
      setFabric(result);
    } catch (e) {
      setError(e.message || "Fabric status failed");
    } finally {
      setLoadingFabric(false);
    }
  };

  const runAllComplianceChecks = async () => {
    try {
      setToast("");
      setError("");

      const result = await apiPost("/api/v1/dashboard/compliance/run-all-checks", {});

      setToast(
        `All compliance checks completed · ${result.frameworks_checked} frameworks · ${result.overall_result}`
      );

      await refresh();
      setTab("Audit");
    } catch (e) {
      setError(e.message || "Run all compliance checks failed");
    }
  };

  const testApiConnection = async () => {
    try {
      setTestingApi(true);
      setToast("");
      setError("");

      const res = await fetch(`${API_BASE}/api/status`);

      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}`);
      }

      const data = await res.json();

      setApiStatus({
        status: "online",
        message: data.service || "DataNexus API reachable",
      });

      setToast(`API online: ${API_BASE}`);
    } catch (e) {
      setApiStatus({
        status: "offline",
        message: e.message || "API unavailable",
      });

      setError(`API offline: ${e.message}`);
    } finally {
      setTestingApi(false);
    }
  };
  useEffect(() => {
    refresh();
    loadDemoValidation();
    loadFabricStatus();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, []);

  const pipelines = useMemo(() => safeArray(live?.pipelines), [live]);
  const events = useMemo(() => safeArray(live?.audit), [live]);

  return (
    <div className="app">
      <div className="header">
        <div>
          <div className="brand">DataNexus</div>
          <div className="subtitle">Era 3 · React live dashboard</div>
        </div>
        <StatusBadge online={online} />
      </div>

      {error && <div className="error">API error: {error}</div>}

      {toast && (
        <div
          style={{
            margin: "16px 32px 0",
            padding: "12px 14px",
            borderRadius: 14,
            background: "rgba(5,150,105,0.10)",
            color: "var(--green)",
            border: "1px solid rgba(5,150,105,0.16)",
            fontSize: 13,
          }}
        >
          {toast}
        </div>
      )}

      <div className="tabs">
        {["Overview", "Pipelines", "Fabric", "Audit", "Compliance", "Query", "Demo", "Settings"].map((t) => (
          <button
            key={t}
            className={`tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && <Overview live={live} online={online} />}

      {tab === "Pipelines" && (
        <Pipelines
          pipelines={pipelines}
          onRunPipeline={runPipeline}
          runningPipelineId={runningPipelineId}
          form={createForm}
          setForm={setCreateForm}
          onCreatePipeline={createPipeline}
          creatingPipeline={creatingPipeline}
        />
      )}


      {tab === "Fabric" && (
        <Fabric
          fabric={fabric}
          onRefreshFabric={loadFabricStatus}
          loadingFabric={loadingFabric}
        />
      )}
      {tab === "Audit" && (
        <Audit
          events={events}
          onExportReport={exportReport}
          onExportPdfReport={exportPdfReport}
          exportingReport={exportingReport}
        />
      )}

      {tab === "Compliance" && (
        <Compliance
          compliance={live?.compliance}
          onRunCompliance={runCompliance}
          runningCompliance={runningCompliance}
          onRunAllComplianceChecks={runAllComplianceChecks}
        />
      )}


      {tab === "Query" && (
        <QueryAssistant
          question={question}
          setQuestion={setQuestion}
          queryResult={queryResult}
          onAskQuery={askQuery}
          querying={querying}
          onBuildIntent={buildFromIntent}
          intentBuilding={intentBuilding}
        />
      )}

      {tab === "Demo" && (
        <DemoValidation
          demo={demo}
          health={health}
          onRunHealthCheck={runHealthCheck}
          checkingHealth={checkingHealth}
        />
      )}

      {tab === "Settings" && (
        <SettingsPanel
          apiStatus={apiStatus}
          onTestApi={testApiConnection}
          testingApi={testingApi}
        />
      )}
      <div className="footer">
        <div>DataNexus · Open source · Local MVP</div>
        <div className="mono">API: {API_BASE}</div>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);





















