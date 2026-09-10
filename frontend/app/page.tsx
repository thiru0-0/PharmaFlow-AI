"use client";
import React from "react";
import { useRouter } from "next/navigation";
import { api, setSession, clearSession } from "@/lib/api";
import { ErrorText } from "@/lib/ui";

const HOME: Record<string, string> = {
  RETAILER: "/retailer",
  DISTRIBUTOR: "/distributor",
  MANUFACTURER: "/manufacturer",
  STATE_DRUG_CONTROLLER: "/dashboard",
  ADMIN: "/dashboard",
};

const QUICK = [
  ["Retailer A — CityCare", "retailer.a@pharmaflow.demo"],
  ["Retailer B — MedPlus", "retailer.b@pharmaflow.demo"],
  ["Distributor — Meridian", "distributor@pharmaflow.demo"],
  ["Manufacturer — Nucleus", "manufacturer@pharmaflow.demo"],
  ["State Drug Controller", "regulator@pharmaflow.demo"],
  ["Platform Admin", "admin@pharmaflow.demo"],
];

export default function Login() {
  const r = useRouter();
  const [email, setEmail] = React.useState("admin@pharmaflow.demo");
  const [password, setPassword] = React.useState("demo1234");
  const [error, setError] = React.useState<any>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => { clearSession(); }, []);

  async function doLogin(e?: string) {
    setBusy(true); setError(null);
    try {
      const res = await api<any>("/auth/login", { method: "POST", auth: false, body: { email: e || email, password: "demo1234" } });
      setSession(res.access_token, res);
      r.push(HOME[res.role] || "/dashboard");
    } catch (err) { setError(err); } finally { setBusy(false); }
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div style={{ width: 440, maxWidth: "100%" }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontWeight: 800, fontSize: 24 }}>PharmaFlow<span style={{ color: "var(--brand)" }}> AI</span></div>
          <p style={{ color: "var(--muted)", fontSize: 14, marginTop: 4 }}>
            Once a medicine enters the return pipeline, the system creates a verifiable digital
            chain of custody and makes re-entry detectable at the point of sale.
          </p>
        </div>

        <div className="card" style={{ padding: 20 }}>
          <div className="label">Email</div>
          <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} style={{ margin: "6px 0 12px" }} />
          <div className="label">Password</div>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ margin: "6px 0 12px" }} />
          <button className="btn" disabled={busy} onClick={() => doLogin()} style={{ width: "100%" }}>Sign in</button>
          <ErrorText e={error} />

          <div style={{ borderTop: "1px solid var(--line)", margin: "16px 0", paddingTop: 12 }}>
            <div className="label" style={{ marginBottom: 8 }}>One-click demo login (real auth, password demo1234)</div>
            <div style={{ display: "grid", gap: 6 }}>
              {QUICK.map(([label, e]) => (
                <button key={e} className="btn secondary" disabled={busy} onClick={() => doLogin(e)} style={{ justifyContent: "flex-start" }}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 12 }}>
          Prototype with synthetic data and synthetic licenses. A real deployment operates under
          applicable CDSCO, licensing, biomedical-waste and state requirements.
        </p>
      </div>
    </div>
  );
}
