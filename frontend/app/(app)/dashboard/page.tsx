"use client";
import React from "react";
import Link from "next/link";
import { api, API, getToken } from "@/lib/api";
import { Badge, Card, Stat, useAsync } from "@/lib/ui";

export default function Dashboard() {
  const sum = useAsync<any>(() => api("/dashboard/summary"), []);
  const dir = useAsync<any[]>(() => api("/dashboard/directory"), []);
  const [feed, setFeed] = React.useState<any[]>([]);
  const lastId = React.useRef(0);

  React.useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const r = await api<any>(`/dashboard/events/stream?since_id=${lastId.current}`);
        if (!alive) return;
        if (r.events.length) {
          lastId.current = r.last_id;
          setFeed((f) => [...r.events.reverse(), ...f].slice(0, 40));
        }
      } catch {}
    }
    poll();
    const t = setInterval(poll, 3500);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const s = sum.data;
  const funnel = s?.funnel || {};
  const order = ["ACTIVE", "RETURN_INITIATED", "PICKUP_SCHEDULED", "DISPUTED", "PICKUP_CONFIRMED", "RECEIVED_BY_MANUFACTURER", "DESTROYED_CERTIFIED"];

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>Control Tower</h1>
        <a className="btn secondary" href={`${API}/dashboard/compliance-export.csv`}
          onClick={(e) => { e.preventDefault(); downloadCsv(); }}>Export compliance CSV</a>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 12 }}>
        <Stat label="Batches" value={s?.totals?.batches ?? "—"} />
        <Stat label="In return pipeline" value={s?.totals?.in_return_pipeline ?? "—"} />
        <Stat label="Destroyed + certified" value={s?.totals?.destroyed_certified ?? "—"} />
        <Stat label="Non-compliant" value={s?.totals?.non_compliant ?? "—"} tone={s?.totals?.non_compliant ? "danger" : ""} />
        <Stat label="Re-entry flagged" value={s?.totals?.reentry_flagged ?? "—"} tone={s?.totals?.reentry_flagged ? "danger" : ""} />
        <Stat label="Compliance rate" value={s ? `${Math.round(s.compliance_rate * 100)}%` : "—"} />
      </div>

      <Card title="Batch funnel">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {order.map((k) => (
            <div key={k} className="card" style={{ padding: "10px 14px", minWidth: 120 }}>
              <div style={{ fontSize: 22, fontWeight: 800 }}>{funnel[k] ?? 0}</div>
              <div className="label">{k.replaceAll("_", " ")}</div>
            </div>
          ))}
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <Card title="Re-entry alerts">
          {(s?.reentry_alerts || []).map((a: any) => (
            <div key={a.id} style={{ borderBottom: "1px solid var(--line)", padding: "8px 0", display: "flex", justifyContent: "space-between", gap: 8 }}>
              <div>
                <Link href={`/alerts/${a.id}`}><strong className="mono">{a.batch_number}</strong></Link>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>
                  {a.attempted_retailer} · {a.notification_latency_ms}ms · ctrl {a.notified_controller ? "✓" : "✗"} · mfr {a.notified_manufacturer ? "✓" : "✗"}
                </div>
              </div>
              <Badge state={a.status} />
            </div>
          ))}
          {!s?.reentry_alerts?.length && <p style={{ color: "var(--muted)" }}>No re-entry alerts.</p>}
        </Card>

        <Card title="Open disputes">
          {(s?.open_disputes || []).map((d: any) => (
            <div key={d.id} style={{ borderBottom: "1px solid var(--line)", padding: "8px 0" }}>
              <Link href="/disputes" className="mono">dispute {d.id.slice(0, 8)}</Link>
              <span style={{ marginLeft: 8, fontSize: 13 }}>reported {d.reported_qty} vs confirmed {d.confirmed_qty}</span>
            </div>
          ))}
          {!s?.open_disputes?.length && <p style={{ color: "var(--muted)" }}>No open disputes.</p>}
        </Card>
      </div>

      <Card title="Registry integrity" right={<Link className="btn secondary" href="/registry">Open explorer</Link>}>
        {s?.registry_health ? (
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <span className={`badge ${s.registry_health.healthy ? "green" : "red"}`}>
              {s.registry_health.healthy ? "HEALTHY — hash chain + signatures valid" : "INTEGRITY BREACH DETECTED"}
            </span>
            <span>{s.registry_health.total_events} events</span>
            <span>{s.registry_health.batches_checked} chains checked</span>
            {!!s.registry_health.breaches?.length && (
              <span className="mono" style={{ color: "var(--danger)" }}>{JSON.stringify(s.registry_health.breaches)}</span>
            )}
          </div>
        ) : <p style={{ color: "var(--muted)" }}>Regulator/admin only.</p>}
      </Card>

      <Card title="Live event feed (3.5s poll over the registry stream)">
        <div style={{ display: "grid", gap: 4, maxHeight: 320, overflow: "auto" }}>
          {feed.map((e) => (
            <div key={e.id} className="mono" style={{ fontSize: 12 }}>
              <span style={{ color: "var(--muted)" }}>{String(e.created_at).slice(11, 19)}</span>{" "}
              <span className="badge blue" style={{ fontSize: 11 }}>{e.event_type}</span>{" "}
              {e.batch_number} · {e.actor} · <span style={{ color: "var(--muted)" }}>{e.hash.slice(0, 12)}…</span>
            </div>
          ))}
          {!feed.length && <p style={{ color: "var(--muted)" }}>Waiting for events…</p>}
        </div>
      </Card>

      <Card title="Network directory">
        <table>
          <thead><tr><th>Name</th><th>Role</th><th>License</th><th>Status</th><th>Location</th></tr></thead>
          <tbody>
            {(dir.data || []).map((u) => (
              <tr key={u.id}>
                <td>{u.name}</td><td>{u.role?.replaceAll("_", " ")}</td>
                <td className="mono">{u.license}</td>
                <td>{u.license_status ? <Badge state={u.license_status} /> : "—"}</td>
                <td>{u.location}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

async function downloadCsv() {
  const res = await fetch(`${API}/dashboard/compliance-export.csv`, { headers: { Authorization: `Bearer ${getToken()}` } });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "pharmaflow_compliance_export.csv"; a.click();
  URL.revokeObjectURL(url);
}
