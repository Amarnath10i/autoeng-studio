"use client";

import { Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmt, num } from "@/lib/format";

export interface Series {
  id: string;
  label: string;
  color: string;
  values: (number | null)[];
  band?: { lo: (number | null)[]; hi: (number | null)[] };
  dashed?: boolean; // only for reference-type series (e.g. measured data or targets)
}

export interface RefLine {
  y: number;
  label: string;
  kind: "limit" | "target";
}

function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {series.map((s) => (
        <span key={s.id} className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} aria-hidden />
          {s.label}
        </span>
      ))}
    </div>
  );
}

function DataTable({
  x,
  xLabel,
  series,
  unit,
}: {
  x: (number | string)[];
  xLabel: string;
  series: Series[];
  unit: string;
}) {
  return (
    <div className="max-h-72 overflow-auto rounded border border-line">
      <table className="w-full text-xs tabular">
        <thead className="sticky top-0 bg-surface-2 text-ink-2">
          <tr>
            <th className="px-2 py-1 text-left font-medium">{xLabel}</th>
            {series.map((s) => (
              <th key={s.id} className="px-2 py-1 text-right font-medium">
                {s.label} {unit && `(${unit})`}
                {s.band && <span className="block font-normal text-ink-3">5–95 %</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {x.map((xv, i) => (
            <tr key={i} className="border-t border-line">
              <td className="px-2 py-0.5">{typeof xv === "number" ? fmt(xv, 1) : xv}</td>
              {series.map((s) => (
                <td key={s.id} className="px-2 py-0.5 text-right">
                  {fmt(s.values[i], 2)}
                  {s.band && (
                    <span className="block text-ink-3">
                      {fmt(s.band.lo[i], 1)}–{fmt(s.band.hi[i], 1)}
                    </span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChartFrame({
  title,
  subtitle,
  actions,
  legend,
  table,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  legend?: React.ReactNode;
  table?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <figure className="border border-line bg-surface p-5">
      <figcaption className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="display text-[14px] text-ink">{title}</div>
          {subtitle && <div className="text-xs text-ink-2">{subtitle}</div>}
        </div>
        <div className="flex items-center gap-2">
          {actions}
          {table && (
            <button type="button"
              onClick={() => setShowTable((v) => !v)}
              className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-ink-2 hover:bg-surface-2 hover:text-ink"
              aria-pressed={showTable}
            >
              <Table2 className="size-3.5" aria-hidden /> {showTable ? "Chart" : "Table"}
            </button>
          )}
        </div>
      </figcaption>
      {legend && <div className="mb-2">{legend}</div>}
      {showTable && table ? table : children}
    </figure>
  );
}

function TooltipBox({
  active,
  label,
  payload,
  xLabel,
  xUnit,
  unit,
  series,
}: {
  active?: boolean;
  label?: number | string;
  payload?: { payload: Record<string, unknown> }[];
  xLabel: string;
  xUnit: string;
  unit: string;
  series: Series[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="border border-line-strong bg-surface px-3 py-2 text-xs shadow-2xl">
      <div className="mb-1 font-medium text-ink">
        {xLabel} {typeof label === "number" ? fmt(label, 1) : label} {xUnit}
      </div>
      {series.map((s) => {
        const v = row[s.id] as number | null;
        const band = row[`${s.id}__band`] as [number, number] | undefined;
        return (
          <div key={s.id} className="flex items-center gap-2 text-ink-2">
            <span className="inline-block h-0.5 w-3 rounded" style={{ background: s.color }} aria-hidden />
            <span className="flex-1">{s.label}</span>
            <span className="tabular text-ink">
              {fmt(v, 2)} {unit}
            </span>
            {band && (
              <span className="tabular text-ink-3">
                ({fmt(band[0], 1)}–{fmt(band[1], 1)})
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function LineChartBands({
  title,
  subtitle,
  x,
  xLabel,
  xUnit = "",
  unit,
  series,
  refs = [],
  height = 260,
  syncId,
  actions,
  yDomain,
}: {
  title: string;
  subtitle?: string;
  x: number[];
  xLabel: string;
  xUnit?: string;
  unit: string;
  series: Series[];
  refs?: RefLine[];
  height?: number;
  syncId?: string;
  actions?: React.ReactNode;
  yDomain?: [number | "auto", number | "auto"];
}) {
  const data = useMemo(
    () =>
      x.map((xv, i) => {
        const row: Record<string, unknown> = { x: xv };
        for (const s of series) {
          row[s.id] = s.values[i];
          if (s.band && s.band.lo[i] != null && s.band.hi[i] != null) row[`${s.id}__band`] = [s.band.lo[i], s.band.hi[i]];
        }
        return row;
      }),
    [x, series],
  );
  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      actions={actions}
      legend={<Legend series={series} />}
      table={<DataTable x={x} xLabel={`${xLabel}${xUnit ? ` (${xUnit})` : ""}`} series={series} unit={unit} />}
    >
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} syncId={syncId} margin={{ top: 8, right: 12, bottom: 16, left: 0 }}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="x"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickLine={false}
              axisLine={{ stroke: "var(--axis)" }}
              tickFormatter={(v) => num(v)}
              label={{ value: `${xLabel}${xUnit ? ` (${xUnit})` : ""}`, position: "insideBottom", offset: -8 }}
            />
            <YAxis
              width={56}
              tickLine={false}
              axisLine={false}
              domain={yDomain ?? ["auto", "auto"]}
              tickFormatter={(v) => num(v)}
              label={{ value: unit, angle: -90, position: "insideLeft", offset: 12 }}
            />
            <Tooltip
              cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
              content={(p) => (
                <TooltipBox
                  active={p.active}
                  label={p.label as number}
                  payload={p.payload as unknown as { payload: Record<string, unknown> }[]}
                  xLabel={xLabel}
                  xUnit={xUnit}
                  unit={unit}
                  series={series}
                />
              )}
            />
            {series
              .filter((s) => s.band)
              .map((s) => (
                <Area
                  key={`${s.id}-band`}
                  dataKey={`${s.id}__band`}
                  stroke="none"
                  fill={s.color}
                  fillOpacity={0.16}
                  isAnimationActive={false}
                  connectNulls
                  activeDot={false}
                />
              ))}
            {series.map((s) => (
              <Line
                key={s.id}
                dataKey={s.id}
                stroke={s.color}
                strokeWidth={2}
                strokeDasharray={s.dashed ? "5 4" : undefined}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }}
                isAnimationActive={false}
                connectNulls
              />
            ))}
            {refs.map((r) => (
              <ReferenceLine
                key={`${r.kind}-${r.label}`}
                y={r.y}
                stroke={r.kind === "limit" ? "var(--critical)" : "var(--ink-3)"}
                strokeWidth={1}
                label={{ value: r.label, position: "insideTopRight", fill: "var(--ink-2)", fontSize: 11 }}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

// Sequential single-hue ramp (light → dark) for magnitude.
const RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"];

function rampColor(t: number) {
  const i = Math.max(0, Math.min(RAMP.length - 1, Math.round(t * (RAMP.length - 1))));
  return RAMP[i];
}

export function Heatmap({
  title,
  subtitle,
  xValues,
  yValues,
  xLabel,
  yLabel,
  values,
  unit,
  digits = 1,
  invert = false,
  annotate,
}: {
  title: string;
  subtitle?: string;
  xValues: number[];
  yValues: number[];
  xLabel: string;
  yLabel: string;
  values: (number | null)[][]; // [y][x]
  unit: string;
  digits?: number;
  invert?: boolean; // true when low values are "more" (e.g. probability of success shown as risk)
  annotate?: (xi: number, yi: number) => string | null;
}) {
  const [hover, setHover] = useState<{ xi: number; yi: number } | null>(null);
  const flat = values.flat().filter((v): v is number => v != null && Number.isFinite(v));
  const lo = Math.min(...flat);
  const hi = Math.max(...flat);
  const norm = (v: number) => (hi === lo ? 0.5 : (v - lo) / (hi - lo));
  const h = values[hover?.yi ?? 0]?.[hover?.xi ?? 0];
  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      table={
        <div className="max-h-72 overflow-auto rounded border border-line">
          <table className="w-full text-xs tabular">
            <thead className="bg-surface-2 text-ink-2">
              <tr>
                <th className="px-2 py-1 text-left">{yLabel} \ {xLabel}</th>
                {xValues.map((xv) => (
                  <th key={xv} className="px-2 py-1 text-right">{fmt(xv, 2)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {yValues.map((yv, yi) => (
                <tr key={yv} className="border-t border-line">
                  <td className="px-2 py-0.5">{fmt(yv, 2)}</td>
                  {xValues.map((_, xi) => (
                    <td key={xi} className="px-2 py-0.5 text-right">{fmt(values[yi][xi], digits)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      }
    >
      <div className="flex items-stretch gap-2">
        <div className="relative w-10 shrink-0 text-right text-[11px] text-ink-3 tabular" aria-hidden>
          {yValues.map((yv, yi) =>
            yi % Math.ceil(yValues.length / 8) ? null : (
              <span
                key={yi}
                className="absolute right-0 -translate-y-1/2"
                style={{ top: `${((yValues.length - 1 - yi + 0.5) / yValues.length) * 100}%` }}
              >
                {num(yv)}
              </span>
            ),
          )}
        </div>
        <div
          className="relative grid aspect-[2/1] min-w-0 flex-1 gap-px"
          style={{ gridTemplateColumns: `repeat(${xValues.length}, 1fr)` }}
          onMouseLeave={() => setHover(null)}
        >
          {yValues.map((_, ryi) => {
            const yi = yValues.length - 1 - ryi;
            return xValues.map((_, xi) => {
              const v = values[yi][xi];
              const t = v == null ? 0 : norm(v);
              return (
                <div
                  key={`${yi}-${xi}`}
                  onMouseEnter={() => setHover({ xi, yi })}
                  className="relative rounded-[2px]"
                  style={{
                    background: v == null ? "var(--surface-3)" : rampColor(invert ? 1 - t : t),
                    outline: hover?.xi === xi && hover?.yi === yi ? "2px solid var(--ink)" : undefined,
                    zIndex: hover?.xi === xi && hover?.yi === yi ? 1 : 0,
                  }}
                  aria-label={`${xLabel} ${xValues[xi]}, ${yLabel} ${yValues[yi]}: ${fmt(v, digits)} ${unit}`}
                />
              );
            });
          })}
        </div>
      </div>
      <div className="ml-12 mt-1 grid text-center text-[11px] text-ink-3 tabular" style={{ gridTemplateColumns: `repeat(${xValues.length}, 1fr)` }} aria-hidden>
        {xValues.map((xv, i) => (
          <span key={i} className={i % Math.ceil(xValues.length / 8) ? "invisible" : ""}>
            {num(xv)}
          </span>
        ))}
      </div>
      <div className="ml-12 mt-1 text-center text-xs text-ink-3">{xLabel}</div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-ink-2">
        <span>
          <span className="text-ink-3">{yLabel} (vertical)</span>
        </span>
        <div className="flex items-center gap-2">
          <span className="tabular">{fmt(invert ? hi : lo, digits)}</span>
          <span
            className="h-2 w-32 rounded"
            style={{ background: `linear-gradient(90deg, ${RAMP[0]}, ${RAMP[6]}, ${RAMP[12]})` }}
            aria-hidden
          />
          <span className="tabular">{fmt(invert ? lo : hi, digits)}</span>
          <span>{unit}</span>
        </div>
        <span className="tabular text-ink">
          {hover
            ? `${xLabel} ${fmt(xValues[hover.xi], 2)} · ${yLabel} ${fmt(yValues[hover.yi], 2)} → ${fmt(h, digits)} ${unit}${
                annotate?.(hover.xi, hover.yi) ? ` · ${annotate(hover.xi, hover.yi)}` : ""
              }`
            : "Hover a cell for its value"}
        </span>
      </div>
    </ChartFrame>
  );
}

export function BarList({
  title,
  subtitle,
  rows,
  unit,
  digits = 1,
  diverging = false,
}: {
  title: string;
  subtitle?: string;
  rows: { label: string; value: number; lo?: number | null; hi?: number | null; note?: string }[];
  unit: string;
  digits?: number;
  diverging?: boolean;
}) {
  const max = Math.max(...rows.map((r) => Math.abs(r.hi ?? r.value)), 1e-9);
  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      legend={
        diverging ? (
          <div className="flex gap-4 text-xs text-ink-2">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-sm" style={{ background: "var(--s1)" }} /> raises the result
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-sm" style={{ background: "var(--s8)" }} /> lowers the result
            </span>
          </div>
        ) : undefined
      }
      table={
        <table className="w-full text-xs tabular">
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-t border-line">
                <td className="py-1 pr-2">{r.label}</td>
                <td className="py-1 text-right">
                  {fmt(r.value, digits)} {unit}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <div className="space-y-1.5">
        {rows.map((r) => {
          const w = (Math.abs(r.value) / max) * 100;
          const color = diverging ? (r.value >= 0 ? "var(--s1)" : "var(--s8)") : "var(--s1)";
          return (
            <div key={r.label} className="grid grid-cols-[minmax(120px,38%)_1fr_auto] items-center gap-2 text-xs">
              <span className="truncate text-ink-2" title={r.note ?? r.label}>
                {r.label}
              </span>
              <div className="relative h-3.5 rounded-sm bg-surface-2">
                <div className="absolute inset-y-0 left-0 rounded-r-[4px]" style={{ width: `${w}%`, background: color }} />
                {r.lo != null && r.hi != null && (
                  <div
                    className="absolute top-1/2 h-px bg-ink"
                    style={{ left: `${(r.lo / max) * 100}%`, width: `${((r.hi - r.lo) / max) * 100}%` }}
                    aria-hidden
                  />
                )}
              </div>
              <span className="w-20 text-right tabular text-ink">
                {fmt(r.value, digits)} {unit}
              </span>
            </div>
          );
        })}
      </div>
    </ChartFrame>
  );
}
