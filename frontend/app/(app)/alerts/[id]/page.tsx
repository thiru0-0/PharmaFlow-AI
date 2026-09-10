"use client";
import React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ShieldAlert } from "lucide-react";
import { api, currentUser } from "@/lib/api";
import {
  Alert, Badge, Button, Card, DataGrid, Mono, PromptModal, SkeletonRows,
  StatusBadge, Timeline, TimelineItem, toneFor,
} from "@/lib/ui";

export default function AlertDetail() {
  const { id } = useParams<{ id: string }>();
  const [a, setA] = React.useState<any>(null);
  const [timeline, setTimeline] = React.useState<any>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [resolving, setResolving] = React.useState(false);
  const role = currentUser<any>()?.role;

  async function load() {
    try {
      const alert = await api<any>(`/alerts/reentry/${id}`);
      setA(alert);
      const batches = await api<any[]>("/dashboard/batches");
      const b = batches.find((x) => x.batch_number === alert.batch_number);
      if (b) setTimeline(await api(`/dashboard/batches/${b.batch_id}/timeline`));
    } catch (e: any) { setErr(e.message); }
  }
  React.useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  if (err) return <Alert tone="danger">{err}</Alert>;
  if (!a) return <Card><SkeletonRows rows={6} /></Card>;

  const canResolve = ["STATE_DRUG_CONTROLLER", "ADMIN"].includes(role) && a.status === "OPEN";

  return (
    <div className="space-y-5">
      <Link href="/alerts" className="inline-flex items-center gap-1.5 text-[13px] font-medium text-muted hover:text-ink">
        <ArrowLeft size={15} /> All alerts
      </Link>

      <div className="rounded-[var(--radius-card)] bg-danger-soft p-5 ring-1 ring-inset ring-danger/25">
        <div className="flex flex-wrap items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-danger text-white"><ShieldAlert size={18} /></span>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[18px] font-semibold text-ink"><Mono className="text-[16px] text-ink">{a.batch_number}</Mono></h1>
              <Badge tone="danger">{a.severity} re-entry</Badge>
              <StatusBadge value={a.status} />
            </div>
            <p className="mt-0.5 text-[13px] text-ink-soft">A returned batch was scanned for sale and blocked at the point of sale.</p>
          </div>
          {canResolve && (
            <Button className="ml-auto" variant="secondary" onClick={() => setResolving(true)}>Resolve investigation</Button>
          )}
        </div>

        <div className="mt-4">
          <DataGrid
            items={[
              { label: "Manufacturer license", value: <Mono>{a.manufacturer_license_id}</Mono> },
              { label: "Batch state at attempt", value: a.batch_state_at_attempt?.replaceAll("_", " ") },
              { label: "Attempted retailer", value: a.attempted_retailer },
              { label: "Scan location", value: a.attempted_location },
              { label: "Original return location", value: a.origin_location || "—" },
              { label: "Attempted quantity", value: a.attempted_quantity },
              { label: "Triggered", value: String(a.triggered_at).slice(0, 19).replace("T", " ") },
              { label: "Notification latency", value: `${a.notification_latency_ms} ms` },
              { label: "Notified", value: `Controller ${a.notified_controller ? "✓" : "✗"} · Manufacturer ${a.notified_manufacturer ? "✓" : "✗"}` },
            ]}
          />
        </div>
        {a.resolution_notes && (
          <p className="mt-4 text-[13px] text-ink-soft"><span className="font-semibold text-ink">Resolution:</span> {a.resolution_notes}</p>
        )}
      </div>

      {timeline && (
        <Card
          title="Registry timeline for this batch"
          actions={<Badge tone={timeline.verification.valid ? "success" : "danger"} dot>{timeline.verification.valid ? "Chain valid" : "Invalid"}</Badge>}
        >
          <Timeline>
            {timeline.timeline.map((e: any, i: number) => (
              <TimelineItem
                key={e.seq}
                tone={toneFor(e.event_type)}
                title={e.event_type.replaceAll("_", " ")}
                actor={e.actor}
                time={String(e.created_at).slice(0, 19).replace("T", " ")}
                last={i === timeline.timeline.length - 1}
              >
                <Mono className="text-muted">{JSON.stringify(e.payload)}</Mono>
              </TimelineItem>
            ))}
          </Timeline>
        </Card>
      )}

      <PromptModal
        open={resolving}
        onClose={() => setResolving(false)}
        title="Resolve investigation"
        label="Resolution note"
        hint="Appends a resolution event to the registry — the original alert is never erased."
        submitLabel="Resolve"
        onSubmit={async (v) => {
          if (!v.trim()) throw new Error("A resolution note is required");
          await api(`/alerts/reentry/${id}/resolve`, { method: "POST", body: { resolution_notes: v } });
          setResolving(false); load();
        }}
      />
    </div>
  );
}
