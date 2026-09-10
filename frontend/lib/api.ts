export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("pf_token");
}

export function setSession(token: string, user: unknown) {
  localStorage.setItem("pf_token", token);
  localStorage.setItem("pf_user", JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem("pf_token");
  localStorage.removeItem("pf_user");
}

export function currentUser<T = any>(): T | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("pf_user");
  return raw ? (JSON.parse(raw) as T) : null;
}

export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any) {
    super(typeof detail === "string" ? detail : detail?.message || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T = any>(
  path: string,
  opts: { method?: string; body?: unknown; auth?: boolean } = {}
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (opts.auth !== false && token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
  return data as T;
}
