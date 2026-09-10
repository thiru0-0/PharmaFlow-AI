"use client";
import React from "react";
import {
  RotateCcw, ShieldAlert, CheckCircle2, GitBranch, Timer, Gauge, Activity, ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, EmptyState, Mono, PageHeader } from "@/lib/ui";

type Action = { label: string; path: string; icon: React.ReactNode; danger?: boolean; desc: string };

const GROUPS: { title: string; items: Action[] }[] = [
  {
    title: "Demo setup",
    items: [
      { label: "Reset demo data", path: "/demo/reset", icon: <RotateCcw size={15} />, danger: true, desc: "Restore the exact seeded state (batches A–I). Run this between demo runs." },
    ],
  },
  {
    title: "Scripted scenarios",
    items: [
      { label: "Run fraud scenario", path: "/demo/scripts/fraud", icon: <ShieldAlert size={15} />, desc: "Retailer A returns Batch D → Retailer B is blocked at the counter, both parties alerted." },
      { label: "Run happy path", path: "/demo/scripts/happy", icon: <CheckCircle2 size={15} />, desc: "One batch all the way to DESTROYED_CERTIFIED with a valid chain." },
      { label: "Run dispute scenario", path: "/demo/scripts/dispute", icon: <GitBranch size={15} />, desc: "A mismatched pickup quantity opens a dispute and freezes the batch." },
    ],
  },
  {
    title: "Background jobs (run automatically every ~90s in demo mode)",
    items: [
      { label: "Run expiry job", path: "/demo/jobs/expiry", icon: <Timer size={15} />, desc: "60-day alerts + auto return requests. Idempotent." },
      { label: "Run SLA scan", path: "/demo/jobs/sla", icon: <Gauge size={15} />, desc: "Flag return / disposal-window breaches as NON_COMPLIANT." },
      { label: "Registry integrity check", path: "/demo/jobs/verify", icon: <ShieldCheck size={15} />, desc: "Re-walk every chain, recompute hashes, verify signatures." },
    ],
  },
];

const PULSE = { label: "Simulate activity", path: "/demo/scripts/pulse", icon: <Activity size={15} />, desc: "A small burst — a couple of sales and one batch advancing a step." };

export default function AdminPage() {
  const [log, setLog] = React.useState<any[]>([]);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [autoPulse, setAutoPulse] = React.useState(false);

  const run = React.useCallback(async (a: Action, quiet = false) => {
    if (!quiet) setBusy(a.path);
    const t0 = performance.now();
    try {
      const res = await api<any>(a.path, { method: "POST" });
      setLog((l) => [{ label: a.label, ms: Math.round(performance.now() - t0), res, at: new Date().toLocaleTimeString() }, ...l].slice(0, 25));
    } catch (e: any) {
      setLog((l) => [{ label: a.label, err: e.message, at: new Date().toLocaleTimeString() }, ...l].slice(0, 25));
    } finally { if (!quiet) setBusy(null); }
  }, []);

  React.useEffect(() => {
    if (!autoPulse) return;
    const t = setInterval(() => run(PULSE, true), 8000);
    return () => clearInterval(t);
  }, [autoPulse, run]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Demo Control"
        description="A presenter panel — not a production feature. Scripted scenarios run the real workflow against the database."
      />

      <Card title="How to run the demo">
        <ol className="space-y-1.5 text-[13px] text-ink-soft">
          <li><b className="text-ink">1.</b> Click <b>Reset demo data</b> to get a clean, known state.</li>
          <li><b className="text-ink">2.</b> Turn on <b>Keep simulating</b> so the Control Tower moves on its own while you talk.</li>
          <li><b className="text-ink">3.</b> Open the <b>State Drug Controller → Control Tower</b> on a second screen. Everything below updates it live.</li>
          <li><b className="text-ink">4.</b> Run <b>fraud scenario</b> for the headline moment, or drive it by hand: sign in as Retailer A, initiate Batch D&apos;s return, then sign in as Retailer B and try to sell it.</li>
          <li><b className="text-ink">5.</b> Reset and repeat.</li>
        </ol>
      </Card>

      <Card
        title="Live activity"
        actions={
          <label className="flex cursor-pointer items-center gap-2 text-[13px] font-medium text-ink-soft">
            <input type="checkbox" checked={autoPulse} onChange={(e) => setAutoPulse(e.target.checked)} className="h-4 w-4 accent-[var(--color-brand)]" />
            Keep simulating (every 8s)
          </label>
        }
      >
        <div className="flex items-center gap-3">
          <Button icon={PULSE.icon} loading={busy === PULSE.path} onClick={() => run(PULSE)}>Simulate activity</Button>
          {autoPulse && <Badge tone="success" dot>auto-simulating</Badge>}
        </div>
        <p className="mt-2 text-[12px] text-muted">{PULSE.desc}</p>
      </Card>

      {GROUPS.map((g) => (
        <Card key={g.title} title={g.title}>
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {g.items.map((a) => (
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
      ))}

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
