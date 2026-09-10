"use client";
import React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Badge, Card } from "@/lib/ui";

const STEPS = ["ACTIVE", "RETURN_INITIATED", "PICKUP_SCHEDULED", "PICKUP_CONFIRMED", "RECEIVED_BY_MANUFACTURER", "DESTROYED_CERTIFIED"];

export default function BatchDetail() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = React.useState<any>(null);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    api(`/dashboard/batches/${id}/timeline`).then(setD).catch((e) => setErr(e.message));
  }, [id]);

  if (err) return <p style={{ color: "var(--danger)" }}>{err}</p>;
  if (!d) return <p>Loading…</p>;
  const b = d.batch;
  const curIdx = STEPS.indexOf(b.state);

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <Link href="/registry">← Registry</Link>
      <div className="card" style={{ padding: 20 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <h1 style={{ margin: 0, fontSize: 20 }}>{b.batch_number}</h1>
          <Badge state={b.state} />
          {b.non_compliant && <span className="badge red">NON-COMPLIANT</span>}
          {b.reentry_flagged && <span className="badge red">RE-ENTRY FLAGGED</span>}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 12, marginTop: 12, fontSize: 14 }}>
          <div><div className="label">Drug</div>{b.drug_name}</div>
          <div><div className="label">Category</div>{b.category}</div>
          <div><div className="label">Manufacturer license</div><span className="mono">{b.manufacturer_license_id}</span></div>
          <div><div className="label">Expiry</div>{String(b.expiry_date).slice(0, 10)}</div>
          <div><div className="label">Flagged at</div>{b.flagged_at ? String(b.flagged_at).slice(0, 19).replace("T", " ") : "—"}</div>
        </div>
      </div>

      <Card title="Lifecycle progress">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {STEPS.map((s, i) => (
            <div key={s} className="badge" style={{
              background: i <= curIdx ? "var(--brand)" : "#f1f5f9",
              color: i <= curIdx ? "#fff" : "#94a3b8",
            }}>{s.replaceAll("_", " ")}</div>
          ))}
        </div>
      </Card>

      <Card title="Registry integrity">
        <span className={`badge ${d.verification.valid ? "green" : "red"}`}>
          {d.verification.valid ? "VALID — hash chain + signatures + ordering ok" : "INVALID"}
        </span>{" "}
        <span>{d.verification.event_count} events</span>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card title="Return"><Pre v={d.return_request} /></Card>
        <Card title="Dispute"><Pre v={d.dispute} /></Card>
        <Card title="Manufacturer receipt"><Pre v={d.receipt} /></Card>
        <Card title="Destruction certificate"><Pre v={d.certificate} /></Card>
      </div>

      {!!d.reentry_alerts?.length && (
        <Card title="Re-entry alerts">
          {d.reentry_alerts.map((a: any) => (
            <div key={a.id}><Link href={`/alerts/${a.id}`}>{a.attempted_retailer}</Link> · {a.attempted_location} · <Badge state={a.status} /></div>
          ))}
        </Card>
      )}

      <Card title="Event timeline">
        <ol style={{ margin: 0, paddingLeft: 18 }}>
          {d.timeline.map((e: any) => (
            <li key={e.seq} style={{ marginBottom: 8 }}>
              <span className="badge blue">{e.event_type}</span>{" "}
              <span style={{ color: "var(--muted)" }}>{String(e.created_at).slice(0, 19).replace("T", " ")} · {e.actor}</span>
              <div className="mono" style={{ color: "var(--muted)" }}>{JSON.stringify(e.payload)}</div>
              <div className="mono" style={{ color: "var(--muted)", fontSize: 11 }}>hash {e.hash.slice(0, 24)}…</div>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}

function Pre({ v }: { v: any }) {
  if (!v) return <p style={{ color: "var(--muted)" }}>—</p>;
  return <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(v, null, 2)}</pre>;
}
