"use client";
import React from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge, Card, useAsync } from "@/lib/ui";

export default function ManufacturerPage() {
  const inbound = useAsync<any[]>(() => api("/manufacturer/inbound"), []);
  const receipts = useAsync<any[]>(() => api("/manufacturer/receipts"), []);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  function reloadAll() { inbound.reload(); receipts.reload(); }

  async function recordReceipt(b: any) {
    const q = prompt(`Confirmed received quantity for ${b.batch_number}?`, String(b.quantity_confirmed ?? ""));
    if (!q) return;
    setErr(null); setMsg(null);
    try {
      const r = await api<any>("/manufacturer/receipts", { method: "POST", body: { batch_id: b.batch_id, quantity: Number(q) } });
      setMsg(`Receipt recorded — batch ${r.batch_state}`); reloadAll();
    } catch (e) { setErr((e as any).message); }
  }

  async function uploadCert(rc: any) {
    setErr(null); setMsg(null);
    try {
      const r = await api<any>("/manufacturer/certificates", {
        method: "POST",
        body: { batch_id: rc.batch_id, facility_name: "GreenCycle Biomedical Waste Facility (synthetic)", cert_url: "mock://uploads/cert.pdf", reason: "expired" },
      });
      setMsg(`Certificate accepted — batch ${r.batch_state}. Disposal record auto-populated.`); reloadAll();
    } catch (e) { setErr((e as any).message); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <h1 style={{ margin: 0 }}>Manufacturer — Receipts &amp; Destruction</h1>
      {msg && <div className="card" style={{ padding: 12, color: "var(--ok)", fontWeight: 600 }}>{msg}</div>}
      {err && <div className="card" style={{ padding: 12, color: "var(--danger)", fontWeight: 600, borderColor: "var(--danger)", background: "#fef2f2" }}>{err}</div>}

      <Card title="Inbound — confirmed pickups awaiting receipt">
        <table>
          <thead><tr><th>Batch</th><th>Drug</th><th>Qty confirmed</th><th>State</th><th></th></tr></thead>
          <tbody>
            {(inbound.data || []).map((b) => (
              <tr key={b.batch_id}>
                <td className="mono">{b.batch_number}</td>
                <td>{b.drug_name}</td>
                <td>{b.quantity_confirmed}</td>
                <td><Badge state={b.batch_state} /></td>
                <td><button className="btn" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => recordReceipt(b)}>Confirm receipt</button></td>
              </tr>
            ))}
            {!inbound.data?.length && <tr><td colSpan={5} style={{ color: "var(--muted)" }}>Nothing inbound.</td></tr>}
          </tbody>
        </table>
      </Card>

      <Card title="Receipts &amp; certificates" right={<button className="btn secondary" onClick={receipts.reload}>Refresh</button>}>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Certificate upload is gated: it is blocked unless a confirmed manufacturer receipt exists and the batch is <span className="mono">RECEIVED_BY_MANUFACTURER</span>.
        </p>
        <table>
          <thead><tr><th>Batch</th><th>Drug</th><th>Qty</th><th>Received</th><th>State</th><th></th></tr></thead>
          <tbody>
            {(receipts.data || []).map((rc) => (
              <tr key={rc.receipt_id}>
                <td><Link className="mono" href={`/batch/${rc.batch_id}`}>{rc.batch_number}</Link></td>
                <td>{rc.drug_name}</td>
                <td>{rc.quantity}</td>
                <td>{String(rc.received_at).slice(0, 10)}</td>
                <td><Badge state={rc.batch_state} /></td>
                <td>
                  {rc.certificate_id ? <span className="badge green">certified</span>
                    : <button className="btn" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => uploadCert(rc)}>Upload destruction certificate</button>}
                </td>
              </tr>
            ))}
            {!receipts.data?.length && <tr><td colSpan={6} style={{ color: "var(--muted)" }}>No receipts.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
