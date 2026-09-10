"use client";
import React from "react";
import Link from "next/link";
import { Route, MapPin, PackageCheck } from "lucide-react";
import { api } from "@/lib/api";
import {
  Alert, Badge, Button, Card, EmptyState, InlineError, Mono, PageHeader,
  PromptModal, SkeletonRows, StatusBadge, Table, Td, Tr,
} from "@/lib/ui";
import { useLiveQuery } from "@/lib/realtime";

export default function DistributorPage() {
  const pending = useLiveQuery<any[]>(() => api("/distributor/returns/pending"), [], { kinds: ["registry"] });
  const pickups = useLiveQuery<any[]>(() => api("/distributor/pickups"), [], { kinds: ["registry"] });
  const routes = useLiveQuery<any[]>(() => api("/distributor/routes"), [], { kinds: ["registry"] });
  const [msg, setMsg] = React.useState<{ tone: "success" | "danger" | "info"; text: string } | null>(null);
  const [optimizing, setOptimizing] = React.useState(false);
  const [confirmRow, setConfirmRow] = React.useState<any>(null);

  const reloadAll = () => { pending.reload(); pickups.reload(); routes.reload(); };

  async function optimize() {
    setOptimizing(true); setMsg(null);
    try {
      const r = await api<any>("/distributor/routes/optimize", { method: "POST", body: { vehicle_capacity: 500 } });
      setMsg({
        tone: "success",
        text: `Route planned · ${r.stops.length} stops · ${r.total_distance_km} km · ₹${r.total_cost} · ${r.ortools_used ? "OR-Tools CVRP" : "nearest-neighbour fallback"}`,
      });
      reloadAll();
    } catch (e: any) { setMsg({ tone: "danger", text: e.message }); }
    finally { setOptimizing(false); }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Distributor Operations"
        description="Pending returns from mapped retailers, optimized pickup routing, and pickup confirmation."
        actions={<Button icon={<Route size={15} />} loading={optimizing} onClick={optimize}>Optimize pickup route</Button>}
      />

      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      <Card title="Pending returns" description="Mapped retailers with returns awaiting pickup." padded={false}>
        <div className="p-5">
          {pending.loading ? <SkeletonRows /> : (
            <Table head={["Batch", "Retailer", "Location", "Qty", "SLA left", "Urgency", "State"]} empty={!pending.data?.length} emptyLabel="No pending returns">
              {(pending.data || []).map((p) => (
                <Tr key={p.return_id}>
                  <Td className="text-ink"><Mono>{p.batch_number}</Mono></Td>
                  <Td>{p.retailer_name}</Td>
                  <Td className="text-muted"><span className="inline-flex items-center gap-1"><MapPin size={13} />{p.retailer_location}</span></Td>
                  <Td>{p.quantity_reported ?? <Badge tone="warning">awaiting count</Badge>}</Td>
                  <Td className="tabular-nums">{p.sla_days_left}d</Td>
                  <Td>
                    <span className="inline-flex items-center gap-2">
                      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-line-soft">
                        <span className="block h-full rounded-full bg-warn" style={{ width: `${Math.round(p.urgency * 100)}%` }} />
                      </span>
                      <span className="tabular-nums text-muted">{p.urgency}</span>
                    </span>
                  </Td>
                  <Td><StatusBadge value={p.batch_state} /></Td>
                </Tr>
              ))}
            </Table>
          )}
        </div>
      </Card>

      <Card title="Optimized routes" description="Urgency-weighted capacitated vehicle routing.">
        {routes.loading ? <SkeletonRows rows={2} /> : routes.data?.length ? (
          <div className="space-y-4">
            {routes.data.map((r) => (
              <div key={r.id} className="rounded-xl border border-line-soft p-4">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12.5px]">
                  <Badge tone={r.ortools_used ? "success" : "warning"}>{r.ortools_used ? "OR-Tools CVRP" : "Nearest-neighbour fallback"}</Badge>
                  <span className="font-semibold text-ink">{r.total_distance_km} km</span>
                  <span className="text-muted">{r.total_duration_min} min</span>
                  <span className="text-muted">₹{r.total_cost}</span>
                  <span className="text-muted">capacity {r.capacity_used}/{r.vehicle_capacity}</span>
                  <span className="text-muted">urgency {r.urgency_score}</span>
                </div>
                <ol className="mt-3 space-y-1.5">
                  {r.stops.map((s: any) => (
                    <li key={s.seq} className="flex items-center gap-3 text-[12.5px]">
                      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand-soft text-[11px] font-bold text-brand">{s.seq}</span>
                      <span className="font-medium text-ink">{s.name}</span>
                      <span className="text-muted">· qty {s.quantity} · urgency {s.urgency} · leg {s.leg_km} km</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={<Route size={18} />} title="No routes yet" description="Run “Optimize pickup route” to batch pending returns into an efficient trip." />
        )}
      </Card>

      <Card title="Pickups" actions={<Button size="sm" variant="ghost" onClick={pickups.reload}>Refresh</Button>} padded={false}>
        <div className="p-5">
          <Table head={["Batch", "Batch state", "Reported", "Confirmed", "Pickup", ""]} empty={!pickups.data?.length} emptyLabel="No pickups">
            {(pickups.data || []).map((p) => (
              <Tr key={p.pickup_id}>
                <Td className="text-ink"><Link href={`/batch/${p.batch_id}`} className="hover:text-brand"><Mono>{p.batch_number}</Mono></Link></Td>
                <Td><StatusBadge value={p.batch_state} /></Td>
                <Td className="tabular-nums">{p.quantity_reported ?? "—"}</Td>
                <Td className="tabular-nums">{p.quantity_confirmed ?? "—"}</Td>
                <Td><StatusBadge value={p.status} /></Td>
                <Td className="text-right">
                  {p.status === "SCHEDULED" && (
                    <Button size="sm" icon={<PackageCheck size={14} />} onClick={() => setConfirmRow(p)}>Confirm pickup</Button>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
        </div>
      </Card>

      <PromptModal
        open={!!confirmRow}
        onClose={() => setConfirmRow(null)}
        title={`Confirm pickup · ${confirmRow?.batch_number ?? ""}`}
        label="Weight-verified confirmed quantity"
        hint={confirmRow ? `Retailer reported ${confirmRow.quantity_reported ?? "—"} units. A mismatch beyond tolerance opens a dispute.` : ""}
        type="number"
        defaultValue={String(confirmRow?.quantity_reported ?? "")}
        submitLabel="Confirm pickup"
        onSubmit={async (v) => {
          const r = await api<any>(`/distributor/pickups/${confirmRow.pickup_id}/confirm`, { method: "POST", body: { quantity_confirmed: Number(v) } });
          setConfirmRow(null);
          setMsg(r.status === "DISPUTED"
            ? { tone: "danger", text: `Dispute opened — reported ${r.reported_qty} vs confirmed ${r.confirmed_qty} (tolerance ±${r.tolerance_units}). Batch blocked.` }
            : { tone: "success", text: `Pickup confirmed — batch now ${r.batch_state?.replaceAll("_", " ")}.` });
          reloadAll();
        }}
      />
    </div>
  );
}
