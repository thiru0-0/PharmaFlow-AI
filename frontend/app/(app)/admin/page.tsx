"use client";
import React from "react";
import { RotateCcw, ShieldAlert, CheckCircle2, GitBranch, Timer, Gauge } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, EmptyState, Mono, PageHeader } from "@/lib/ui";

type Action = { label: string; path: string; icon: React.ReactNode; danger?: boolean; desc: string };

const ACTIONS: Action[] = [
  { label: "Reset demo data", path: "/demo/reset", icon: <RotateCcw size={15} />, danger: true, desc: "Restore the exact seeded state (batches A–I)." },
  { label: "Run fraud scenario", path: "/demo/scripts/fraud", icon: <ShieldAlert size={15} />, desc: "Retailer A returns Batch D → Retailer B is blocked at POS." },
  { label: "Run happy path", path: "/demo/scripts/happy", icon: <CheckCircle2 size={15} />, desc: "Full lifecycle to DESTROYED_CERTIFIED with a valid chain." },
  { label: "Run dispute scenario", path: "/demo/scripts/dispute", icon: <GitBranch size={15} />, desc: "Mismatched pickup quantity opens a dispute and blocks the batch." },
  { label: "Run expiry job", path: "/demo/jobs/expiry", icon: <Timer size={15} />, desc: "60-day alerts + auto return requests (idempotent)." },
  { label: "Run SLA scan", path: "/demo/jobs/sla", icon: <Gauge size={15} />, desc: "Flag return/disposal-window breaches as NON_COMPLIANT." },
  { label: "Registry integrity check", path: "/demo/jobs/verify", icon: <ShieldAlert size={15} />, desc: "Re-walk every chain, recompute hashes, verify signatures." },
];

export default function AdminPage() {
  const [log, setLog] = React.useState<any[]>([]);
  const [busy, setBusy] = React.useState<string | null>(null);

  async function run(a: Action) {
    setBusy(a.path);
    const t0 = performance.now();
    try {
      const res = await api<any>(a.path, { method: "POST" });
      setLog((l) => [{ label: a.label, ms: Math.round(performance.now() - t0), res, at: new Date().toLocaleTimeString() }, ...l]);
    } catch (e: any) {
      setLog((l) => [{ label: a.label, err: e.message, at: new Date().toLocaleTimeString() }, ...l]);
    } finally { setBusy(null); }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Demo Control"
        description="Scripted scenarios run the real workflow against the database and report elapsed time. Reset is re-runnable for a live demo."
      />

      <Card title="Actions">
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {ACTIONS.map((a) => (
            <button
              key={a.path}
              disabled={!!busy}
              onClick={() => run(a)}
              className={`rounded-xl p-4 text-left ring-1 ring-inset transition-colors disabled:opacity-50 ${
                a.danger ? "bg-danger-soft ring-danger/20 hover:bg-danger-soft/70" : "bg-surface ring-line hover:bg-surface-2"
              }`}
            >
              <div className={`flex items-center gap-2 text-[13.5px] font-semibold ${a.danger ? "text-danger" : "text-ink"}`}>
                {busy === a.path ? <span className="animate-[pf-spin_.7s_linear_infinite]">{a.icon}</span> : a.icon}
                {a.label}
              </div>
              <p className="mt-1 text-[12px] text-muted">{a.desc}</p>
            </button>
          ))}
        </div>
      </Card>

      <Card title="Run log">
        {log.length ? (
          <div className="space-y-3">
            {log.map((e, i) => (
              <div key={i} className="rounded-xl border border-line-soft p-3.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[13px] font-semibold text-ink">{e.label}</span>
                  <span className="flex items-center gap-2">
                    {e.err ? <Badge tone="danger">error</Badge> : <Badge tone="success">ok · {e.ms} ms</Badge>}
                    <span className="text-[11.5px] text-muted tabular-nums">{e.at}</span>
                  </span>
                </div>
                {e.err
                  ? <p className="mt-2 text-[12.5px] font-medium text-danger">{e.err}</p>
                  : <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-surface-2 p-3 text-[11.5px] leading-relaxed text-ink-soft ring-1 ring-inset ring-line"><Mono>{JSON.stringify(e.res, null, 2)}</Mono></pre>}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={<Timer size={18} />} title="No runs yet" description="Trigger an action above to see its result and timing here." />
        )}
      </Card>
    </div>
  );
}
