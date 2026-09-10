"use client";
import React from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { api, setSession, clearSession } from "@/lib/api";
import { Button, Field, Input, InlineError } from "@/lib/ui";

const HOME: Record<string, string> = {
  RETAILER: "/retailer",
  DISTRIBUTOR: "/distributor",
  MANUFACTURER: "/manufacturer",
  STATE_DRUG_CONTROLLER: "/dashboard",
  ADMIN: "/dashboard",
};

const QUICK: [string, string, string][] = [
  ["Retailer A", "CityCare Pharmacy", "retailer.a@pharmaflow.demo"],
  ["Retailer B", "MedPlus Demo", "retailer.b@pharmaflow.demo"],
  ["Distributor", "Meridian Distribution", "distributor@pharmaflow.demo"],
  ["Manufacturer", "Nucleus Pharma", "manufacturer@pharmaflow.demo"],
  ["State Drug Controller", "Maharashtra FDA", "regulator@pharmaflow.demo"],
  ["Platform Admin", "PharmaFlow Ops", "admin@pharmaflow.demo"],
];

export default function Login() {
  const r = useRouter();
  const [email, setEmail] = React.useState("admin@pharmaflow.demo");
  const [password, setPassword] = React.useState("demo1234");
  const [error, setError] = React.useState<any>(null);
  const [busy, setBusy] = React.useState<string | null>(null);

  React.useEffect(() => { clearSession(); }, []);

  async function doLogin(e: string, pw?: string) {
    setBusy(e); setError(null);
    try {
      const res = await api<any>("/auth/login", { method: "POST", auth: false, body: { email: e, password: pw ?? "demo1234" } });
      setSession(res.access_token, res);
      r.push(HOME[res.role] || "/dashboard");
    } catch (err) { setError(err); setBusy(null); }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* brand panel */}
      <div className="relative hidden flex-col justify-between bg-sidebar p-12 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand text-[14px] font-bold">Pf</div>
          <span className="text-[16px] font-semibold">PharmaFlow AI</span>
        </div>
        <div className="max-w-md">
          <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em]">
            A verifiable chain of custody from pharmacy shelf to certified destruction.
          </h1>
          <p className="mt-4 text-[14px] leading-relaxed text-sidebar-ink">
            Once a medicine enters the return pipeline, PharmaFlow creates a tamper-evident record
            of every handoff — and makes re-entry detectable at the point of sale.
          </p>
          <div className="mt-8 flex items-center gap-2 text-[12.5px] text-sidebar-ink-dim">
            <ShieldCheck size={16} /> Hash-chained · Ed25519-signed · append-only registry
          </div>
        </div>
        <p className="text-[11.5px] leading-relaxed text-sidebar-ink-dim">
          Prototype with synthetic data and synthetic licenses. A real deployment operates under
          applicable CDSCO, licensing, biomedical-waste and state requirements.
        </p>
      </div>

      {/* form */}
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[380px]">
          <div className="mb-7 lg:hidden">
            <div className="text-[20px] font-semibold">PharmaFlow AI</div>
            <p className="mt-1 text-[13px] text-muted">Reverse-chain compliance registry</p>
          </div>

          <h2 className="text-[19px] font-semibold text-ink">Sign in</h2>
          <p className="mt-1 text-[13px] text-muted">Use your licensed account, or pick a demo role below.</p>

          <div className="mt-6 space-y-3">
            <Field label="Email">
              <Input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
            </Field>
            <Field label="Password">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
                onKeyDown={(e) => e.key === "Enter" && doLogin(email, password)} />
            </Field>
            <Button className="w-full" loading={busy === email} onClick={() => doLogin(email, password)}>
              Sign in <ArrowRight size={15} />
            </Button>
            <InlineError e={error} />
          </div>

          <div className="mt-7">
            <div className="mb-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
              One-click demo login · password demo1234
            </div>
            <div className="grid gap-1.5">
              {QUICK.map(([role, org, e]) => (
                <button
                  key={e}
                  onClick={() => doLogin(e)}
                  disabled={!!busy}
                  className="flex items-center justify-between rounded-lg bg-surface px-3 py-2.5 text-left ring-1 ring-line transition-colors hover:bg-surface-2 disabled:opacity-50"
                >
                  <span>
                    <span className="block text-[13px] font-semibold text-ink">{role}</span>
                    <span className="block text-[11.5px] text-muted">{org}</span>
                  </span>
                  <ArrowRight size={15} className="text-muted" />
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
