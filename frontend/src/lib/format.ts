import type { Json, Source, Status } from "./types";

export const APP_NAME = "AutoEng Studio";

/** Where a result was computed, without naming hardware: "GPU" or "CPU". */
export function computeLabel(c?: { backend?: string; gpu?: unknown } | null): string {
  if (!c) return "CPU";
  return c.backend === "cupy" || (c.gpu != null && c.gpu !== "" && c.gpu !== false) ? "GPU" : "CPU";
}

export function fmt(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  const abs = Math.abs(v);
  if (abs !== 0 && (abs >= 1e5 || abs < 10 ** -digits)) return v.toPrecision(3);
  return v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Magnitude-aware formatting: ~3 significant figures, no trailing noise. */
export function num(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  const a = Math.abs(v);
  const digits = a === 0 ? 0 : a >= 100 ? 0 : a >= 10 ? 1 : a >= 1 ? 2 : Math.min(4, 2 - Math.floor(Math.log10(a)));
  return v.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  return `${(v * 100).toFixed(digits)} %`;
}

export function kwToHp(kw: number) {
  return kw * 1.34102;
}

export const SOURCE_LABEL: Record<Source, string> = {
  measured: "Measured",
  manufacturer: "Manufacturer",
  literature: "Literature",
  user: "User",
  estimated: "Estimated",
  unknown: "Unknown",
  calibrated: "Calibrated",
  community: "Community",
  calculated: "Calculated",
  simulated: "Simulated",
};

export const SOURCE_HELP: Record<Source, string> = {
  measured: "Measured on the real part or vehicle",
  manufacturer: "From a manufacturer datasheet or specification",
  literature: "From handbooks, standards or published research",
  user: "Entered by you",
  estimated: "An estimate: replace it with data when you can",
  unknown: "Origin unknown: treat results that depend on it as unverified",
  calibrated: "Fitted to your measured data",
  community: "Learned from similar real engines other users shared",
  calculated: "Calculated by an engineering model",
  simulated: "Produced by a simulation",
};

export const STATUS_LABEL: Record<Status, string> = {
  ok: "OK",
  warning: "Warning",
  critical: "Critical",
  failure: "Predicted failure",
  no_data: "No data",
  unchecked: "Not checked",
};

export const STATUS_COLOR: Record<Status, string> = {
  ok: "var(--good)",
  warning: "var(--warning)",
  critical: "var(--serious)",
  failure: "var(--critical)",
  no_data: "var(--ink-3)",
  unchecked: "var(--axis)",
};

export const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)"];

export function getAt(obj: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((o, k) => (o && typeof o === "object" ? (o as Json)[k] : undefined), obj);
}

export function setAt<T extends Json>(obj: T, path: string, value: unknown): T {
  const copy = structuredClone(obj);
  const keys = path.split(".");
  let node: Json = copy;
  keys.slice(0, -1).forEach((k) => {
    if (typeof node[k] !== "object" || node[k] === null) node[k] = {};
    node = node[k] as Json;
  });
  node[keys[keys.length - 1]] = value;
  return copy;
}

export function timeAgo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}
