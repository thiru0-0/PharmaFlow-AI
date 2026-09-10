"use client";
import React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ShieldCheck, ShieldX } from "lucide-react";
import { api } from "@/lib/api";
import {
  Alert, Badge, Card, DataGrid, Mono, SkeletonRows, StatusBadge,
  Timeline, TimelineItem, toneFor,
} from "@/lib/ui";
import { onLive } from "@/lib/realtime";

const STEPS = ["ACTIVE", "RETURN_INITIATED", "PICKUP_SCHEDULED", "PICKUP_CONFIRMED", "RECEIVED_BY_MANUFACTURER", "DESTROYED_CERTIFIED"];

export default function BatchDetail() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = React.useState<any>(null);
  const [err, setErr] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    api(`/dashboard/batches/${id}/timeline`).then(setD).catch((e) => setErr(e.message));
  }, [id]);

  React.useEffect(() => { load(); }, [load]);

  React.useEffect(
    () => onLive((e) => {
      if ((e.kind === "registry" || e.kind === "reentry") && e.batch_id === id) load();
    }),
    [id, load]
  );

  if (err) return <Alert tone="danger">{err}</Alert>;
  if (!d) return <Card><SkeletonRows rows={7} /></Card>;

  const b = d.batch;
  const curIdx = STEPS.indexOf(b.state === "DISPUTED" ? "PICKUP_SCHEDULED" : b.state);

  return (
    <div className="space-y-5">
      <Link href="/registry" className="inline-flex items-center gap-1.5 text-[13px] font-medium text-muted hover:text-ink">
        <ArrowLeft size={15} /> Registry Explorer
      </Link>

      <Card>
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-[18px] font-semibold text-ink"><Mono className="text-[16px] text-ink">{b.batch_number}</Mono></h1>
          <StatusBadge value={b.state} />
          {b.non_compliant && <Badge tone="danger">Non-compliant</Badge>}
          {b.reentry_flagged && <Badge tone="danger">Re-entry flagged</Badge>}
        </div>
        <div className="mt-4">
          <DataGrid
            items={[
              { label: "Drug", value: b.drug_name },
              { label: "Category", value: b.category },
              { label: "Manufacturer license", value: <Mono>{b.manufacturer_license_id}</Mono> },
              { label: "Manufactured", value: String(b.mfg_date).slice(0, 10) },
              { label: "Expiry", value: String(b.expiry_date).slice(0, 10) },
              { label: "Flagged at", value: b.flagged_at ? String(b.flagged_at).slice(0, 19).replace("T", " ") : "—" },
            ]}
          />
        </div>
      </Card>

      <Card title="Lifecycle">
        <div className="flex flex-wrap items-center gap-1.5">
          {STEPS.map((s, i) => (
            <React.Fragment key={s}>
              <span
                className={`rounded-full px-2.5 py-1 text-[11.5px] font-semibold ${
                  i < curIdx ? "bg-brand-soft text-brand"
                  : i === curIdx ? "bg-brand text-white"
                  : "bg-line-soft text-muted"
                }`}
              >
                {s.replaceAll("_", " ")}
              </span>
              {i < STEPS.length - 1 && <span className="text-line">—</span>}
            </React.Fragment>
          ))}
        </div>
        {b.state === "DISPUTED" && <p className="mt-3 text-[12.5px] font-medium text-danger">Currently disputed — blocked at pickup confirmation.</p>}
      </Card>

      <Card
        title="Registry integrity"
        actions={
          <Badge tone={d.verification.valid ? "success" : "danger"} dot>
            {d.verification.valid ? "Valid" : "Invalid"}
          </Badge>
        }
      >
        <div className="flex flex-wrap gap-4 text-[12.5px] text-ink-soft">
          {[
            ["Hash chain", d.verification.hash_chain_valid],
            ["Signatures", d.verification.signatures_valid],
            ["Ordering", d.verification.ordering_valid],
          ].map(([k, ok]) => (
            <span key={k as string} className="inline-flex items-center gap-1.5">
              {ok ? <ShieldCheck size={14} className="text-ok" /> : <ShieldX size={14} className="text-danger" />}{k}
            </span>
          ))}
          <span className="text-muted">{d.verification.event_count} events</span>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <RecordCard title="Return request" v={d.return_request} />
        <RecordCard title="Dispute" v={d.dispute} />
        <RecordCard title="Manufacturer receipt" v={d.receipt} />
        <RecordCard title="Destruction certificate" v={d.certificate} />
      </div>

      {!!d.reentry_alerts?.length && (
        <Card title="Re-entry alerts">
          <ul className="space-y-2">
            {d.reentry_alerts.map((a: any) => (
              <li key={a.id} className="flex items-center gap-2 text-[13px]">
                <Link href={`/alerts/${a.id}`} className="font-medium text-brand hover:underline">{a.attempted_retailer}</Link>
                <span className="text-muted">· {a.attempted_location}</span>
                <StatusBadge value={a.status} />
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Activity timeline">
        <Timeline>
          {d.timeline.map((e: any, i: number) => (
            <TimelineItem
              key={e.seq}
              tone={toneFor(e.event_type)}
              title={e.event_type.replaceAll("_", " ")}
              actor={e.actor}
              time={String(e.created_at).slice(0, 19).replace("T", " ")}
              last={i === d.timeline.length - 1}
            >
              <Mono className="text-muted">{JSON.stringify(e.payload)}</Mono>
            </TimelineItem>
          ))}
        </Timeline>
      </Card>
    </div>
  );
}

function RecordCard({ title, v }: { title: string; v: any }) {
  return (
    <Card title={title}>
      {v ? (
        <dl className="space-y-1.5 text-[12.5px]">
          {Object.entries(v).map(([k, val]) => (
            <div key={k} className="flex gap-3">
              <dt className="w-32 shrink-0 text-muted">{k.replaceAll("_", " ")}</dt>
              <dd className="min-w-0 break-words text-ink">{String(val)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-[13px] text-muted">Not reached yet.</p>
      )}
    </Card>
  );
}
