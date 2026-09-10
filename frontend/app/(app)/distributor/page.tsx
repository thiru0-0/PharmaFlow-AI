"use client";
import React from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge, Card, useAsync } from "@/lib/ui";

export default function DistributorPage() {
  const pending = useAsync<any[]>(() => api("/distributor/returns/pending"), []);
  const pickups = useAsync<any[]>(() => api("/distributor/pickups"), []);
  const routes = useAsync<any[]>(() => api("/distributor/routes"), []);
  const [msg, setMsg] = React.useState<string | null>(null);

  function reloadAll() { pending.reload(); pickups.reload(); routes.reload(); }

  async function optimize() {
    setMsg(null);
    try {
      const r = await api<any>("/distributor/routes/optimize", { method: "POST", body: { vehicle_capacity: 500 } });
      setMsg(`Route: ${r.stops.length} stops · ${r.total_distance_km} km · cost ₹${r.total_cost} · ${r.ortools_used ? "OR-Tools CVRP" : "nearest-neighbour fallback"}`);
      reloadAll();
    } catch (e) { setMsg((e as any).message); }
  }

  async function confirm(p: any) {
    const q = prompt(`Confirmed (weight-verified) quantity for ${p.batch_number}? (retailer reported ${p.quantity_reported})`, String(p.quantity_reported ?? ""));
    if (!q) return;
    try {
      const r = await api<any>(`/distributor/pickups/${p.pickup_id}/confirm`, { method: "POST", body: { quantity_confirmed: Number(q) } });
      setMsg(r.status === "DISPUTED"
        ? `DISPUTE raised: reported ${r.reported_qty} vs confirmed ${r.confirmed_qty} (tolerance ±${r.tolerance_units}) — batch blocked`
        : `Pickup confirmed — batch now ${r.batch_state}`);
      reloadAll();
    } catch (e) { setMsg((e as any).message); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <h1 style={{ margin: 0 }}>Distributor — Pickups &amp; Routing</h1>
      {msg && <div className="card" style={{ padding: 12, fontSize: 14 }}>{msg}</div>}

      <Card title="Pending returns (mapped retailers)" right={<button className="btn" onClick={optimize}>Optimize pickup route</button>}>
        <table>
          <thead><tr><th>Batch</th><th>Retailer</th><th>Location</th><th>Qty</th><th>SLA days left</th><th>Urgency</th><th>State</th></tr></thead>
          <tbody>
            {(pending.data || []).map((p) => (
              <tr key={p.return_id}>
                <td className="mono">{p.batch_number}</td>
                <td>{p.retailer_name}</td>
                <td>{p.retailer_location}</td>
                <td>{p.quantity_reported ?? <span className="badge amber">awaiting retailer count</span>}</td>
                <td>{p.sla_days_left}</td>
                <td>{p.urgency}</td>
                <td><Badge state={p.batch_state} /></td>
              </tr>
            ))}
            {!pending.data?.length && <tr><td colSpan={7} style={{ color: "var(--muted)" }}>No pending returns.</td></tr>}
          </tbody>
        </table>
      </Card>

      <Card title="Optimized routes">
        {(routes.data || []).map((r) => (
          <div key={r.id} style={{ borderBottom: "1px solid var(--line)", padding: "10px 0" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <span className={`badge ${r.ortools_used ? "green" : "amber"}`}>{r.ortools_used ? "OR-Tools CVRP" : "nearest-neighbour fallback"}</span>
              <strong>{r.total_distance_km} km</strong>
              <span>{r.total_duration_min} min</span>
              <span>cost ₹{r.total_cost}</span>
              <span>capacity {r.capacity_used}/{r.vehicle_capacity}</span>
              <span>urgency score {r.urgency_score}</span>
            </div>
            <ol className="mono" style={{ margin: "6px 0 0 18px" }}>
              {r.stops.map((s: any) => (
                <li key={s.seq}>{s.name} — qty {s.quantity}, urgency {s.urgency}, leg {s.leg_km} km</li>
              ))}
            </ol>
          </div>
        ))}
        {!routes.data?.length && <p style={{ color: "var(--muted)" }}>No routes generated yet.</p>}
      </Card>

      <Card title="Pickups" right={<button className="btn secondary" onClick={pickups.reload}>Refresh</button>}>
        <table>
          <thead><tr><th>Batch</th><th>State</th><th>Reported</th><th>Confirmed</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {(pickups.data || []).map((p) => (
              <tr key={p.pickup_id}>
                <td><Link className="mono" href={`/batch/${p.batch_id}`}>{p.batch_number}</Link></td>
                <td><Badge state={p.batch_state} /></td>
                <td>{p.quantity_reported ?? "—"}</td>
                <td>{p.quantity_confirmed ?? "—"}</td>
                <td><Badge state={p.status} /></td>
                <td>
                  {["SCHEDULED"].includes(p.status) && (
                    <button className="btn" style={{ fontSize: 12, padding: "4px 8px" }} onClick={() => confirm(p)}>Confirm pickup</button>
                  )}
                </td>
              </tr>
            ))}
            {!pickups.data?.length && <tr><td colSpan={6} style={{ color: "var(--muted)" }}>No pickups.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
