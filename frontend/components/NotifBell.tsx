"use client";
import React from "react";
import Link from "next/link";
import { Bell, CheckCheck } from "lucide-react";
import { useNotifications } from "@/lib/realtime";
import { cn } from "@/lib/ui";

const LABELS: Record<string, string> = {
  EXPIRY_60_DAY: "Expiry approaching",
  RETURN_AUTO_CREATED: "Return auto-created",
  RETURN_INITIATED: "Return initiated",
  DISPUTE_RAISED: "Dispute raised",
  DISPUTE_RESOLVED: "Dispute resolved",
  CERTIFICATE_ISSUED: "Destruction certificate issued",
  SLA_BREACH: "Compliance deadline breached",
  REENTRY_FRAUD: "Re-entry blocked at point of sale",
};

function toneOf(type: string) {
  if (type === "REENTRY_FRAUD" || type === "SLA_BREACH" || type === "DISPUTE_RAISED") return "text-danger";
  if (type === "EXPIRY_60_DAY" || type === "RETURN_AUTO_CREATED") return "text-warn";
  return "text-brand";
}

function ago(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function NotifBell() {
  const { items, unread, markAll, markOne } = useNotifications();
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative grid h-9 w-9 place-items-center rounded-lg text-ink-soft hover:bg-line-soft"
        aria-label="Notifications"
      >
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="pf-anim-in absolute right-0 z-50 mt-2 w-[340px] rounded-xl bg-surface shadow-xl ring-1 ring-line">
          <div className="flex items-center justify-between border-b border-line-soft px-4 py-2.5">
            <span className="text-[13px] font-semibold text-ink">Notifications</span>
            {unread > 0 && (
              <button onClick={markAll} className="inline-flex items-center gap-1 text-[12px] font-medium text-brand hover:underline">
                <CheckCheck size={13} /> Mark all read
              </button>
            )}
          </div>
          <div className="max-h-[380px] overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13px] text-muted">You’re all caught up.</p>
            ) : (
              items.map((n) => {
                const inner = (
                  <div
                    className={cn(
                      "flex gap-3 border-b border-line-soft px-4 py-3 last:border-0",
                      !n.read && "bg-brand-soft/40"
                    )}
                  >
                    <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", n.read ? "bg-line" : "bg-brand")} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className={cn("text-[12.5px] font-semibold", toneOf(n.type))}>
                          {LABELS[n.type] || n.type.replaceAll("_", " ")}
                        </span>
                        <span className="shrink-0 text-[11px] text-muted">{ago(n.created_at)}</span>
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-[12px] text-ink-soft">
                        {n.payload?.batch_number ? `${n.payload.batch_number} · ` : ""}
                        {n.payload?.attempted_retailer
                          ? `attempt at ${n.payload.attempted_location || n.payload.attempted_retailer}`
                          : n.payload?.action_required || n.payload?.reason_for_disposal || n.payload?.days_to_expiry != null
                          ? n.payload.action_required || `${n.payload.days_to_expiry} days to expiry`
                          : n.delivery_status === "simulated" ? "email/SMS simulated" : "in-app"}
                      </p>
                    </div>
                  </div>
                );
                return n.batch_id ? (
                  <Link key={n.id} href={`/batch/${n.batch_id}`} onClick={() => { markOne(n.id); setOpen(false); }}>
                    {inner}
                  </Link>
                ) : (
                  <button key={n.id} className="block w-full text-left" onClick={() => markOne(n.id)}>
                    {inner}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
