"use client";

import { CheckCircle2, CircleDot, RotateCw, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { LineChartBands } from "@/components/charts/Charts";
import { Card, Note } from "@/components/ui";
import { api } from "@/lib/api";
import { fmt } from "@/lib/format";
import type { Json } from "@/lib/types";
import type { LayoutCylinder } from "./Engine3D";

interface OrderVerdict {
  force_n: number;
  couple_nm: number;
  force_balanced: boolean;
  couple_balanced: boolean;
  force_counterweightable: boolean;
  couple_counterweightable: boolean;
}

export interface BalanceResult {
  layout: string;
  cylinders: LayoutCylinder[];
  firing_intervals_deg: number[];
  even_firing: boolean;
  rod_ratio: number;
  rpm: number;
  unit_force_n: number;
  primary: OrderVerdict;
  secondary: OrderVerdict;
  summary: string[];
  trace: {
    crank_deg: number[];
    primary_vertical_n: number[];
    primary_lateral_n: number[];
    secondary_vertical_n: number[];
    secondary_lateral_n: number[];
  };
  package_mm: { length: number; width: number; height_above_crank: number };
  assumptions: string[];
}

/** Layout analysis for the current design, refreshed (debounced) as it is edited. */
export function useLayout(design: Json | null) {
  const [layout, setLayout] = useState<BalanceResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!design) return;
    const t = setTimeout(() => {
      api<BalanceResult>("/api/v1/engine/layout", { method: "POST", json: { design } })
        .then((r) => {
          setLayout(r);
          setError(null);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [design]);
  return { layout, error };
}

const LAYOUT_NAME: Record<string, string> = { inline: "Inline", v: "V", w: "W", flat: "Flat" };

function Verdict({ label, v }: { label: string; v: OrderVerdict }) {
  const row = (what: string, value: number, unit: string, balanced: boolean, cw: boolean) => {
    const Icon = balanced ? CheckCircle2 : cw ? RotateCw : TriangleAlert;
    const color = balanced ? "var(--good)" : cw ? "var(--ink-2)" : "var(--warning)";
    const text = balanced ? "Balanced" : cw ? "Cancelled by counterweights" : "Free";
    return (
      <tr className="border-t border-line">
        <td className="py-2">{what}</td>
        <td className="py-2 text-right tabular">{balanced ? "0" : fmt(value, 0)} {unit}</td>
        <td className="py-2 pl-4">
          <span className="inline-flex items-center gap-1.5 text-xs">
            <Icon className="size-3.5" style={{ color }} aria-hidden /> {text}
          </span>
        </td>
      </tr>
    );
  };
  return (
    <>
      <tr>
        <td colSpan={3} className="eyebrow pb-1 pt-4">{label}</td>
      </tr>
      {row("Force", v.force_n, "N", v.force_balanced, v.force_counterweightable)}
      {row("Rocking couple", v.couple_nm, "N·m", v.couple_balanced, v.couple_counterweightable)}
    </>
  );
}

/** Firing events around the 720° four-stroke cycle. */
function FiringClock({ gaps }: { gaps: number[] }) {
  const events = gaps.reduce<number[]>((acc, g, i) => [...acc, i === 0 ? 0 : acc[i - 1] + gaps[i - 1]], []);
  const R = 88;
  const c = 110;
  const pt = (deg: number, rad: number) => {
    const a = (deg / 720) * 2 * Math.PI - Math.PI / 2;
    return [c + rad * Math.cos(a), c + rad * Math.sin(a)];
  };
  return (
    <svg viewBox="-14 0 248 220" className="mx-auto w-full max-w-[240px]" role="img" aria-label={`Firing events every ${gaps.map((g) => fmt(g, 0)).join(", ")} degrees`}>
      <circle cx={c} cy={c} r={R} fill="none" stroke="var(--line-strong)" />
      {[0, 180, 360, 540].map((d) => {
        const [x, y] = pt(d, R + 14);
        return (
          <text key={d} x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="fill-[var(--ink-3)] text-[10px]">
            {d}°
          </text>
        );
      })}
      {events.map((e, i) => {
        const [x1, y1] = pt(e, R - 10);
        const [x2, y2] = pt(e, R + 4);
        return (
          <g key={i}>
            <line x1={c} y1={c} x2={x1} y2={y1} stroke="var(--line)" />
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--s1)" strokeWidth={3} />
          </g>
        );
      })}
      <text x={c} y={c - 6} textAnchor="middle" className="fill-[var(--ink)] text-[22px] font-light">
        {gaps.length}
      </text>
      <text x={c} y={c + 14} textAnchor="middle" className="fill-[var(--ink-3)] text-[10px] uppercase tracking-[0.16em]">
        per cycle
      </text>
    </svg>
  );
}

export function BalancePanel({ layout, cylinders, bankAngle }: { layout: BalanceResult; cylinders: number; bankAngle: number }) {
  const name = `${LAYOUT_NAME[layout.layout] ?? layout.layout}${cylinders}`;
  const distinct = [...new Set(layout.firing_intervals_deg.map((g) => Math.round(g)))];
  const t = layout.trace;
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[1fr_1fr_1fr]">
        <Card title={`${name} balance`} subtitle={`Free inertia forces at ${fmt(layout.rpm, 0)} rpm (redline). One piston's primary force is ${fmt(layout.unit_force_n, 0)} N.`}>
          <table className="w-full text-sm">
            <tbody>
              <Verdict label="Primary (1× crank speed)" v={layout.primary} />
              <Verdict label="Secondary (2× crank speed)" v={layout.secondary} />
            </tbody>
          </table>
        </Card>
        <Card title="Firing" subtitle={layout.even_firing ? "Even firing: power pulses are equally spaced." : "Uneven firing: pulses are bunched, giving a lumpy torque and a distinctive sound."}>
          <FiringClock gaps={layout.firing_intervals_deg} />
          <p className="mt-3 flex items-center justify-center gap-2 text-sm tabular">
            <CircleDot className="size-3.5 text-ink-3" aria-hidden />
            Intervals {distinct.map((g) => `${g}°`).join(" / ")}
          </p>
        </Card>
        <Card title="Package" subtitle="Rough block envelope, for fitting the engine in a bay.">
          <dl className="grid grid-cols-2 gap-y-3 text-sm">
            <dt className="text-ink-3">Length along crank</dt>
            <dd className="text-right tabular">{fmt(layout.package_mm.length, 0)} mm</dd>
            <dt className="text-ink-3">Width</dt>
            <dd className="text-right tabular">{fmt(layout.package_mm.width, 0)} mm</dd>
            <dt className="text-ink-3">Height above crank</dt>
            <dd className="text-right tabular">{fmt(layout.package_mm.height_above_crank, 0)} mm</dd>
            {layout.layout !== "inline" && (
              <>
                <dt className="text-ink-3">Bank angle</dt>
                <dd className="text-right tabular">{fmt(bankAngle, 0)}°</dd>
              </>
            )}
            <dt className="text-ink-3">Rod ratio r/L</dt>
            <dd className="text-right tabular">{fmt(layout.rod_ratio, 3)}</dd>
          </dl>
        </Card>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <LineChartBands
          title="Primary shaking force"
          subtitle="Net force from all pistons over one crank revolution. Zero lines mean the order is balanced."
          x={t.crank_deg}
          xLabel="Crank angle"
          xUnit="°"
          unit="N"
          syncId="balance"
          series={[
            { id: "pv", label: "Vertical", color: "var(--s1)", values: t.primary_vertical_n },
            { id: "pl", label: "Lateral", color: "var(--s2)", values: t.primary_lateral_n },
          ]}
        />
        <LineChartBands
          title="Secondary shaking force"
          subtitle="Twice-per-revolution force from the rod angularity (λ = r/L). The reason big inline-fours get balance shafts."
          x={t.crank_deg}
          xLabel="Crank angle"
          xUnit="°"
          unit="N"
          syncId="balance"
          series={[
            { id: "sv", label: "Vertical", color: "var(--s1)", values: t.secondary_vertical_n },
            { id: "sl", label: "Lateral", color: "var(--s2)", values: t.secondary_lateral_n },
          ]}
        />
      </div>
      <Card title="Cylinder arrangement">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm tabular">
            <thead className="text-left text-xs text-ink-2">
              <tr>
                <th className="py-1.5 font-medium">Cylinder</th>
                <th className="py-1.5 font-medium">Bank</th>
                <th className="py-1.5 text-right font-medium">Along crank</th>
                <th className="py-1.5 text-right font-medium">Bank angle</th>
                <th className="py-1.5 text-right font-medium">Crankpin</th>
              </tr>
            </thead>
            <tbody>
              {layout.cylinders.map((c) => (
                <tr key={c.index} className="border-t border-line">
                  <td className="py-1.5">{c.index + 1}</td>
                  <td className="py-1.5">{String.fromCharCode(65 + c.bank)}</td>
                  <td className="py-1.5 text-right">{fmt(c.x * 1000, 0)} mm</td>
                  <td className="py-1.5 text-right">{fmt(c.bank_angle, 1)}°</td>
                  <td className="py-1.5 text-right">{fmt(c.pin_angle, 0)}°</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Note>
        {layout.summary.join(". ")}. {layout.assumptions.join(" ")}
      </Note>
    </div>
  );
}
