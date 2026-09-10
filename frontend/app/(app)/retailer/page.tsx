"use client";
import React from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { Badge, Card, ErrorText, useAsync } from "@/lib/ui";
import Scanner from "@/components/Scanner";

export default function RetailerPage() {
  const batches = useAsync<any[]>(() => api("/retailer/batches"), []);
  const returns = useAsync<any[]>(() => api("/retailer/returns"), []);
  const notifs = useAsync<any[]>(() => api("/dashboard/notifications"), []);

  const [qr, setQr] = React.useState("");
  const [qty, setQty] = React.useState(1);
  const [saleResult, setSaleResult] = React.useState<any>(null);
  const [blocked, setBlocked] = React.useState<any>(null);
  const [saleErr, setSaleErr] = React.useState<any>(null);

  function reloadAll() { batches.reload(); returns.reload(); notifs.reload(); }

  async function sell() {
    setSaleErr(null); setSaleResult(null); setBlocked(null);
    try {
      const res = await api<any>("/retailer/pos/sale", { method: "POST", body: { qr_payload: qr, quantity: Number(qty) } });
      setSaleResult(res);
      reloadAll();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.detail?.status === "BLOCKED_REENTRY") {
        setBlocked(e.detail); reloadAll();
      } else setSaleErr(e);
    }
  }

  async function initiateReturn(b: any) {
    const q = prompt(`Counted quantity to return for ${b.batch_number}?`, String(b.quantity_on_hand));
    if (!q) return;
    try {
      await api(`/retailer/batches/${b.batch_id}/initiate-return`, { method: "POST", body: { quantity_reported: Number(q), condition: "sealed" } });
      reloadAll();
    } catch (e) { alert((e as any).message || "Failed"); }
  }

  async function confirmReturn(rr: any) {
    const q = prompt(`Confirm counted quantity for ${rr.batch_number}?`, "0");
    if (!q) return;
    try {
      await api(`/retailer/returns/${rr.id}/confirm`, { method: "POST", body: { quantity_reported: Number(q), condition: "sealed" } });
      reloadAll();
    } catch (e) { alert((e as any).message || "Failed"); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <h1 style={{ margin: 0 }}>Retailer POS &amp; Inventory</h1>

      {blocked && (
        <div className="card" style={{ padding: 20, borderColor: "var(--danger)", background: "#fef2f2" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="badge red">RE-ENTRY BLOCKED</span>
            <strong style={{ fontSize: 16 }}>Sale of {blocked.batch_number} blocked at point of sale</strong>
          </div>
          <p style={{ margin: "10px 0", fontSize: 14 }}>{blocked.message}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 10, fontSize: 13 }}>
            <div><div className="label">Batch state</div>{blocked.batch_state}</div>
            <div><div className="label">Attempted at</div>{blocked.attempted_location}</div>
            <div><div className="label">State Drug Controller</div>{blocked.notified?.state_drug_controller ? "✓ notified" : "—"}</div>
            <div><div className="label">Manufacturer</div>{blocked.notified?.manufacturer ? "✓ notified" : "—"}</div>
            <div><div className="label">Latency</div>{blocked.latency_ms} ms</div>
          </div>
          <Link className="btn secondary" style={{ marginTop: 12 }} href={`/alerts/${blocked.alert_id}`}>Open re-entry alert</Link>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <Card title="Scan to sell">
          <Scanner onScan={(t) => setQr(t)} />
          <div className="label" style={{ marginTop: 8 }}>QR payload (or use demo scan)</div>
          <input className="input" value={qr} onChange={(e) => setQr(e.target.value)} placeholder="(01)08901234500…(10)AZ-2025-…" style={{ margin: "6px 0" }} />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            {(batches.data || []).slice(0, 6).map((b) => (
              <button key={b.batch_id} className="btn secondary" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => setQr(b.qr_payload)}>
                demo scan {b.batch_number}
              </button>
            ))}
          </div>
          <div className="label">Quantity</div>
          <input className="input" type="number" min={1} value={qty} onChange={(e) => setQty(Number(e.target.value))} style={{ margin: "6px 0" }} />
          <button className="btn" onClick={sell} disabled={!qr}>Record sale</button>
          <ErrorText e={saleErr} />
          {saleResult && (
            <p style={{ color: "var(--ok)", fontWeight: 700, marginTop: 8 }}>
              ✓ Sold {saleResult.quantity} × {saleResult.batch_number} — {saleResult.remaining_on_hand} left on hand
            </p>
          )}
        </Card>

        <Card title="Notifications" right={<button className="btn secondary" onClick={notifs.reload}>Refresh</button>}>
          <div style={{ display: "grid", gap: 8, maxHeight: 320, overflow: "auto" }}>
            {(notifs.data || []).map((n) => (
              <div key={n.id} style={{ borderBottom: "1px solid var(--line)", paddingBottom: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong style={{ fontSize: 13 }}>{n.type.replaceAll("_", " ")}</strong>
                  <span className="badge gray">{n.channel} · {n.delivery_status}</span>
                </div>
                <div className="mono" style={{ color: "var(--muted)" }}>{JSON.stringify(n.payload)}</div>
              </div>
            ))}
            {!notifs.data?.length && <p style={{ color: "var(--muted)" }}>No notifications.</p>}
          </div>
        </Card>
      </div>

      <Card title="Inventory" right={<button className="btn secondary" onClick={batches.reload}>Refresh</button>}>
        <table>
          <thead><tr><th>Batch</th><th>Drug</th><th>Expiry</th><th>Days</th><th>On hand</th><th>State</th><th></th></tr></thead>
          <tbody>
            {(batches.data || []).map((b) => (
              <tr key={b.batch_id}>
                <td><Link href={`/batch/${b.batch_id}`} className="mono">{b.batch_number}</Link></td>
                <td>{b.drug_name}</td>
                <td>{String(b.expiry_date).slice(0, 10)}</td>
                <td>
                  {b.days_to_expiry <= 60 && b.days_to_expiry >= 0 && b.state === "ACTIVE" && (
                    <span className="badge amber">{b.days_to_expiry}d to expiry</span>
                  )}
                  {b.days_to_expiry < 0 && <span className="badge red">expired</span>}
                  {b.days_to_expiry > 60 && <span>{b.days_to_expiry}</span>}
                </td>
                <td>{b.quantity_on_hand}</td>
                <td><Badge state={b.state} /> {b.reentry_flagged && <span className="badge red">RE-ENTRY</span>}</td>
                <td>
                  {b.state === "ACTIVE" && (
                    <button className="btn secondary" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => initiateReturn(b)}>
                      Initiate return
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="My returns" right={<button className="btn secondary" onClick={returns.reload}>Refresh</button>}>
        <table>
          <thead><tr><th>Batch</th><th>Status</th><th>Qty reported</th><th>Condition</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {(returns.data || []).map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.batch_number}</td>
                <td><Badge state={r.status} /></td>
                <td>{r.quantity_reported ?? "—"}</td>
                <td>{r.condition ?? "—"}</td>
                <td>{String(r.created_at).slice(0, 16).replace("T", " ")}</td>
                <td>
                  {(r.status === "AUTO_CREATED") && (
                    <button className="btn" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => confirmReturn(r)}>Confirm quantity + photo</button>
                  )}
                </td>
              </tr>
            ))}
            {!returns.data?.length && <tr><td colSpan={6} style={{ color: "var(--muted)" }}>No returns yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
