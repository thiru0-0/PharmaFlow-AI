"use client";
import React from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Check, Info, Loader2, X } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  helpers                                                            */
/* ------------------------------------------------------------------ */
export function cn(...parts: unknown[]) {
  return parts.filter((p) => typeof p === "string" && p).join(" ");
}

export type Tone = "neutral" | "brand" | "success" | "warning" | "danger" | "info";

const TONE_BADGE: Record<Tone, string> = {
  neutral: "bg-line-soft text-ink-soft ring-line",
  brand: "bg-brand-soft text-brand ring-brand-ring",
  success: "bg-ok-soft text-ok ring-ok/20",
  warning: "bg-warn-soft text-warn ring-warn/20",
  danger: "bg-danger-soft text-danger ring-danger/20",
  info: "bg-info-soft text-info ring-info/15",
};

/** Map a domain status/state string to a semantic tone. */
export function toneFor(value?: string): Tone {
  const v = (value || "").toUpperCase();
  if (["ACTIVE", "PICKUP_CONFIRMED", "RESOLVED", "SOLD", "COMPLIANT", "CONFIRMED", "HEALTHY", "VALID", "PICKED_UP"].includes(v))
    return v === "ACTIVE" || v === "SOLD" || v === "COMPLIANT" || v === "HEALTHY" || v === "VALID" ? "success" : "info";
  if (["RETURN_INITIATED", "AUTO_CREATED", "PENDING", "OPEN", "SCHEDULED", "PICKUP_SCHEDULED", "AWAITING", "RECEIVED_BY_MANUFACTURER"].includes(v))
    return v === "OPEN" ? "warning" : v === "RECEIVED_BY_MANUFACTURER" || v === "PICKUP_SCHEDULED" ? "info" : "warning";
  if (["DISPUTED", "EXPIRED", "NON_COMPLIANT", "CRITICAL", "BLOCKED", "REENTRY", "INVALID", "BREACH", "SUSPENDED"].includes(v))
    return "danger";
  if (["DESTROYED_CERTIFIED", "CLOSED"].includes(v)) return "neutral";
  return "neutral";
}

/* ------------------------------------------------------------------ */
/*  primitives                                                         */
/* ------------------------------------------------------------------ */
export function Spinner({ className = "" }: { className?: string }) {
  return <Loader2 className={cn("animate-[pf-spin_.7s_linear_infinite]", className)} size={16} />;
}

export function Badge({
  tone = "neutral",
  children,
  className,
  dot,
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11.5px] font-semibold leading-5 ring-1 ring-inset whitespace-nowrap",
        TONE_BADGE[tone],
        className
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />}
      {children}
    </span>
  );
}

export function StatusBadge({ value, className }: { value?: string; className?: string }) {
  if (!value) return null;
  return (
    <Badge tone={toneFor(value)} className={className}>
      {value.replaceAll("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}
    </Badge>
  );
}

type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "success";
const BTN: Record<BtnVariant, string> = {
  primary: "bg-brand text-white hover:bg-brand-hover shadow-[0_1px_2px_rgba(37,99,235,.25)]",
  secondary: "bg-surface text-ink ring-1 ring-inset ring-line hover:bg-surface-2",
  ghost: "bg-transparent text-ink-soft hover:bg-line-soft",
  danger: "bg-danger text-white hover:brightness-95",
  success: "bg-ok text-white hover:brightness-95",
};

export const Button = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: BtnVariant;
    size?: "sm" | "md";
    loading?: boolean;
    icon?: React.ReactNode;
  }
>(function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors disabled:opacity-50 disabled:pointer-events-none",
        size === "sm" ? "px-2.5 py-1.5 text-[12.5px]" : "px-3.5 py-2 text-[13.5px]",
        BTN[variant],
        className
      )}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
});

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "w-full rounded-lg bg-surface px-3 py-2 text-[13.5px] text-ink ring-1 ring-inset ring-line placeholder:text-muted",
        "focus:outline-none focus:ring-2 focus:ring-brand transition-shadow",
        props.className
      )}
    />
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "w-full rounded-lg bg-surface px-3 py-2 text-[13.5px] text-ink ring-1 ring-inset ring-line placeholder:text-muted",
        "focus:outline-none focus:ring-2 focus:ring-brand min-h-[80px] resize-y",
        props.className
      )}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "w-full rounded-lg bg-surface px-3 py-2 text-[13.5px] text-ink ring-1 ring-inset ring-line",
        "focus:outline-none focus:ring-2 focus:ring-brand",
        props.className
      )}
    />
  );
}

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label?: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("block", className)}>
      {label && <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</span>}
      {children}
      {hint && !error && <span className="mt-1 block text-[12px] text-muted">{hint}</span>}
      {error && <span className="mt-1 block text-[12px] font-medium text-danger">{error}</span>}
    </label>
  );
}

