"use client";
import React from "react";
import Link from "next/link";
import { Activity, Boxes, Download, ShieldCheck, ShieldX, TriangleAlert } from "lucide-react";
import { api, API, getToken } from "@/lib/api";
import {
  Alert, Badge, Button, Card, EmptyState, Mono, PageHeader, SkeletonRows,
  StatCard, StatusBadge, Table, Td, Tr, useAsync,
} from "@/lib/ui";

const FUNNEL = [
  "ACTIVE", "RETURN_INITIATED", "PICKUP_SCHEDULED", "DISPUTED",
  "PICKUP_CONFIRMED", "RECEIVED_BY_MANUFACTURER", "DESTROYED_CERTIFIED",
];

export default function Dashboard() {
  const sum = useAsync<any>(() => api("/dashboard/summary"), []);
  const dir = useAsync<any[]>(() => api("/dashboard/directory"), []);
  const [feed, setFeed] = React.useState<any[]>([]);
  const lastId = React.useRef(0);

  React.useEffect(() => {
    let alive = true;
    let t: ReturnType<typeof setInterval> | undefined;
    async function poll() {
      try {
        const r = await api<any>(`/dashboard/events/stream?since_id=${lastId.current}`);
        if (!alive || !r.events.length) return;
        lastId.current = Math.max(lastId.current, r.last_id);
        setFeed((f) => {
          const seen = new Set(f.map((x: any) => x.id));
          const fresh = r.events.filter((x: any) => !seen.has(x.id));
          return [...fresh.reverse(), ...f].slice(0, 30);
        });
      } catch {
        if (t) clearInterval(t); // stop polling on auth/network failure
      }
    }
    poll();
    t = setInterval(poll, 3500);
    return () => { alive = false; if (t) clearInterval(t); };
  }, []);

  async function downloadCsv() {
    const res = await fetch(`${API}/dashboard/compliance-export.csv`, { headers: { Authorization: `Bearer ${getToken()}` } });
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url; a.download = "pharmaflow_compliance_export.csv"; a.click();
    URL.revokeObjectURL(url);
  }

  const s = sum.data;
  const funnel = s?.funnel || {};
  const funnelMax = Math.max(1, ...FUNNEL.map((k) => funnel[k] || 0));
  const health = s?.registry_health;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Control Tower"
        description="Network-wide status across the reverse chain — flags, disputes, SLA breaches and registry integrity."
        actions={<Button variant="secondary" icon={<Download size={15} />} onClick={downloadCsv}>Compliance CSV</Button>}
      />

      {sum.loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><SkeletonRows rows={1} cols={4} /></div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Batches tracked" value={s?.totals?.batches ?? "—"} icon={<Boxes size={15} />} hint={`${s?.totals?.in_return_pipeline ?? 0} in the return pipeline`} />
          <StatCard label="Destroyed & certified" value={s?.totals?.destroyed_certified ?? "—"} tone="neutral" icon={<ShieldCheck size={15} />} />
          <StatCard label="Non-compliant" value={s?.totals?.non_compliant ?? "—"} tone={s?.totals?.non_compliant ? "danger" : "success"} icon={<TriangleAlert size={15} />} />
          <StatCard label="Re-entry flagged" value={s?.totals?.reentry_flagged ?? "—"} tone={s?.totals?.reentry_flagged ? "danger" : "success"} icon={<ShieldX size={15} />} />
        </div>
      )}

      <Card title="Batch funnel" description="Live counts at each lifecycle state.">
        <div className="space-y-2.5">
          {FUNNEL.map((k) => {
            const n = funnel[k] || 0;
            return (
              <div key={k} className="flex items-center gap-3">
                <span className="w-52 shrink-0 text-[12px] font-medium text-ink-soft">{k.replaceAll("_", " ")}</span>
                <div className="h-6 flex-1 overflow-hidden rounded-md bg-line-soft">
                  <div
                    className={`h-full rounded-md ${k === "DISPUTED" ? "bg-danger" : k === "DESTROYED_CERTIFIED" ? "bg-muted" : "bg-brand"}`}
                    style={{ width: `${Math.max(n ? 8 : 0, (n / funnelMax) * 100)}%` }}
                  />
                </div>
                <span className="w-8 shrink-0 text-right text-[13px] font-semibold tabular-nums text-ink">{n}</span>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Re-entry alerts">
          {sum.loading ? <SkeletonRows rows={3} cols={1} /> : s?.reentry_alerts?.length ? (
            <ul className="divide-y divide-line-soft">
              {s.reentry_alerts.map((a: any) => (
                <li key={a.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <Link href={`/alerts/${a.id}`} className="font-semibold text-ink hover:text-brand"><Mono className="text-[12.5px] text-ink">{a.batch_number}</Mono></Link>
                    <div className="text-[11.5px] text-muted">
                      {a.attempted_retailer} · {a.notification_latency_ms}ms · ctrl {a.notified_controller ? "✓" : "✗"} · mfr {a.notified_manufacturer ? "✓" : "✗"}
                    </div>
                  </div>
                  <StatusBadge value={a.status} />
                </li>
              ))}
            </ul>
          ) : <EmptyState icon={<ShieldCheck size={18} />} title="No re-entry alerts" description="Blocked sale attempts on flagged batches show up here." />}
        </Card>

        <Card title="Open disputes">
          {sum.loading ? <SkeletonRows rows={3} cols={1} /> : s?.open_disputes?.length ? (
            <ul className="divide-y divide-line-soft">
              {s.open_disputes.map((d: any) => (
                <li key={d.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                  <Link href="/disputes" className="text-[13px] font-medium text-ink hover:text-brand">Dispute {d.id.slice(0, 8)}</Link>
                  <span className="text-[12.5px] text-muted">reported {d.reported_qty} · confirmed {d.confirmed_qty}</span>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon={<ShieldCheck size={18} />} title="No open disputes" description="Quantity mismatches beyond tolerance appear here." />}
        </Card>
      </div>

      {health && (
        <Card title="Registry integrity">
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={health.healthy ? "success" : "danger"} dot>
              {health.healthy ? "Healthy — hash chain & signatures valid" : "Integrity breach detected"}
            </Badge>
            <span className="text-[12.5px] text-muted">{health.total_events} events · {health.batches_checked} chains checked</span>
            <Link href="/registry" className="ml-auto text-[12.5px] font-semibold text-brand hover:underline">Open Registry Explorer →</Link>
          </div>
          {!!health.breaches?.length && (
            <Mono className="mt-2 block text-danger">{JSON.stringify(health.breaches)}</Mono>
          )}
        </Card>
      )}

      <Card title="Live event feed" description="3.5s poll over the append-only registry stream." bodyClassName="max-h-[340px] overflow-y-auto">
        {feed.length ? (
          <ul className="space-y-1.5">
            {feed.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-2 text-[12px]">
                <span className="text-muted tabular-nums">{String(e.created_at).slice(11, 19)}</span>
                <Badge tone="info">{e.event_type}</Badge>
                <span className="font-medium text-ink">{e.batch_number}</span>
                <span className="text-muted">· {e.actor}</span>
                <Mono className="text-muted">{e.hash.slice(0, 12)}…</Mono>
              </li>
            ))}
          </ul>
        ) : (
          <div className="flex items-center gap-2 py-4 text-[13px] text-muted"><Activity size={15} /> Waiting for events…</div>
        )}
      </Card>

      <Card title="Network directory" padded={false}>
        <div className="p-5">
          {dir.loading ? <SkeletonRows /> : (
            <Table head={["Name", "Role", "License", "Status", "Location"]} empty={!dir.data?.length}>
              {(dir.data || []).map((u) => (
                <Tr key={u.id}>
                  <Td className="font-medium text-ink">{u.name}</Td>
                  <Td>{u.role?.replaceAll("_", " ")}</Td>
                  <Td><Mono>{u.license}</Mono></Td>
                  <Td>{u.license_status ? <StatusBadge value={u.license_status} /> : "—"}</Td>
                  <Td className="text-muted">{u.location}</Td>
                </Tr>
              ))}
            </Table>
          )}
        </div>
      </Card>
    </div>
  );
}
