"use client";
import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ScanLine,
  Truck,
  Factory,
  LayoutGrid,
  DatabaseZap,
  ShieldAlert,
  Scale,
  SlidersHorizontal,
  LogOut,
  Menu,
  X,
  ChevronDown,
} from "lucide-react";
import { currentUser, clearSession, getToken } from "@/lib/api";
import { cn } from "@/lib/ui";
import { useRealtime } from "@/lib/realtime";
import NotifBell from "@/components/NotifBell";

type Item = { href: string; label: string; icon: React.ReactNode; roles: string[]; group: string };

const NAV: Item[] = [
  { href: "/retailer", label: "Retailer POS", icon: <ScanLine size={17} />, roles: ["RETAILER"], group: "Workspace" },
  { href: "/distributor", label: "Distributor", icon: <Truck size={17} />, roles: ["DISTRIBUTOR"], group: "Workspace" },
  { href: "/manufacturer", label: "Manufacturer", icon: <Factory size={17} />, roles: ["MANUFACTURER"], group: "Workspace" },
  { href: "/dashboard", label: "Control Tower", icon: <LayoutGrid size={17} />, roles: ["STATE_DRUG_CONTROLLER", "ADMIN"], group: "Workspace" },
  { href: "/registry", label: "Registry Explorer", icon: <DatabaseZap size={17} />, roles: ["RETAILER", "DISTRIBUTOR", "MANUFACTURER", "STATE_DRUG_CONTROLLER", "ADMIN"], group: "Oversight" },
  { href: "/alerts", label: "Re-entry Alerts", icon: <ShieldAlert size={17} />, roles: ["MANUFACTURER", "STATE_DRUG_CONTROLLER", "ADMIN"], group: "Oversight" },
  { href: "/disputes", label: "Disputes", icon: <Scale size={17} />, roles: ["RETAILER", "DISTRIBUTOR", "STATE_DRUG_CONTROLLER", "ADMIN"], group: "Oversight" },
  { href: "/admin", label: "Demo Control", icon: <SlidersHorizontal size={17} />, roles: ["ADMIN"], group: "System" },
];

const TITLES: Record<string, string> = {
  "/retailer": "Retailer POS & Inventory",
  "/distributor": "Distributor Operations",
  "/manufacturer": "Manufacturer Desk",
  "/dashboard": "Control Tower",
  "/registry": "Registry Explorer",
  "/alerts": "Re-entry Alerts",
  "/disputes": "Disputes",
  "/admin": "Demo Control",
};

function titleFor(path: string) {
  if (path.startsWith("/batch/")) return "Batch Detail";
  if (path.startsWith("/alerts/")) return "Re-entry Alert";
  return TITLES[path] || "PharmaFlow AI";
}

function initials(name = "") {
  return name.replace(/[^A-Za-z ]/g, "").split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "PF";
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const r = useRouter();
  const { connected } = useRealtime();
  const [user, setUser] = React.useState<any>(null);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [menuOpen, setMenuOpen] = React.useState(false);

  React.useEffect(() => {
    if (!getToken()) { r.replace("/"); return; }
    setUser(currentUser());
  }, [r]);

  React.useEffect(() => { setMobileOpen(false); setMenuOpen(false); }, [path]);

  if (!user) return null;
  const items = NAV.filter((n) => n.roles.includes(user.role));
  const groups = Array.from(new Set(items.map((i) => i.group)));

  const sidebar = (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex items-center gap-2 px-5 pb-4 pt-5">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-[13px] font-bold text-white">Pf</div>
        <div>
          <div className="text-[14px] font-semibold text-white">PharmaFlow AI</div>
          <div className="text-[10.5px] text-sidebar-ink-dim">Reverse-chain registry</div>
        </div>
        <button className="ml-auto text-sidebar-ink lg:hidden" onClick={() => setMobileOpen(false)}>
          <X size={18} />
        </button>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-2">
        {groups.map((g) => (
          <div key={g}>
            <div className="px-2 pb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-sidebar-ink-dim">{g}</div>
            <div className="space-y-0.5">
              {items.filter((i) => i.group === g).map((n) => {
                const active = path === n.href || path.startsWith(n.href + "/");
                return (
                  <Link
                    key={n.href}
                    href={n.href}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors",
                      active ? "bg-brand text-white" : "text-sidebar-ink hover:bg-sidebar-hover hover:text-white"
                    )}
                  >
                    <span className={cn(active ? "text-white" : "text-sidebar-ink-dim")}>{n.icon}</span>
                    {n.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-white/5 px-4 py-3 text-[11px] leading-relaxed text-sidebar-ink-dim">
        Prototype · synthetic data &amp; licenses. A real deployment operates under CDSCO,
        licensing and biomedical-waste requirements.
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      {/* desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen lg:block">{sidebar}</aside>

      {/* mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-[264px] shadow-2xl">{sidebar}</div>
        </div>
      )}

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur sm:px-6">
          <button className="text-ink-soft lg:hidden" onClick={() => setMobileOpen(true)}>
            <Menu size={20} />
          </button>
          <h2 className="text-[15px] font-semibold text-ink">{titleFor(path)}</h2>
          <span
            className={cn(
              "ml-2 hidden items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium sm:inline-flex",
              connected ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn"
            )}
            title={connected ? "Live updates connected" : "Reconnecting — falling back to polling"}
          >
            <span className={cn("h-1.5 w-1.5 rounded-full", connected ? "bg-ok" : "bg-warn animate-[pf-pulse_1.4s_ease-in-out_infinite]")} />
            {connected ? "Live" : "Reconnecting"}
          </span>

          <div className="relative ml-auto flex items-center gap-1">
            <NotifBell />
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-2 rounded-lg px-1.5 py-1.5 hover:bg-line-soft"
            >
              <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-soft text-[12px] font-bold text-brand">
                {initials(user.name)}
              </span>
              <span className="hidden text-left sm:block">
                <span className="block max-w-[160px] truncate text-[12.5px] font-semibold text-ink">{user.name}</span>
                <span className="block text-[11px] text-muted">{user.role?.replaceAll("_", " ")}</span>
              </span>
              <ChevronDown size={15} className="text-muted" />
            </button>
            {menuOpen && (
              <div className="pf-anim-in absolute right-0 z-50 mt-1.5 w-52 rounded-xl bg-surface p-1.5 shadow-xl ring-1 ring-line">
                <div className="px-2.5 py-2 text-[12px] text-muted">
                  Signed in as
                  <div className="mt-0.5 truncate font-semibold text-ink">{user.name}</div>
                </div>
                <button
                  onClick={() => { clearSession(); r.push("/"); }}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] font-medium text-danger hover:bg-danger-soft"
                >
                  <LogOut size={15} /> Sign out
                </button>
              </div>
            )}
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1220px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
