"use client";
import React from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge, Card, useAsync } from "@/lib/ui";

export default function AlertsPage() {
  const alerts = useAsync<any[]>(() => api("/alerts/reentry"), []);
  return (
    <div style={{ display: "grid", gap: 20 }}>
      <h1 style={{ margin: 0 }}>Re-entry Alerts</h1>
      <Card title="All alerts" right={<button className="btn secondary" onClick={alerts.reload}>Refresh</button>}>
        <table>
          <thead><tr><th>Severity</th><th>Batch</th><th>Attempted by</th><th>Location</th><th>Qty</th><th>Notified</th><th>Latency</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {(alerts.data || []).map((a) => (
              <tr key={a.id}>
                <td><Badge state={a.severity} /></td>
                <td className="mono">{a.batch_number}</td>
                <td>{a.attempted_retailer}</td>
                <td>{a.attempted_location}</td>
                <td>{a.attempted_quantity}</td>
                <td>{a.notified_controller ? "ctrl ✓" : "ctrl ✗"} · {a.notified_manufacturer ? "mfr ✓" : "mfr ✗"}</td>
                <td>{a.notification_latency_ms} ms</td>
                <td><Badge state={a.status} /></td>
                <td><Link className="btn secondary" style={{ fontSize: 12, padding: "4px 8px" }} href={`/alerts/${a.id}`}>Open</Link></td>
              </tr>
            ))}
            {!alerts.data?.length && <tr><td colSpan={9} style={{ color: "var(--muted)" }}>No alerts.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
