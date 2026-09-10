"use client";
import React from "react";
import Link from "next/link";
import { ShieldAlert, ShieldCheck, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, Card, EmptyState, Mono, PageHeader, SkeletonRows, StatusBadge, Table, Td, Tr } from "@/lib/ui";
import { useLiveQuery } from "@/lib/realtime";

export default function AlertsPage() {
  const alerts = useLiveQuery<any[]>(() => api("/alerts/reentry"), [], { kinds: ["reentry", "registry"] });
  const open = (alerts.data || []).filter((a) => a.status === "OPEN").length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Re-entry Alerts"
        description="Blocked point-of-sale attempts on batches already in the return pipeline."
        actions={
          <Badge tone={open ? "danger" : "success"} dot>
            {open ? `${open} open` : "All clear"}
          </Badge>
        }
      />

      <Card padded={false}>
        <div className="p-5">
          {alerts.loading ? <SkeletonRows /> : alerts.data?.length ? (
            <Table head={["Severity", "Batch", "Attempted by", "Location", "Qty", "Notified", "Latency", "Status", ""]}>
              {alerts.data.map((a) => (
                <Tr key={a.id}>
                  <Td><Badge tone="danger"><ShieldAlert size={12} /> {a.severity}</Badge></Td>
                  <Td className="text-ink"><Mono>{a.batch_number}</Mono></Td>
                  <Td>{a.attempted_retailer}</Td>
                  <Td className="text-muted">{a.attempted_location}</Td>
                  <Td className="tabular-nums">{a.attempted_quantity}</Td>
                  <Td className="text-[12px] text-muted">
                    ctrl {a.notified_controller ? "✓" : "✗"} · mfr {a.notified_manufacturer ? "✓" : "✗"}
                  </Td>
                  <Td className="tabular-nums">{a.notification_latency_ms} ms</Td>
                  <Td><StatusBadge value={a.status} /></Td>
                  <Td className="text-right">
                    <Link href={`/alerts/${a.id}`}><Button size="sm" variant="secondary">Open <ArrowRight size={13} /></Button></Link>
                  </Td>
                </Tr>
              ))}
            </Table>
          ) : (
            <EmptyState icon={<ShieldCheck size={20} />} title="No re-entry alerts" description="If a returned batch is scanned for sale anywhere in the network, it will be blocked and listed here." />
          )}
        </div>
      </Card>
    </div>
  );
}
