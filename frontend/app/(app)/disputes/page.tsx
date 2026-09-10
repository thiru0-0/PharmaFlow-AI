"use client";
import React from "react";
import { Scale, Paperclip, Gavel, ArrowLeftRight } from "lucide-react";
import { api, currentUser } from "@/lib/api";
import {
  Alert, Badge, Button, Card, EmptyState, Field, InlineError, Input, Mono, Modal,
  PageHeader, PromptModal, SkeletonRows, StatusBadge, Table, Td, Timeline, TimelineItem, Tr,
} from "@/lib/ui";
import { useLiveQuery } from "@/lib/realtime";

function priorityOf(d: any): { tone: "danger" | "warning" | "neutral"; label: string } {
  const ratio = d.tolerance_units ? d.difference / d.tolerance_units : d.difference;
  if (ratio >= 3) return { tone: "danger", label: "High" };
  if (ratio >= 1.5) return { tone: "warning", label: "Medium" };
  return { tone: "neutral", label: "Low" };
}

export default function DisputesPage() {
  const disputes = useLiveQuery<any[]>(() => api("/disputes"), [], { kinds: ["registry"] });
  const role = currentUser<any>()?.role;
  const [sel, setSel] = React.useState<any>(null);
  const [msg, setMsg] = React.useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [evidenceOpen, setEvidenceOpen] = React.useState(false);
  const [resolveOpen, setResolveOpen] = React.useState(false);

  async function open(idOrRow: any) {
    const id = typeof idOrRow === "string" ? idOrRow : idOrRow.id;
    setMsg(null);
    setSel(await api(`/disputes/${id}`));
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Disputes"
        description="Quantity-mismatch cases between a retailer's reported return and the distributor's confirmed pickup."
      />
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      <Card padded={false}>
        <div className="p-5">
          {disputes.loading ? <SkeletonRows /> : disputes.data?.length ? (
            <Table head={["Priority", "Batch", "Parties", "Reported", "Confirmed", "Δ", "Tolerance", "Status", ""]}>
              {disputes.data.map((d) => {
                const p = priorityOf(d);
                return (
                  <Tr key={d.id} onClick={() => open(d)}>
                    <Td><Badge tone={p.tone}>{p.label}</Badge></Td>
                    <Td className="text-ink"><Mono>{d.batch_number}</Mono></Td>
                    <Td className="text-[12.5px] text-muted">{d.retailer} ↔ {d.distributor}</Td>
                    <Td className="tabular-nums">{d.reported_qty}</Td>
                    <Td className="tabular-nums">{d.confirmed_qty}</Td>
                    <Td className="font-semibold tabular-nums text-ink">{d.difference}</Td>
                    <Td className="tabular-nums text-muted">±{d.tolerance_units}</Td>
                    <Td><StatusBadge value={d.status} /></Td>
                    <Td className="text-right"><Button size="sm" variant="ghost">View</Button></Td>
                  </Tr>
                );
              })}
            </Table>
          ) : (
            <EmptyState icon={<Scale size={20} />} title="No disputes" description="A pickup quantity outside tolerance opens a case here and blocks the batch." />
          )}
        </div>
      </Card>

      {sel && (
        <Card
          title={<span className="flex items-center gap-2">Dispute {sel.id.slice(0, 8)} · <Mono className="text-ink">{sel.batch_number}</Mono></span>}
          actions={<StatusBadge value={sel.status} />}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-line-soft p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Retailer reported</div>
              <div className="mt-1 text-[26px] font-semibold tabular-nums text-ink">{sel.reported_qty}</div>
              <div className="mt-1 text-[12px] text-muted">{sel.retailer}</div>
              <Mono className="mt-1 block truncate text-muted">{sel.retailer_photo}</Mono>
            </div>
            <div className="rounded-xl border border-line-soft p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Distributor confirmed</div>
              <div className="mt-1 text-[26px] font-semibold tabular-nums text-ink">{sel.confirmed_qty}</div>
              <div className="mt-1 text-[12px] text-muted">{sel.distributor}</div>
              <Mono className="mt-1 block truncate text-muted">{sel.distributor_photo}</Mono>
            </div>
          </div>

          <div className="mt-3 flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-[12.5px] text-ink-soft ring-1 ring-inset ring-line">
            <ArrowLeftRight size={14} className="text-muted" />
            Difference <b className="mx-1 text-ink">{sel.difference}</b> exceeds tolerance <b className="mx-1 text-ink">±{sel.tolerance_units}</b>
            — batch <StatusBadge value={sel.batch_state} /> and blocked from progressing while open.
          </div>

          <div className="mt-4">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Evidence</div>
            {sel.evidence?.length ? (
              <Timeline>
                {sel.evidence.map((e: any, i: number) => (
                  <TimelineItem key={i} title={e.by} time={String(e.at).slice(0, 16).replace("T", " ")} last={i === sel.evidence.length - 1}>
                    {e.note}
                  </TimelineItem>
                ))}
              </Timeline>
            ) : (
              <p className="text-[13px] text-muted">No evidence submitted yet.</p>
            )}
          </div>

          {sel.resolution_notes && (
            <Alert tone="success" title="Resolved" >
              Reconciled to <b>{sel.reconciled_qty}</b> — {sel.resolution_notes}
            </Alert>
          )}

          {sel.status === "OPEN" && (
            <div className="mt-4 flex flex-wrap gap-2">
              {["RETAILER", "DISTRIBUTOR", "ADMIN"].includes(role) && (
                <Button variant="secondary" icon={<Paperclip size={14} />} onClick={() => setEvidenceOpen(true)}>Submit evidence</Button>
              )}
              {role === "ADMIN"
                ? <Button icon={<Gavel size={14} />} onClick={() => setResolveOpen(true)}>Adjudicate & reconcile</Button>
                : <span className="self-center text-[12px] text-muted">Only a platform admin / supervisor can adjudicate.</span>}
            </div>
          )}
        </Card>
      )}

      <PromptModal
        open={evidenceOpen}
        onClose={() => setEvidenceOpen(false)}
        title="Submit evidence"
        label="Note (recount, photo description, …)"
        submitLabel="Submit"
        onSubmit={async (v) => {
          if (!v.trim()) throw new Error("A note is required");
          await api(`/disputes/${sel.id}/evidence`, { method: "POST", body: { note: v } });
          setEvidenceOpen(false); open(sel.id);
        }}
      />

      <ResolveModal
        open={resolveOpen}
        onClose={() => setResolveOpen(false)}
        dispute={sel}
        onDone={(text) => { setResolveOpen(false); setMsg({ tone: "success", text }); disputes.reload(); if (sel) open(sel.id); }}
      />
    </div>
  );
}

