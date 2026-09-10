"use client";
import React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, currentUser } from "@/lib/api";
import { Badge, Card } from "@/lib/ui";

export default function AlertDetail() {
  const { id } = useParams<{ id: string }>();
  const [a, setA] = React.useState<any>(null);
  const [timeline, setTimeline] = React.useState<any>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const role = currentUser<any>()?.role;

  async function load() {
    try {
      const alert = await api<any>(`/alerts/reentry/${id}`);
      setA(alert);
      const batches = await api<any[]>("/dashboard/batches");
      const b = batches.find((x) => x.batch_number === alert.batch_number);
      if (b) setTimeline(await api(`/dashboard/batches/${b.batch_id}/timeline`));
    } catch (e) { setErr((e as any).message); }
  }
  React.useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  async function resolve() {
    const note = prompt("Investigation resolution note:");
    if (!note) return;
    try { await api(`/alerts/reentry/${id}/resolve`, { method: "POST", body: { resolution_notes: note } }); load(); }
    catch (e) { alert((e as any).message); }
  }

  if (err) return <p style={{ color: "var(--danger)" }}>{err}</p>;
  if (!a) return <p>Loading…</p>;

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <Link href="/alerts">← All alerts</Link>
      <div className="card" style={{ padding: 20, borderColor: "var(--danger)", background: "#fef2f2" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span className="badge red">{a.severity} RE-ENTRY</span>
          <h1 style={{ margin: 0, fontSize: 20 }}>{a.batch_number}</h1>
          <Badge state={a.status} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginTop: 14, fontSize: 14 }}>
          <div><div className="label">Manufacturer license</div><span className="mono">{a.manufacturer_license_id}</span></div>
          <div><div className="label">Batch state at attempt</div>{a.batch_state_at_attempt}</div>
          <div><div className="label">Attempted retailer</div>{a.attempted_retailer}</div>
          <div><div className="label">Scan location</div>{a.attempted_location}</div>
          <div><div className="label">Original return location</div>{a.origin_location || "—"}</div>
          <div><div className="label">Attempted sale quantity</div>{a.attempted_quantity}</div>
          <div><div className="label">Triggered</div>{String(a.triggered_at).slice(0, 19).replace("T", " ")}</div>
          <div><div className="label">Notification latency</div>{a.notification_latency_ms} ms</div>
          <div><div className="label">State Drug Controller</div>{a.notified_controller ? "✓ notified" : "✗"}</div>
          <div><div className="label">Manufacturer</div>{a.notified_manufacturer ? "✓ notified" : "✗"}</div>
        </div>
        {a.resolution_notes && <p style={{ marginTop: 12 }}><b>Resolution:</b> {a.resolution_notes}</p>}
        {["STATE_DRUG_CONTROLLER", "ADMIN"].includes(role) && a.status === "OPEN" && (
          <button className="btn ok" style={{ marginTop: 12 }} onClick={resolve}>Resolve investigation</button>
        )}
      </div>

      {timeline && (
        <Card title="Complete registry timeline for this batch">
          <div style={{ marginBottom: 10 }}>
            <span className={`badge ${timeline.verification.valid ? "green" : "red"}`}>
              chain {timeline.verification.valid ? "valid" : "INVALID"}
            </span>
          </div>
          <ol style={{ margin: 0, paddingLeft: 18 }}>
            {timeline.timeline.map((e: any) => (
              <li key={e.seq} style={{ marginBottom: 8 }}>
                <span className="badge blue">{e.event_type}</span>{" "}
                <span style={{ color: "var(--muted)" }}>{String(e.created_at).slice(0, 19).replace("T", " ")} · {e.actor}</span>
                <div className="mono" style={{ color: "var(--muted)" }}>{JSON.stringify(e.payload)}</div>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}
