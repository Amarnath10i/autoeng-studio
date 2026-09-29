"use client";

import { LineChartBands, type Series } from "@/components/charts/Charts";
import { LimitsTable } from "@/components/project/Panels";
import { Card, Note, Stat } from "@/components/ui";
import { fmt, kwToHp, pct, SERIES } from "@/lib/format";
import type { Dist, EngineResult, LimitResult, VehicleDesign } from "@/lib/types";

export interface VehicleResult {
  architecture: { driveline_chain: string[]; planned_components: string[]; models: Record<string, boolean> };
  engine_component: string;
  engine: EngineResult;
  evaluated: { component: string; models: string[] }[];
  not_evaluated: { component: string; type: string; reason: string }[];
  performance: {
    accel_0_100_s: Dist;
    quarter_mile_s: Dist;
    trap_speed_kmh: Dist;
    top_speed_kmh: Dist;
    top_speed_gear: number;
    traction_limited_until_kmh: Dist;
    max_axle_torque_nm: Dist;
    gear_speeds_at_redline_kmh: number[];
    trace: { t: number[]; v: number[]; gear: number[]; a: number[]; rpm: number[] };
    force_diagram: { speed_kmh: number[]; gears: (number | null)[][]; resistance: number[] };
  } | null;
  performance_note?: string;
  limits: LimitResult[];
  targets: { id: string; target: number; better: string; nominal: number; probability_met: number }[];
  trust: EngineResult["trust"];
  error?: string;
}

const TARGET_LABEL: Record<string, string> = { accel_0_100_s: "0–100 km/h", top_speed_kmh: "Top speed", quarter_mile_s: "Quarter mile" };

export function PerformanceTab({ result, design }: { result: VehicleResult; design: VehicleDesign }) {
  const p = result.performance;
  const name = (id: string) => design.components[id]?.name || id;
  const e = result.engine.summary;
  const range = (d: Dist, digits = 1) => `90 % range ${fmt(d.p05, digits)}–${fmt(d.p95, digits)}`;

  return (
    <div className="space-y-4">
      {result.not_evaluated.length > 0 && (
        <Note>
          Not evaluated (no physics model yet): {result.not_evaluated.map((n) => name(n.component)).join(", ")}.
        </Note>
      )}
      {result.performance_note && <Note tone="warning">{result.performance_note}</Note>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Engine peak power" value={fmt(e.peak_power.nominal, 0)} unit="kW" sub={`${fmt(kwToHp(e.peak_power.nominal), 0)} hp`} />
        <Stat label="Engine peak torque" value={fmt(e.peak_torque.nominal, 0)} unit="N·m" sub={`at ${fmt(e.peak_torque.rpm, 0)} rpm`} />
        {p && (
          <>
            <Stat label="0–100 km/h" value={fmt(p.accel_0_100_s.nominal, 1)} unit="s" sub={range(p.accel_0_100_s)} />
            <Stat label="Quarter mile" value={fmt(p.quarter_mile_s.nominal, 1)} unit="s" sub={`trap ${fmt(p.trap_speed_kmh.nominal, 0)} km/h`} />
            <Stat label="Top speed" value={fmt(p.top_speed_kmh.nominal, 0)} unit="km/h" sub={`in gear ${p.top_speed_gear} · ${range(p.top_speed_kmh, 0)}`} />
            <Stat label="Traction-limited to" value={fmt(p.traction_limited_until_kmh.nominal, 0)} unit="km/h" sub="wheelspin risk below this speed" />
          </>
        )}
      </div>
      {result.targets.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-3">
          {result.targets.map((t) => (
            <Stat
              key={t.id}
              label={`Target: ${TARGET_LABEL[t.id] ?? t.id} ${t.better === "lower" ? "≤" : "≥"} ${fmt(t.target, 1)}`}
              value={pct(t.probability_met)}
              sub={`chance to meet · nominal ${fmt(t.nominal, 1)}`}
              status={t.probability_met >= 0.9 ? "ok" : t.probability_met >= 0.5 ? "warning" : "critical"}
            />
          ))}
        </div>
      )}
      {p && (
        <div className="grid gap-4 xl:grid-cols-2">
          <LineChartBands
            title="Full-throttle acceleration: speed"
            x={p.trace.t}
            xLabel="Time"
            xUnit="s"
            unit="km/h"
            syncId="accel"
            series={[{ id: "v", label: "Speed", color: "var(--s1)", values: p.trace.v }]}
            refs={[{ y: 100, label: "100 km/h", kind: "target" }]}
          />
          <LineChartBands
            title="Engine speed during the run"
            subtitle="Upshift points appear as drops"
            x={p.trace.t}
            xLabel="Time"
            xUnit="s"
            unit="rpm"
            syncId="accel"
            series={[{ id: "rpm", label: "Engine speed", color: "var(--s2)", values: p.trace.rpm }]}
          />
          <LineChartBands
            title="Traction diagram"
            subtitle="Wheel force available in each gear vs. road resistance (flat road, no wind)"
            x={p.force_diagram.speed_kmh}
            xLabel="Speed"
            xUnit="km/h"
            unit="N"
            series={[
              ...p.force_diagram.gears.map<Series>((g, i) => ({ id: `g${i}`, label: `Gear ${i + 1}`, color: SERIES[i % SERIES.length], values: g })),
              { id: "res", label: "Resistance", color: "var(--ink-2)", values: p.force_diagram.resistance, dashed: true },
            ]}
            height={300}
          />
          <Card title="Gearing">
            <table className="w-full text-sm tabular">
              <thead className="text-left text-xs text-ink-2">
                <tr><th className="py-1 font-medium">Gear</th><th className="py-1 text-right font-medium">Speed at redline</th></tr>
              </thead>
              <tbody>
                {p.gear_speeds_at_redline_kmh.map((s, i) => (
                  <tr key={i} className="border-t border-line"><td className="py-1">{i + 1}</td><td className="py-1 text-right">{fmt(s, 0)} km/h</td></tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-ink-3">Max axle torque during the run: {fmt(p.max_axle_torque_nm.nominal, 0)} N·m (95 %: {fmt(p.max_axle_torque_nm.p95, 0)}).</p>
          </Card>
        </div>
      )}
      <Card title="Driveline and engine limits">
        <LimitsTable limits={[...result.limits, ...result.engine.limits.map((l) => ({ ...l, component: `${result.engine_component}:${l.component}` }))]} componentName={(id) => (id.includes(":") ? `${name(id.split(":")[0])} · ${id.split(":")[1].replace(/_/g, " ")}` : name(id))} />
      </Card>
    </div>
  );
}
