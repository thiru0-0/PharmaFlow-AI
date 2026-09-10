"use client";
import React from "react";

export function Badge({ state }: { state: string }) {
  const map: Record<string, string> = {
    ACTIVE: "green",
    RETURN_INITIATED: "amber",
    PICKUP_SCHEDULED: "blue",
    DISPUTED: "red",
    PICKUP_CONFIRMED: "blue",
    RECEIVED_BY_MANUFACTURER: "blue",
    DESTROYED_CERTIFIED: "gray",
    OPEN: "red",
    RESOLVED: "green",
    CRITICAL: "red",
    SOLD: "green",
  };
  return <span className={`badge ${map[state] || "gray"}`}>{state?.replaceAll("_", " ")}</span>;
}

export function Card({ title, right, children }: { title?: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      {title && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 16px", borderBottom: "1px solid var(--line)" }}>
          <h3 style={{ margin: 0, fontSize: 15 }}>{title}</h3>
          {right}
        </div>
      )}
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  );
}

export function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="label">{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, color: tone === "danger" ? "var(--danger)" : "var(--ink)" }}>{value}</div>
    </div>
  );
}

export function ErrorText({ e }: { e: any }) {
  if (!e) return null;
  const msg = typeof e === "string" ? e : e?.message || JSON.stringify(e);
  return <p style={{ color: "var(--danger)", fontSize: 13, fontWeight: 600, margin: "8px 0" }}>{msg}</p>;
}

export function useAsync<T>(fn: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);
  const run = React.useCallback(() => {
    setLoading(true);
    fn()
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  React.useEffect(() => { run(); }, [run]);
  return { data, error, loading, reload: run };
}
