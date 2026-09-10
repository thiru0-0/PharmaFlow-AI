"use client";
import React from "react";
import Link from "next/link";
import { Inbox, FileCheck2, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import {
  Alert, Badge, Button, Card, EmptyState, Mono, PageHeader, PromptModal,
  SkeletonRows, StatusBadge, Table, Td, Tr,
} from "@/lib/ui";
import { useLiveQuery } from "@/lib/realtime";

export default function ManufacturerPage() {
  const inbound = useLiveQuery<any[]>(() => api("/manufacturer/inbound"), [], { kinds: ["registry"] });
  const receipts = useLiveQuery<any[]>(() => api("/manufacturer/receipts"), [], { kinds: ["registry"] });
  const [msg, setMsg] = React.useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [receiptRow, setReceiptRow] = React.useState<any>(null);
  const [certBusy, setCertBusy] = React.useState<string | null>(null);

  const reloadAll = () => { inbound.reload(); receipts.reload(); };

  async function uploadCert(rc: any) {
    setCertBusy(rc.receipt_id); setMsg(null);
    try {
      const r = await api<any>("/manufacturer/certificates", {
        method: "POST",
        body: { batch_id: rc.batch_id, facility_name: "GreenCycle Biomedical Waste Facility (synthetic)", cert_url: "mock://uploads/cert.pdf", reason: "expired" },
      });
      setMsg({ tone: "success", text: `Certificate accepted — batch ${r.batch_state?.replaceAll("_", " ")}. Disposal record auto-populated.` });
      reloadAll();
    } catch (e: any) {
      setMsg({ tone: "danger", text: e.message });
    } finally { setCertBusy(null); }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Manufacturer Desk"
        description="Confirm receipt of returned batches and issue destruction certificates once received."
      />

      {msg && <Alert tone={msg.tone} title={msg.tone === "danger" ? "Certificate blocked" : "Done"}>{msg.text}</Alert>}

      <Card title="Inbound" description="Confirmed pickups for your batches, awaiting a receipt record." padded={false}>
        <div className="p-5">
          {inbound.loading ? <SkeletonRows /> : (
            <Table head={["Batch", "Drug", "Qty confirmed", "State", ""]} empty={!inbound.data?.length} emptyLabel="Nothing inbound">
              {(inbound.data || []).map((b) => (
                <Tr key={b.batch_id}>
                  <Td className="text-ink"><Mono>{b.batch_number}</Mono></Td>
                  <Td>{b.drug_name}</Td>
                  <Td className="tabular-nums">{b.quantity_confirmed}</Td>
                  <Td><StatusBadge value={b.batch_state} /></Td>
                  <Td className="text-right"><Button size="sm" icon={<Inbox size={14} />} onClick={() => setReceiptRow(b)}>Confirm receipt</Button></Td>
                </Tr>
              ))}
            </Table>
          )}
        </div>
      </Card>

      <Card
        title="Receipts & certificates"
        description="Certificate upload is blocked unless a confirmed receipt exists and the batch is RECEIVED_BY_MANUFACTURER."
        actions={<Button size="sm" variant="ghost" onClick={receipts.reload}>Refresh</Button>}
        padded={false}
      >
        <div className="p-5">
          {receipts.loading ? <SkeletonRows /> : receipts.data?.length ? (
            <Table head={["Batch", "Drug", "Qty", "Received", "State", ""]}>
              {receipts.data.map((rc) => (
                <Tr key={rc.receipt_id}>
                  <Td className="text-ink"><Link href={`/batch/${rc.batch_id}`} className="hover:text-brand"><Mono>{rc.batch_number}</Mono></Link></Td>
                  <Td>{rc.drug_name}</Td>
                  <Td className="tabular-nums">{rc.quantity}</Td>
                  <Td>{String(rc.received_at).slice(0, 10)}</Td>
                  <Td><StatusBadge value={rc.batch_state} /></Td>
                  <Td className="text-right">
                    {rc.certificate_id
                      ? <Badge tone="success"><ShieldCheck size={12} /> Certified</Badge>
                      : <Button size="sm" icon={<FileCheck2 size={14} />} loading={certBusy === rc.receipt_id} onClick={() => uploadCert(rc)}>Upload certificate</Button>}
                  </Td>
                </Tr>
              ))}
            </Table>
          ) : (
            <EmptyState icon={<FileCheck2 size={18} />} title="No receipts yet" description="Confirm an inbound pickup to start the destruction record." />
          )}
        </div>
      </Card>

      <PromptModal
        open={!!receiptRow}
        onClose={() => setReceiptRow(null)}
        title={`Confirm receipt · ${receiptRow?.batch_number ?? ""}`}
        label="Confirmed received quantity"
        type="number"
        defaultValue={String(receiptRow?.quantity_confirmed ?? "")}
        submitLabel="Confirm receipt"
        onSubmit={async (v) => {
          const r = await api<any>("/manufacturer/receipts", { method: "POST", body: { batch_id: receiptRow.batch_id, quantity: Number(v) } });
          setReceiptRow(null);
          setMsg({ tone: "success", text: `Receipt recorded — batch ${r.batch_state?.replaceAll("_", " ")}.` });
          reloadAll();
        }}
      />
    </div>
  );
}
