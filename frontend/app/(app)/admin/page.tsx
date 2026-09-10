"use client";
import React from "react";
import { api } from "@/lib/api";
import { Card } from "@/lib/ui";

export default function AdminPage() {
  const [log, setLog] = React.useState<any[]>([]);
  const [busy, setBusy] = React.useState<string | null>(null);

  async function run(label: string, path: string) {
    setBusy(label);
    const t0 = performance.now();
    try {
      const res = await api<any>(path, { method: "POST" });
      const ms = Math.round(performance.now() - t0);
      setLog((l) => [{ label, ms, res, at: new Date().toLocaleTimeString() }, ...l]);
    } catch (e) {
      setLog((l) => [{ label, err: (e as any).message, at: new Date().toLocaleTimeString() }, ...l]);
    } finally { setBusy(null); }
  }

  const actions: [string, string][] = [
    ["RESET DEMO DATA", "/demo/reset"],
    ["Run fraud scenario", "/demo/scripts/fraud"],
    ["Run happy path", "/demo/scripts/happy"],
    ["Run dispute scenario", "/demo/scripts/dispute"],
    ["Run expiry job", "/demo/jobs/expiry"],
    ["Run SLA scan", "/demo/jobs/sla"],
    ["Run registry integrity check", "/demo/jobs/verify"],
  ];

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <h1 style={{ margin: 0 }}>Demo Control</h1>
      <Card title="Actions">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {actions.map(([label, path]) => (
            <button key={path} className={`btn ${label.startsWith("RESET") ? "danger" : "secondary"}`}
              disabled={!!busy} onClick={() => run(label, path)}>
              {busy === label ? "Running…" : label}
            </button>
          ))}
        </div>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>
          RESET restores the exact seeded state (batches A–G). Scenario runners execute the real
          flow against the database and report elapsed time.
        </p>
      </Card>

      <Card title="Run log">
        <div style={{ display: "grid", gap: 10 }}>
          {log.map((e, i) => (
            <div key={i} className="card" style={{ padding: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>{e.label}</strong>
                <span className="mono">{e.at} {e.ms != null && `· ${e.ms} ms`}</span>
              </div>
              {e.err
                ? <p style={{ color: "var(--danger)", margin: "6px 0 0" }}>{e.err}</p>
                : <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: "6px 0 0", maxHeight: 260, overflow: "auto" }}>{JSON.stringify(e.res, null, 2)}</pre>}
            </div>
          ))}
          {!log.length && <p style={{ color: "var(--muted)" }}>No runs yet.</p>}
        </div>
      </Card>
    </div>
  );
}
