"use client";

import clsx from "clsx";
import { AlertTriangle, CheckCircle2, CircleHelp, Loader2, type LucideIcon, OctagonX, ShieldAlert, X } from "lucide-react";
import { useState } from "react";
import { twMerge } from "tailwind-merge";
import { SOURCE_HELP, SOURCE_LABEL, STATUS_COLOR, STATUS_LABEL } from "@/lib/format";
import type { Source, Status } from "@/lib/types";

export function Button({
  variant = "secondary",
  size = "md",
  className,
  loading,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}) {
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || loading}
      className={twMerge(
        clsx(
          "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-[2px] font-display font-medium uppercase tracking-[0.16em] transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-40",
          size === "sm" && "h-8 px-3 text-[11px]",
          size === "md" && "h-10 px-5 text-[12px]",
          size === "lg" && "h-12 px-8 text-[13px]",
          variant === "primary" && "bg-accent text-accent-ink hover:opacity-90",
          variant === "secondary" && "border border-line-strong text-ink hover:border-ink hover:bg-accent-soft",
          variant === "ghost" && "text-ink-2 hover:text-ink",
          variant === "danger" && "border border-line-strong text-[var(--critical)] hover:border-[var(--critical)]",
        ),
        className,
      )}
    >
      {loading && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Card({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={twMerge("border border-line bg-surface", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            {title && <h3 className="display text-[15px] text-ink">{title}</h3>}
            {subtitle && <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-ink-2">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={twMerge("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

const STATUS_ICON: Record<Status, LucideIcon> = {
  ok: CheckCircle2,
  warning: AlertTriangle,
  critical: ShieldAlert,
  failure: OctagonX,
  no_data: CircleHelp,
  unchecked: CircleHelp,
};

export function StatusBadge({ status, compact }: { status: Status; compact?: boolean }) {
  const Icon = STATUS_ICON[status] ?? CircleHelp;
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-ink">
      <Icon className="size-3.5 shrink-0" style={{ color: STATUS_COLOR[status] }} aria-hidden />
      {!compact && STATUS_LABEL[status]}
      {compact && <span className="sr-only">{STATUS_LABEL[status]}</span>}
    </span>
  );
}

export function SourceBadge({ source, reference }: { source: Source; reference?: string | null }) {
  const tone =
    source === "measured" || source === "calibrated"
      ? "border-[var(--good)] text-ink"
      : source === "estimated" || source === "unknown"
        ? "border-dashed border-line-strong text-ink-3"
        : "border-line-strong text-ink-2";
  return (
    <span
      title={`${SOURCE_HELP[source] ?? source}${reference ? `\n${reference}` : ""}`}
      className={clsx("inline-flex items-center border px-1.5 py-px font-display text-[10px] font-medium uppercase tracking-[0.14em]", tone)}
    >
      {SOURCE_LABEL[source] ?? source}
    </span>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: string; icon?: LucideIcon }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <nav role="tablist" className="flex gap-7 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={clsx(
            "-mb-px inline-flex items-center gap-2 whitespace-nowrap border-b py-3 font-display text-[13px] font-medium uppercase tracking-[0.16em] transition-colors",
            value === t.id ? "border-ink text-ink" : "border-transparent text-ink-3 hover:text-ink-2",
          )}
        >
          {t.icon && <t.icon className="size-3.5" strokeWidth={1.5} aria-hidden />}
          {t.label}
        </button>
      ))}
    </nav>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { id: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex border border-line-strong p-0.5">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          className={clsx(
            "px-3 py-1 font-display text-[11px] font-medium uppercase tracking-[0.14em] transition-colors",
            value === o.id ? "bg-accent text-accent-ink" : "text-ink-2 hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="eyebrow mb-1.5 block">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-3">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "h-9 w-full rounded-[2px] border border-line bg-surface-2 px-2.5 text-sm text-ink placeholder:text-ink-3 transition-colors hover:border-line-strong focus:border-ink focus:outline-none";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={twMerge(inputClass, "tabular", props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={twMerge(inputClass, props.className)} />;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-2 text-sm text-ink-2" role="status">
      <Loader2 className="size-4 animate-spin" strokeWidth={1.5} aria-hidden />
      <span className="eyebrow">{label ?? "Loading"}</span>
    </div>
  );
}

export function ErrorNote({ error, onClose }: { error: string | null; onClose?: () => void }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex items-start gap-3 border border-[var(--critical)]/60 bg-surface px-4 py-3 text-sm text-ink">
      <OctagonX className="mt-0.5 size-4 shrink-0 text-[var(--critical)]" aria-hidden />
      <span className="flex-1 whitespace-pre-wrap">{error}</span>
      {onClose && (
        <button type="button" onClick={onClose} aria-label="Dismiss" className="text-ink-3 hover:text-ink">
          <X className="size-4" />
        </button>
      )}
    </div>
  );
}

export function Note({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warning" }) {
  return (
    <div
      className={clsx(
        "flex items-start gap-3 border-l-2 bg-surface px-4 py-3 text-[13px] leading-relaxed text-ink-2",
        tone === "warning" ? "border-[var(--warning)]" : "border-line-strong",
      )}
    >
      {tone === "warning" && <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-[var(--warning)]" aria-hidden />}
      <div>{children}</div>
    </div>
  );
}

/** Spec-sheet figure: spaced label, large light numeral, quiet context line. */
export function Stat({
  label,
  value,
  unit,
  sub,
  status,
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: React.ReactNode;
  status?: Status;
}) {
  return (
    <div className="border border-line bg-surface px-5 py-4">
      <div className="flex items-center justify-between gap-2">
        <span className="eyebrow">{label}</span>
        {status && <StatusBadge status={status} compact />}
      </div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="text-[34px] font-extralight leading-none tracking-tight text-ink">{value}</span>
        {unit && <span className="display text-sm text-ink-2">{unit}</span>}
      </div>
      {sub && <div className="mt-2 text-xs text-ink-3">{sub}</div>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="border border-dashed border-line-strong px-6 py-14 text-center">
      <p className="display text-sm text-ink">{title}</p>
      {children && <div className="mt-2 text-sm text-ink-2">{children}</div>}
    </div>
  );
}

export function SectionTitle({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
        <h2 className="display text-2xl font-light tracking-[0.08em] text-ink sm:text-3xl">{title}</h2>
      </div>
      {children}
    </div>
  );
}

export function useAsync() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, setError, run };
}
