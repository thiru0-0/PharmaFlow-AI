"use client";
import React from "react";
import { API, api, getToken } from "@/lib/api";
import { useAsync } from "@/lib/ui";

/* ------------------------------------------------------------------ */
/*  live event bus (browser side)                                      */
/* ------------------------------------------------------------------ */
export type LiveEvent = { kind: string; [k: string]: any };

const bus = typeof window !== "undefined" ? new EventTarget() : null;

export function onLive(cb: (e: LiveEvent) => void): () => void {
  if (!bus) return () => {};
  const h = (ev: Event) => cb((ev as CustomEvent).detail as LiveEvent);
  bus.addEventListener("live", h);
  return () => bus.removeEventListener("live", h);
}

type RealtimeState = { connected: boolean };
const Ctx = React.createContext<RealtimeState>({ connected: false });
export const useRealtime = () => React.useContext(Ctx);

/**
 * Opens one SSE connection for the whole app. The JWT rides in the query string
 * because EventSource can't set headers — fine for this read-only stream over TLS.
 */
export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = React.useState(false);

  React.useEffect(() => {
    const token = getToken();
    if (!token) return;

    let es: EventSource | null = null;
    let stopped = false;
    let backoff = 1000;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (stopped) return;
      es = new EventSource(`${API}/stream?token=${encodeURIComponent(token)}`);
      es.addEventListener("hello", () => { setConnected(true); backoff = 1000; });
      es.addEventListener("message", (e) => {
        try {
          bus?.dispatchEvent(new CustomEvent("live", { detail: JSON.parse((e as MessageEvent).data) }));
        } catch {}
      });
      es.onerror = () => {
        setConnected(false);
        es?.close();
        if (!stopped) {
          retry = setTimeout(connect, backoff);
          backoff = Math.min(backoff * 2, 15000);
        }
      };
    };

    connect();
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
      es?.close();
    };
  }, []);

  return <Ctx.Provider value={{ connected }}>{children}</Ctx.Provider>;
}

/* ------------------------------------------------------------------ */
/*  live query — useAsync + push refetch + poll fallback              */
/* ------------------------------------------------------------------ */
export function useLiveQuery<T>(
  fn: () => Promise<T>,
  deps: any[] = [],
  opts: { kinds?: string[]; pollMs?: number } = {}
) {
  const q = useAsync<T>(fn, deps);
  const { connected } = useRealtime();
  const reloadRef = React.useRef(q.reload);
  reloadRef.current = q.reload;
  const debounce = React.useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const kinds = opts.kinds;
  const kindKey = kinds ? kinds.join(",") : "*";

  // push: refetch on a relevant live event (coalesced)
  React.useEffect(() => {
    return onLive((e) => {
      if (kinds && !kinds.includes(e.kind)) return;
      if (debounce.current) clearTimeout(debounce.current);
      debounce.current = setTimeout(() => reloadRef.current(), 350);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kindKey]);

  // refetch when the tab regains focus / becomes visible
  React.useEffect(() => {
    const onFocus = () => reloadRef.current();
    const onVis = () => { if (!document.hidden) reloadRef.current(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  // poll fallback only while the stream is down
  React.useEffect(() => {
    if (connected) return;
    const t = setInterval(() => reloadRef.current(), opts.pollMs ?? 6000);
    return () => clearInterval(t);
  }, [connected, opts.pollMs]);

  return q;
}

/* ------------------------------------------------------------------ */
/*  notifications                                                      */
/* ------------------------------------------------------------------ */
export type Notif = {
  id: string; type: string; channel: string; delivery_status: string;
  payload: any; read: boolean; created_at: string; batch_id: string | null; recipient: string;
};

export function useNotifications() {
  const [items, setItems] = React.useState<Notif[]>([]);
  const [unread, setUnread] = React.useState(0);

  const load = React.useCallback(async () => {
    try {
      const r = await api<{ unread_count: number; items: Notif[] }>("/notifications?limit=40");
      setItems(r.items);
      setUnread(r.unread_count);
    } catch {}
  }, []);

  React.useEffect(() => { load(); }, [load]);

  React.useEffect(
    () => onLive((e) => { if (e.kind === "notification" || e.kind === "reentry") load(); }),
    [load]
  );

  React.useEffect(() => {
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  const markAll = React.useCallback(async () => {
    setUnread(0);
    setItems((xs) => xs.map((x) => ({ ...x, read: true })));
    try { await api("/notifications/read-all", { method: "POST" }); } finally { load(); }
  }, [load]);

  const markOne = React.useCallback(async (id: string) => {
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, read: true } : x)));
    setUnread((u) => Math.max(0, u - 1));
    try { await api(`/notifications/${id}/read`, { method: "POST" }); } finally { load(); }
  }, [load]);

  return { items, unread, reload: load, markAll, markOne };
}