function ResolveModal({ open, onClose, dispute, onDone }: { open: boolean; onClose: () => void; dispute: any; onDone: (t: string) => void }) {
  const [qty, setQty] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<any>(null);
  React.useEffect(() => { if (open && dispute) { setQty(String(dispute.confirmed_qty)); setNotes(""); setErr(null); } }, [open, dispute]);

  async function submit() {
    setBusy(true); setErr(null);
    try {
      const r = await api<any>(`/disputes/${dispute.id}/resolve`, { method: "POST", body: { reconciled_qty: Number(qty), resolution_notes: notes || "adjudicated" } });
      onDone(`Dispute resolved — batch now ${r.batch_state?.replaceAll("_", " ")}, reconciled to ${r.reconciled_qty}.`);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Adjudicate & reconcile"
      description={dispute ? `${dispute.batch_number} · reported ${dispute.reported_qty} vs confirmed ${dispute.confirmed_qty}` : ""}
      footer={<>
        <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
        <Button size="sm" loading={busy} onClick={submit}>Resolve</Button>
      </>}
    >
      <div className="space-y-3">
        <Field label="Reconciled quantity"><Input type="number" value={qty} onChange={(e) => setQty(e.target.value)} /></Field>
        <Field label="Resolution note"><Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Recount agreed with both parties" /></Field>
        <InlineError e={err} />
      </div>
    </Modal>
  );
}
