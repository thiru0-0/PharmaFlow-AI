"use client";
import React from "react";
import { api, currentUser } from "@/lib/api";
import { Badge, Card, useAsync } from "@/lib/ui";

export default function DisputesPage() {
  const disputes = useAsync<any[]>(() => api("/disputes"), []);
  const role = currentUser<any>()?.role;
  const [sel, setSel] = React.useState<any>(null);
  const [msg, setMsg] = React.useState<string | null>(null);

  async function open(id: string) {
    setMsg(null);
    setSel(await api(`/disputes/${id}`));
  }
  async function addEvidence() {
    const note = prompt("Evidence note (recount / photo description):");
    if (!note) return;
    try { await api(`/disputes/${sel.id}/evidence`, { method: "POST", body: { note } }); open(sel.id); }
    catch (e) { setMsg((e as any).message); }
  }
  async function resolve() {
    const q = prompt("Reconciled quantity:", String(sel.confirmed_qty));
    if (!q) return;
    const note = prompt("Resolution note:") || "adjudicated";
    try {
      const r = await api<any>(`/disputes/${sel.id}/resolve`, { method: "POST", body: { reconciled_qty: Number(q), resolution_notes: note } });
      setMsg(`Resolved — batch ${r.batch_state}`); disputes.reload(); open(sel.id);
    } catch (e) { setMsg((e as any).message); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <h1 style={{ margin: 0 }}>Disputes</h1>
      {msg && <div className="card" style={{ padding: 12 }}>{msg}</div>}
      <Card title="Quantity-mismatch cases" right={<button className="btn secondary" onClick={disputes.reload}>Refresh</button>}>
        <table>
          <thead><tr><th>Batch</th><th>Retailer</th><th>Distributor</th><th>Reported</th><th>Confirmed</th><th>Diff</th><th>Tolerance</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {(disputes.data || []).map((d) => (
              <tr key={d.id}>
                <td className="mono">{d.batch_number}</td>
                <td>{d.retailer}</td><td>{d.distributor}</td>
                <td>{d.reported_qty}</td><td>{d.confirmed_qty}</td>
                <td><b>{d.difference}</b></td><td>±{d.tolerance_units}</td>
                <td><Badge state={d.status} /></td>
                <td><button className="btn secondary" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => open(d.id)}>View</button></td>
              </tr>
            ))}
            {!disputes.data?.length && <tr><td colSpan={9} style={{ color: "var(--muted)" }}>No disputes.</td></tr>}
          </tbody>
        </table>
      </Card>

      {sel && (
        <Card title={`Dispute ${sel.id.slice(0, 8)} — ${sel.batch_number}`}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="card" style={{ padding: 12 }}>
              <div className="label">Retailer reported</div>
              <div style={{ fontSize: 24, fontWeight: 800 }}>{sel.reported_qty}</div>
              <div className="mono">{sel.retailer_photo}</div>
            </div>
            <div className="card" style={{ padding: 12 }}>
              <div className="label">Distributor confirmed</div>
              <div style={{ fontSize: 24, fontWeight: 800 }}>{sel.confirmed_qty}</div>
              <div className="mono">{sel.distributor_photo}</div>
            </div>
          </div>
          <p style={{ fontSize: 14 }}>Difference <b>{sel.difference}</b> exceeds tolerance <b>±{sel.tolerance_units}</b> → batch <Badge state={sel.batch_state} /> (blocked from progressing while OPEN).</p>
          <div>
            <div className="label">Evidence</div>
            {sel.evidence?.map((e: any, i: number) => (
              <div key={i} className="mono" style={{ fontSize: 12 }}>• {e.by}: {e.note}</div>
            ))}
            {!sel.evidence?.length && <p style={{ color: "var(--muted)" }}>No evidence submitted.</p>}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            {sel.status === "OPEN" && ["RETAILER", "DISTRIBUTOR", "ADMIN"].includes(role) && (
              <button className="btn secondary" onClick={addEvidence}>Submit evidence</button>
            )}
            {sel.status === "OPEN" && role === "ADMIN" && (
              <button className="btn ok" onClick={resolve}>Adjudicate &amp; reconcile</button>
            )}
            {sel.status === "OPEN" && role !== "ADMIN" && (
              <span style={{ fontSize: 12, color: "var(--muted)" }}>Only a platform admin / supervisor can adjudicate.</span>
            )}
          </div>
          {sel.resolution_notes && <p><b>Resolution:</b> {sel.resolution_notes} (reconciled {sel.reconciled_qty})</p>}
        </Card>
      )}
    </div>
  );
}
