"use client";
import React from "react";
import { api } from "@/lib/api";
import { Badge, Card } from "@/lib/ui";

export default function RegistryExplorer() {
  const [batchNo, setBatchNo] = React.useState("AZ-2025-G");
  const [mlid, setMlid] = React.useState("");
  const [history, setHistory] = React.useState<any>(null);
  const [verify, setVerify] = React.useState<any>(null);
  const [err, setErr] = React.useState<string | null>(null);

  async function load() {
    setErr(null); setHistory(null); setVerify(null);
    const qs = mlid ? `?manufacturer_license_id=${mlid}` : "";
    try {
      const [h, v] = await Promise.all([
        api(`/registry/batches/${batchNo}/history${qs}`),
        api(`/registry/verify/${batchNo}${qs}`),
      ]);
      setHistory(h); setVerify(v);
    } catch (e) { setErr((e as any).message); }
  }

  React.useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <h1 style={{ margin: 0 }}>Registry Explorer</h1>
      <Card title="Search a batch chain">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
          <div><div className="label">Batch number</div><input className="input" value={batchNo} onChange={(e) => setBatchNo(e.target.value)} /></div>
          <div><div className="label">Manufacturer license (optional)</div><input className="input" value={mlid} onChange={(e) => setMlid(e.target.value)} placeholder="disambiguates reused batch numbers" style={{ width: 320 }} /></div>
          <button className="btn" onClick={load}>Load + verify chain</button>
        </div>
        {err && <p style={{ color: "var(--danger)", fontWeight: 600 }}>{err}</p>}
      </Card>

      {verify && (
        <Card title="Chain verification">
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <span className={`badge ${verify.valid ? "green" : "red"}`}>{verify.valid ? "VALID" : "INVALID — INTEGRITY BREACH"}</span>
            <span>hash chain: <b>{verify.hash_chain_valid ? "ok" : "broken"}</b></span>
            <span>signatures: <b>{verify.signatures_valid ? "ok" : "invalid"}</b></span>
            <span>ordering: <b>{verify.ordering_valid ? "ok" : "bad"}</b></span>
            <span>{verify.event_count} events</span>
          </div>
          {!!verify.problems?.length && (
            <ul className="mono" style={{ color: "var(--danger)" }}>
              {verify.problems.map((p: any, i: number) => <li key={i}>seq {p.seq}: {p.issue}</li>)}
            </ul>
          )}
        </Card>
      )}

      {history && (
        <Card title={`${history.batch_number} — ${history.drug_name} · ${history.current_state}`}>
          <table>
            <thead><tr><th>#</th><th>Event</th><th>Actor</th><th>prev_hash</th><th>hash</th><th>sig</th><th>Time</th></tr></thead>
            <tbody>
              {history.events.map((e: any) => (
                <tr key={e.seq}>
                  <td>{e.seq}</td>
                  <td><span className="badge blue">{e.event_type}</span></td>
                  <td>{e.actor}</td>
                  <td className="mono">{e.prev_hash.slice(0, 10)}…</td>
                  <td className="mono">{e.hash.slice(0, 10)}…</td>
                  <td className="mono">{e.signature}</td>
                  <td>{String(e.created_at).slice(0, 19).replace("T", " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