export function Mono({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("font-[family-name:var(--font-mono)] text-[12px] text-ink-soft", className)}>{children}</span>;
}

/* ------------------------------------------------------------------ */
/*  layout blocks                                                      */
/* ------------------------------------------------------------------ */
export function Card({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  padded = true,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  padded?: boolean;
}) {
  return (
    <section className={cn("rounded-[var(--radius-card)] bg-surface ring-1 ring-line shadow-[0_1px_2px_rgba(16,24,40,.04)]", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-line-soft px-5 py-3.5">
          <div>
            {title && <h3 className="text-[14.5px] font-semibold text-ink">{title}</h3>}
            {description && <p className="mt-0.5 text-[12.5px] text-muted">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn(padded ? "p-5" : "", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-[22px] font-semibold tracking-[-0.02em] text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-[13.5px] text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: Tone;
  icon?: React.ReactNode;
}) {
  const ring: Record<Tone, string> = {
    neutral: "bg-line-soft text-ink-soft",
    brand: "bg-brand-soft text-brand",
    success: "bg-ok-soft text-ok",
    warning: "bg-warn-soft text-warn",
    danger: "bg-danger-soft text-danger",
    info: "bg-info-soft text-info",
  };
  return (
    <div className="rounded-[var(--radius-card)] bg-surface p-4 ring-1 ring-line shadow-[0_1px_2px_rgba(16,24,40,.04)]">
      <div className="flex items-center justify-between">
        <span className="text-[11.5px] font-semibold uppercase tracking-wide text-muted">{label}</span>
        {icon && <span className={cn("grid h-7 w-7 place-items-center rounded-lg", ring[tone])}>{icon}</span>}
      </div>
      <div className="mt-2 text-[26px] font-semibold tracking-[-0.02em] text-ink tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-[12px] text-muted">{hint}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  table                                                              */
/* ------------------------------------------------------------------ */
export function Table({
  head,
  children,
  empty,
  emptyLabel = "Nothing to show",
  className,
}: {
  head: React.ReactNode[];
  children: React.ReactNode;
  empty?: boolean;
  emptyLabel?: string;
  className?: string;
}) {
  return (
    <div className={cn("-mx-5 -my-5 overflow-x-auto", className)}>
      <table className="w-full min-w-[560px] border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line">
            {head.map((h, i) => (
              <th key={i} className="whitespace-nowrap px-5 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-muted">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {empty ? (
            <tr>
              <td colSpan={head.length} className="px-5 py-10 text-center text-[13px] text-muted">
                {emptyLabel}
              </td>
            </tr>
          ) : (
            children
          )}
        </tbody>
      </table>
    </div>
  );
}

export function Tr({ children, className, onClick }: { children: React.ReactNode; className?: string; onClick?: () => void }) {
  return (
    <tr
      onClick={onClick}
      className={cn("border-b border-line-soft last:border-0 transition-colors", onClick && "cursor-pointer hover:bg-surface-2", className)}
    >
      {children}
    </tr>
  );
}

export function Td({ children, className, colSpan }: { children?: React.ReactNode; className?: string; colSpan?: number }) {
  return <td colSpan={colSpan} className={cn("px-5 py-3 align-middle text-ink-soft", className)}>{children}</td>;
}

/* ------------------------------------------------------------------ */
/*  feedback                                                           */
/* ------------------------------------------------------------------ */
export function Alert({
  tone = "info",
  title,
  children,
  actions,
  icon,
}: {
  tone?: Tone;
  title?: React.ReactNode;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  const map: Record<Tone, string> = {
    neutral: "bg-surface ring-line",
    brand: "bg-brand-soft ring-brand-ring",
    success: "bg-ok-soft ring-ok/20",
    warning: "bg-warn-soft ring-warn/25",
    danger: "bg-danger-soft ring-danger/25",
    info: "bg-info-soft ring-info/15",
  };
  const fallbackIcon =
    tone === "danger" || tone === "warning" ? <AlertTriangle size={16} /> : tone === "success" ? <Check size={16} /> : <Info size={16} />;
  return (
    <div className={cn("pf-anim-in rounded-xl p-4 ring-1 ring-inset", map[tone])}>
      <div className="flex gap-3">
        <span
          className={cn(
            "mt-0.5 shrink-0",
            tone === "danger" ? "text-danger" : tone === "warning" ? "text-warn" : tone === "success" ? "text-ok" : "text-info"
          )}
        >
          {icon ?? fallbackIcon}
        </span>
        <div className="min-w-0 flex-1">
          {title && <div className="text-[13.5px] font-semibold text-ink">{title}</div>}
          {children && <div className={cn("text-[13px] text-ink-soft", title && "mt-1")}>{children}</div>}
          {actions && <div className="mt-3 flex flex-wrap gap-2">{actions}</div>}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line px-6 py-12 text-center">
      {icon && <div className="mb-3 grid h-11 w-11 place-items-center rounded-xl bg-line-soft text-muted">{icon}</div>}
      <div className="text-[14px] font-semibold text-ink">{title}</div>
      {description && <p className="mt-1 max-w-sm text-[13px] text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: any; retry?: () => void }) {
  const msg = typeof error === "string" ? error : error?.message || "Something went wrong";
  return (
    <Alert
      tone="danger"
      title="Couldn’t load this data"
      actions={retry && <Button size="sm" variant="secondary" onClick={retry}>Retry</Button>}
    >
      {msg}
    </Alert>
  );
}

export function InlineError({ e }: { e: any }) {
  if (!e) return null;
  const msg = typeof e === "string" ? e : e?.message || JSON.stringify(e);
  return <p className="mt-2 text-[12.5px] font-medium text-danger">{msg}</p>;
}

export function SkeletonRows({ rows = 4, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <div key={c} className="pf-skeleton h-4 flex-1" style={{ opacity: 1 - r * 0.12 }} />
          ))}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  overlays                                                           */
/* ------------------------------------------------------------------ */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;
  const w = size === "sm" ? "max-w-sm" : size === "lg" ? "max-w-2xl" : "max-w-md";
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 pt-[10vh]" onMouseDown={onClose}>
      <div
        className={cn("pf-anim-in w-full rounded-2xl bg-surface shadow-xl ring-1 ring-line", w)}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line-soft px-5 py-4">
          <div>
            <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
            {description && <p className="mt-0.5 text-[12.5px] text-muted">{description}</p>}
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-line-soft hover:text-ink">
            <X size={16} />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line-soft px-5 py-3.5">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}

/** Small single-value prompt replacement. */
export function PromptModal({
  open,
  onClose,
  onSubmit,
  title,
  label,
  hint,
  type = "text",
  defaultValue = "",
  submitLabel = "Confirm",
  tone = "primary",
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (value: string) => Promise<void> | void;
  title: string;
  label: string;
  hint?: string;
  type?: "text" | "number";
  defaultValue?: string;
  submitLabel?: string;
  tone?: BtnVariant;
}) {
  const [value, setValue] = React.useState(defaultValue);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<any>(null);
  React.useEffect(() => { if (open) { setValue(defaultValue); setErr(null); } }, [open, defaultValue]);

  async function submit() {
    setBusy(true); setErr(null);
    try { await onSubmit(value); onClose(); } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant={tone} size="sm" loading={busy} onClick={submit}>{submitLabel}</Button>
        </>
      }
    >
      <Field label={label} hint={hint}>
        <Input
          autoFocus
          type={type}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
      </Field>
      <InlineError e={err} />
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/*  timeline                                                           */
/* ------------------------------------------------------------------ */
export function Timeline({ children }: { children: React.ReactNode }) {
  return <ol className="relative ml-1.5 border-l border-line pl-6">{children}</ol>;
}

export function TimelineItem({
  title,
  time,
  actor,
  tone = "brand",
  children,
  last,
}: {
  title: React.ReactNode;
  time?: React.ReactNode;
  actor?: React.ReactNode;
  tone?: Tone;
  children?: React.ReactNode;
  last?: boolean;
}) {
  const dot: Record<Tone, string> = {
    neutral: "bg-muted",
    brand: "bg-brand",
    success: "bg-ok",
    warning: "bg-warn",
    danger: "bg-danger",
    info: "bg-info",
  };
  return (
    <li className={cn("relative", last ? "pb-0" : "pb-5")}>
      <span className={cn("absolute -left-[30px] top-1 h-2.5 w-2.5 rounded-full ring-4 ring-surface", dot[tone])} />
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-[13px] font-semibold text-ink">{title}</span>
        {actor && <span className="text-[12px] text-muted">· {actor}</span>}
        {time && <span className="text-[12px] text-muted">· {time}</span>}
      </div>
      {children && <div className="mt-1 text-[12px] text-ink-soft">{children}</div>}
    </li>
  );
}

export function DataGrid({ items }: { items: Array<{ label: string; value: React.ReactNode }> }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
      {items.map((it, i) => (
        <div key={i}>
          <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">{it.label}</dt>
          <dd className="mt-1 text-[13.5px] text-ink">{it.value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ------------------------------------------------------------------ */
/*  data fetching hook                                                 */
/* ------------------------------------------------------------------ */
export function useAsync<T>(fn: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);
  const fnRef = React.useRef(fn);
  fnRef.current = fn;

  const run = React.useCallback(() => {
    setLoading(true);
    fnRef
      .current()
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  React.useEffect(() => { run(); }, [run]);
  return { data, error, loading, reload: run, setData };
}
