"use client";
import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { currentUser, clearSession, getToken } from "@/lib/api";

type NavItem = { href: string; label: string; roles: string[] };
const NAV: NavItem[] = [
  { href: "/retailer", label: "Retailer POS", roles: ["RETAILER"] },
  { href: "/distributor", label: "Distributor", roles: ["DISTRIBUTOR"] },
  { href: "/manufacturer", label: "Manufacturer", roles: ["MANUFACTURER"] },
  { href: "/dashboard", label: "Control Tower", roles: ["STATE_DRUG_CONTROLLER", "ADMIN"] },
  { href: "/registry", label: "Registry Explorer", roles: ["RETAILER", "DISTRIBUTOR", "MANUFACTURER", "STATE_DRUG_CONTROLLER", "ADMIN"] },
  { href: "/alerts", label: "Re-entry Alerts", roles: ["MANUFACTURER", "STATE_DRUG_CONTROLLER", "ADMIN"] },
  { href: "/disputes", label: "Disputes", roles: ["RETAILER", "DISTRIBUTOR", "STATE_DRUG_CONTROLLER", "ADMIN"] },
  { href: "/admin", label: "Demo Control", roles: ["ADMIN"] },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const r = useRouter();
  const [user, setUser] = React.useState<any>(null);

  React.useEffect(() => {
    if (!getToken()) { r.replace("/"); return; }
    setUser(currentUser());
  }, [r]);

  if (!user) return null;
  const items = NAV.filter((n) => n.roles.includes(user.role));

  return (
    <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", minHeight: "100vh" }}>
      <aside style={{ background: "#0f172a", color: "#cbd5e1", padding: 16, display: "flex", flexDirection: "column" }}>
        <div style={{ fontWeight: 800, fontSize: 18, color: "#fff", marginBottom: 4 }}>
          PharmaFlow<span style={{ color: "#5b9bff" }}> AI</span>
        </div>
        <div style={{ fontSize: 11, color: "#64748b", marginBottom: 20 }}>Reverse-chain compliance registry</div>
        <nav style={{ display: "grid", gap: 4 }}>
          {items.map((n) => {
            const active = path === n.href || path.startsWith(n.href + "/");
            return (
              <Link key={n.href} href={n.href}
                style={{
                  padding: "9px 12px", borderRadius: 8, fontSize: 14, fontWeight: 600,
                  color: active ? "#fff" : "#cbd5e1", background: active ? "#1d4ed8" : "transparent",
                }}>
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div style={{ marginTop: "auto", fontSize: 12, color: "#94a3b8" }}>
          <div style={{ color: "#fff", fontWeight: 700 }}>{user.name}</div>
          <div>{user.role?.replaceAll("_", " ")}</div>
          <button className="btn secondary" style={{ marginTop: 10, width: "100%" }}
            onClick={() => { clearSession(); r.push("/"); }}>Sign out</button>
        </div>
      </aside>
      <main style={{ padding: 24, maxWidth: 1180, width: "100%" }}>{children}</main>
    </div>
  );
}
