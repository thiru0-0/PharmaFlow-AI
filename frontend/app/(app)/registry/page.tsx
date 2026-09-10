"use client";
import React from "react";
import Link from "next/link";
import { Search, ShieldCheck, ShieldX, Fingerprint } from "lucide-react";
import { api } from "@/lib/api";
import {
  Alert, Badge, Button, Card, DataGrid, EmptyState, Field, Input, Mono, PageHeader,
  SkeletonRows, StatusBadge, Table, Td, Timeline, TimelineItem, Tr, toneFor,
} from "@/lib/ui";
import { onLive, useLiveQuery } from "@/lib/realtime";

export default function RegistryExplorer() {
  const list = useLiveQuery<any[]>(() => api("/dashboard/batches"), [], { kinds: ["registry"] });
  const [q, setQ] = React.useState("");
  const [sel, setSel] = React.useState<{ batch_number: string; mlid: string } | null>(null);
  const [history, setHistory] = React.useState<any>(null);
  const [verify, setVerify] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const rows = (list.data || []).filter((b) =>
    !q || b.batch_number.toLowerCase().includes(q.toLowerCase()) || b.drug_name?.toLowerCase().includes(q.toLowerCase())
  );

  async function load(batch_number: string, mlid: string) {
    setSel({ batch_number, mlid }); setLoading(true); setErr(null); setHistory(null); setVerify(null);
    try {
      const qs = `?manufacturer_license_id=${encodeURIComponent(mlid)}`;
      const [h, v] = await Promise.all([
        api(`/registry/batches/${batch_number}/history${qs}`),
        api(`/registry/verify/${batch_number}${qs}`),
      ]);
      setHistory(h); setVerify(v);
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  }

  React.useEffect(() => {
    if (!sel && list.data?.length) { const b = list.data[0]; load(b.batch_number, b.manufacturer_license_id); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.data]);

  // live: if an event lands for the batch currently open, refresh its chain
  const selRef = React.useRef(sel);
  selRef.current = sel;
  React.useEffect(
    () =>
      onLive((e) => {
        const s = selRef.current;
        if (e.kind === "registry" && s && e.batch_number === s.batch_number && e.manufacturer_license_id === s.mlid) {
          load(s.batch_number, s.mlid);
        }
      }),
    []
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Registry Explorer"
        description="Search any batch, verify its hash chain and signatures, and walk the full chain of custody."
      />

      <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
        <Card title="Batches" padded={false} className="lg:sticky lg:top-20 lg:self-start">
          <div className="border-b border-line-soft p-3">
            <div className="relative">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search batch or drug" className="pl-9" />
            </div>
          </div>
          <div className="max-h-[520px] overflow-y-auto p-2">
            {list.loading ? (
              <div className="p-3"><SkeletonRows rows={5} cols={1} /></div>
            ) : rows.length ? rows.map((b) => {
              const active = sel?.batch_number === b.batch_number && sel?.mlid === b.manufacturer_license_id;
              return (
                <button
                  key={b.batch_id}
                  onClick={() => load(b.batch_number, b.manufacturer_license_id)}
                  className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${active ? "bg-brand-soft ring-1 ring-inset ring-brand-ring" : "hover:bg-surface-2"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <Mono className={active ? "text-brand" : "text-ink"}>{b.batch_number}</Mono>
                    <StatusBadge value={b.state} />
                  </div>
                  <div className="mt-0.5 truncate text-[11.5px] text-muted">{b.drug_name} · {b.manufacturer_license_id.slice(0, 8)}</div>
                </button>
              );
            }) : <div className="p-4"><EmptyState title="No matches" /></div>}
          </div>
        </Card>

        <div className="space-y-5">
          {err && <Alert tone="danger">{err}</Alert>}
          {loading && <Card><SkeletonRows rows={6} /></Card>}

          {history && verify && !loading && (
            <>
              <Card
                title={history.batch_number}
                description={`${history.drug_name} · ${history.current_state?.replaceAll("_", " ")}`}
                actions={<StatusBadge value={history.current_state} />}
              >
                <DataGrid
                  items={[
                    { label: "Manufacturer license", value: <Mono>{history.manufacturer_license_id}</Mono> },
                    { label: "Flagged at", value: history.flagged_at ? String(history.flagged_at).slice(0, 19).replace("T", " ") : "—" },
                    { label: "Overlay flags", value: (
                      <span className="flex gap-1.5">
                        {history.non_compliant && <Badge tone="danger">Non-compliant</Badge>}
                        {history.reentry_flagged && <Badge tone="danger">Re-entry</Badge>}
                        {!history.non_compliant && !history.reentry_flagged && "None"}
                      </span>
                    ) },
                    { label: "Events", value: history.events.length },
                  ]}
                />
              </Card>

              <Card title="Chain verification">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge tone={verify.valid ? "success" : "danger"} dot>
                    {verify.valid ? "Chain valid" : "Integrity breach"}
                  </Badge>
                  {[
                    ["Hash chain", verify.hash_chain_valid],
                    ["Signatures", verify.signatures_valid],
                    ["Ordering", verify.ordering_valid],
                  ].map(([k, ok]) => (
                    <span key={k as string} className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-soft">
                      {ok ? <ShieldCheck size={14} className="text-ok" /> : <ShieldX size={14} className="text-danger" />}
                      {k}
                    </span>
                  ))}
                  <span className="text-[12.5px] text-muted">{verify.event_count} events</span>
                </div>
                {!!verify.problems?.length && (
                  <ul className="mt-3 space-y-1">
                    {verify.problems.map((p: any, i: number) => (
                      <li key={i} className="text-[12.5px] font-medium text-danger">seq {p.seq}: {p.issue}</li>
                    ))}
                  </ul>
                )}
              </Card>

              <Card title="Chain of custody">
                <Timeline>
                  {history.events.map((e: any, i: number) => (
                    <TimelineItem
                      key={e.seq}
                      tone={toneFor(e.event_type)}
                      title={e.event_type.replaceAll("_", " ")}
                      actor={e.actor}
                      time={String(e.created_at).slice(0, 19).replace("T", " ")}
                      last={i === history.events.length - 1}
                    >
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                        <span className="inline-flex items-center gap-1"><Fingerprint size={12} className="text-muted" /><Mono>{e.hash.slice(0, 16)}…</Mono></span>
                        <Mono className="text-muted">prev {e.prev_hash.slice(0, 12)}…</Mono>
                      </div>
                    </TimelineItem>
                  ))}
                </Timeline>
              </Card>

              <Card title="Events" padded={false}>
                <div className="p-5">
                  <Table head={["#", "Event", "Actor", "Hash", "Signature", "Time"]}>
                    {history.events.map((e: any) => (
                      <Tr key={e.seq}>
                        <Td className="tabular-nums text-muted">{e.seq}</Td>
                        <Td><Badge tone={toneFor(e.event_type)}>{e.event_type}</Badge></Td>
                        <Td>{e.actor}</Td>
                        <Td><Mono>{e.hash.slice(0, 14)}…</Mono></Td>
                        <Td><Mono>{e.signature}</Mono></Td>
                        <Td className="text-muted">{String(e.created_at).slice(0, 19).replace("T", " ")}</Td>
                      </Tr>
                    ))}
                  </Table>
                </div>
              </Card>

              <div>
                <Link href={history.batch_number ? `/batch/${list.data?.find((b) => b.batch_number === sel?.batch_number && b.manufacturer_license_id === sel?.mlid)?.batch_id ?? ""}` : "#"}
                  className="text-[13px] font-semibold text-brand hover:underline">
                  Open full batch detail →
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
