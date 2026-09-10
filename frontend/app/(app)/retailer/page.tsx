"use client";
import React from "react";
import Link from "next/link";
import { Boxes, PackageX, Bell, ShieldAlert, ArrowRight } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import {
  Alert, Badge, Button, Card, DataGrid, EmptyState, Field, InlineError, Input,
  Mono, PageHeader, PromptModal, SkeletonRows, StatusBadge, Table, Td, Tr, useAsync,
} from "@/lib/ui";
import Scanner from "@/components/Scanner";

export default function RetailerPage() {
  const batches = useAsync<any[]>(() => api("/retailer/batches"), []);
  const returns = useAsync<any[]>(() => api("/retailer/returns"), []);
  const notifs = useAsync<any[]>(() => api("/dashboard/notifications"), []);

  const [qr, setQr] = React.useState("");
  const [qty, setQty] = React.useState(1);
  const [sale, setSale] = React.useState<any>(null);
  const [blocked, setBlocked] = React.useState<any>(null);
  const [saleErr, setSaleErr] = React.useState<any>(null);
  const [selling, setSelling] = React.useState(false);
  const [modal, setModal] = React.useState<null | { kind: "initiate" | "confirm"; row: any }>(null);

  const reloadAll = () => { batches.reload(); returns.reload(); notifs.reload(); };

  async function sell() {
    setSaleErr(null); setSale(null); setBlocked(null); setSelling(true);
    try {
      const res = await api<any>("/retailer/pos/sale", { method: "POST", body: { qr_payload: qr, quantity: Number(qty) } });
      setSale(res); reloadAll();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.detail?.status === "BLOCKED_REENTRY") { setBlocked(e.detail); reloadAll(); }
      else setSaleErr(e);
    } finally { setSelling(false); }
  }

  const pending = (returns.data || []).filter((r) => r.status === "AUTO_CREATED").length;
  const nearExpiry = (batches.data || []).filter((b) => b.days_to_expiry <= 60 && b.days_to_expiry >= 0 && b.state === "ACTIVE").length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Retailer POS & Inventory"
        description="Scan to sell, monitor expiry, and hand expired stock into the return pipeline."
      />

      {blocked && (
        <Alert
          tone="danger"
          icon={<ShieldAlert size={18} />}
          title={`Sale of ${blocked.batch_number} blocked at the point of sale`}
          actions={
            <Link href={`/alerts/${blocked.alert_id}`}>
              <Button size="sm" variant="secondary">Open re-entry alert <ArrowRight size={14} /></Button>
            </Link>
          }
        >
          <p>{blocked.message}</p>
          <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
            {[
              ["Batch state", blocked.batch_state?.replaceAll("_", " ")],
              ["Attempted at", blocked.attempted_location],
              ["Drug controller", blocked.notified?.state_drug_controller ? "Notified" : "—"],
              ["Manufacturer", blocked.notified?.manufacturer ? "Notified" : "—"],
              ["Detection latency", `${blocked.latency_ms} ms`],
            ].map(([k, v]) => (
              <div key={k as string}>
                <div className="text-[10.5px] font-semibold uppercase tracking-wide text-danger/70">{k}</div>
                <div className="text-[13px] font-medium text-ink">{v}</div>
              </div>
            ))}
          </div>
        </Alert>
      )}

      <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
        <Card title="Scan to sell" description="Point-of-sale checkout with a real-time re-entry check.">
          <Scanner onScan={setQr} />
          <div className="mt-4 space-y-3">
            <Field label="Scanned QR / DataMatrix payload">
              <Input value={qr} onChange={(e) => setQr(e.target.value)} placeholder="(01)08901234500…(10)AZ-2025-…" />
            </Field>
            {!!batches.data?.length && (
              <div className="flex flex-wrap gap-1.5">
                {batches.data.slice(0, 6).map((b) => (
                  <button
                    key={b.batch_id}
                    onClick={() => setQr(b.qr_payload)}
                    className="rounded-md bg-surface-2 px-2 py-1 text-[11.5px] font-medium text-ink-soft ring-1 ring-inset ring-line hover:bg-line-soft"
                  >
                    demo scan · {b.batch_number}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-end gap-3">
              <Field label="Quantity" className="w-28">
                <Input type="number" min={1} value={qty} onChange={(e) => setQty(Number(e.target.value))} />
              </Field>
              <Button onClick={sell} loading={selling} disabled={!qr} className="mb-[1px]">Record sale</Button>
            </div>
            <InlineError e={saleErr} />
            {sale && (
              <Alert tone="success" title={`Sold ${sale.quantity} × ${sale.batch_number}`}>
                {sale.remaining_on_hand} units remaining on hand · transaction {sale.pos_transaction_id.slice(0, 8)}
              </Alert>
            )}
          </div>
        </Card>

        <Card
          title="Notifications"
          actions={<Button size="sm" variant="ghost" onClick={notifs.reload}>Refresh</Button>}
          bodyClassName="max-h-[420px] overflow-y-auto"
        >
          {notifs.loading ? (
            <SkeletonRows rows={4} cols={1} />
          ) : notifs.data?.length ? (
            <ul className="space-y-2.5">
              {notifs.data.map((n) => (
                <li key={n.id} className="rounded-lg border border-line-soft p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12.5px] font-semibold text-ink">{n.type.replaceAll("_", " ")}</span>
                    <Badge tone={n.delivery_status === "sent" ? "success" : "neutral"}>{n.channel} · {n.delivery_status}</Badge>
                  </div>
                  <Mono className="mt-1 block truncate">{JSON.stringify(n.payload)}</Mono>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={<Bell size={18} />} title="No notifications yet" description="Expiry, return and fraud alerts will appear here." />
          )}
        </Card>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { label: "Batches on hand", value: batches.data?.length ?? "—", icon: <Boxes size={15} /> },
          { label: "Near expiry (≤60d)", value: nearExpiry, icon: <PackageX size={15} />, tone: nearExpiry ? "warning" : "neutral" },
          { label: "Returns to confirm", value: pending, icon: <ArrowRight size={15} />, tone: pending ? "warning" : "neutral" },
        ].map((s: any) => (
          <div key={s.label} className="rounded-[var(--radius-card)] bg-surface p-4 ring-1 ring-line">
            <div className="flex items-center justify-between">
              <span className="text-[11.5px] font-semibold uppercase tracking-wide text-muted">{s.label}</span>
              <span className="text-muted">{s.icon}</span>
            </div>
            <div className="mt-1.5 text-[24px] font-semibold tabular-nums text-ink">{s.value}</div>
          </div>
        ))}
      </div>

      <Card title="Inventory" actions={<Button size="sm" variant="ghost" onClick={batches.reload}>Refresh</Button>} padded={false}>
        <div className="p-5">
          {batches.loading ? (
            <SkeletonRows />
          ) : (
            <Table head={["Batch", "Drug", "Expiry", "Status", "On hand", "State", ""]} empty={!batches.data?.length} emptyLabel="No inventory">
              {(batches.data || []).map((b) => (
                <Tr key={b.batch_id}>
                  <Td className="text-ink"><Link href={`/batch/${b.batch_id}`} className="font-medium hover:text-brand"><Mono>{b.batch_number}</Mono></Link></Td>
                  <Td>{b.drug_name}</Td>
                  <Td>{String(b.expiry_date).slice(0, 10)}</Td>
                  <Td>
                    {b.days_to_expiry < 0 ? <Badge tone="danger">Expired</Badge>
                      : b.days_to_expiry <= 60 && b.state === "ACTIVE" ? <Badge tone="warning">{b.days_to_expiry}d left</Badge>
                      : <span className="text-muted">{b.days_to_expiry}d</span>}
                  </Td>
                  <Td className="tabular-nums text-ink">{b.quantity_on_hand}</Td>
                  <Td>
                    <div className="flex items-center gap-1.5">
                      <StatusBadge value={b.state} />
                      {b.reentry_flagged && <Badge tone="danger">Re-entry</Badge>}
                    </div>
                  </Td>
                  <Td className="text-right">
                    {b.state === "ACTIVE" && (
                      <Button size="sm" variant="secondary" onClick={() => setModal({ kind: "initiate", row: b })}>Initiate return</Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
          )}
        </div>
      </Card>

      <Card title="My returns" actions={<Button size="sm" variant="ghost" onClick={returns.reload}>Refresh</Button>} padded={false}>
        <div className="p-5">
          <Table head={["Batch", "Status", "Qty reported", "Condition", "Created", ""]} empty={!returns.data?.length} emptyLabel="No returns yet">
            {(returns.data || []).map((r) => (
              <Tr key={r.id}>
                <Td className="text-ink"><Mono>{r.batch_number}</Mono></Td>
                <Td><StatusBadge value={r.status} /></Td>
                <Td className="tabular-nums">{r.quantity_reported ?? "—"}</Td>
                <Td>{r.condition ?? "—"}</Td>
                <Td>{String(r.created_at).slice(0, 16).replace("T", " ")}</Td>
                <Td className="text-right">
                  {r.status === "AUTO_CREATED" && (
                    <Button size="sm" onClick={() => setModal({ kind: "confirm", row: r })}>Confirm quantity</Button>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
        </div>
      </Card>

      <PromptModal
        open={modal?.kind === "initiate"}
        onClose={() => setModal(null)}
        title={`Initiate return · ${modal?.row?.batch_number ?? ""}`}
        label="Counted quantity to return"
        hint="Creates a return request and flags the batch in the shared registry."
        type="number"
        defaultValue={String(modal?.row?.quantity_on_hand ?? "")}
        submitLabel="Initiate return"
        onSubmit={async (v) => {
          await api(`/retailer/batches/${modal!.row.batch_id}/initiate-return`, { method: "POST", body: { quantity_reported: Number(v), condition: "sealed" } });
          setModal(null); reloadAll();
        }}
      />
      <PromptModal
        open={modal?.kind === "confirm"}
        onClose={() => setModal(null)}
        title={`Confirm return · ${modal?.row?.batch_number ?? ""}`}
        label="Counted quantity"
        hint="Attach the condition photo and confirm the counted quantity before pickup."
        type="number"
        defaultValue="0"
        submitLabel="Confirm return"
        onSubmit={async (v) => {
          await api(`/retailer/returns/${modal!.row.id}/confirm`, { method: "POST", body: { quantity_reported: Number(v), condition: "sealed" } });
          setModal(null); reloadAll();
        }}
      />
    </div>
  );
}
