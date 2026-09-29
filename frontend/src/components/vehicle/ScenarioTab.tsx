"use client";

import { Plus, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { LineChartBands, type RefLine, type Series } from "@/components/charts/Charts";
import { LimitsTable } from "@/components/project/Panels";
import { ComputePicker } from "@/components/project/ProjectBar";
import { Button, Card, ErrorNote, Field, Input, Note, Select, Spinner, Stat, useAsync } from "@/components/ui";
import { runJob } from "@/lib/api";
import { fmt, pct } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Dist, LimitResult, Scenario, VehicleDesign } from "@/lib/types";

export interface EventStat {
  probability: number;
  median_time_s: number | null;
  earliest_time_s: number | null;
  duration_s: number;
}

export interface ScenarioPoint {
  weather: Scenario["weather"] & { pressure_kpa: number };
  engine_peak_power_kw: Dist;
  max_coolant_c: Dist;
  max_disc_c: Dist;
  max_engine_torque_nm: Dist;
  coolant_limit: EventStat;
  disc_limit: EventStat;
  speed_deficit: EventStat;
  fuel_energy_mj: Dist;
  brake_energy_mj: Dist;
  distance_km: Dist;
  checks: LimitResult[];
}

export interface ScenarioResult {
  scenario: Scenario & { duration_s: number };
  samples: number;
  points: ScenarioPoint[];
  trace: {
    t: number[];
    target_kmh: (number | null)[];
    nominal: Record<string, number[][]>;
    bands: Record<string, { p05: number[][]; p50: number[][]; p95: number[][] }> | null;
  } | null;
  limits: { max_coolant_temp_c: number; max_disc_temp_c: number; gearbox_torque_nm: number; clutch_torque_nm: number };
  compute: { backend: string; device: string };
  trust: { models: { id: string; version: string; fidelity_level: number; name: string }[]; assumptions: string[]; disclaimer: string };
  study?: { temperatures_c: number[]; altitudes_m: number[]; seconds: number };
}

export const TRACE_SERIES: Record<string, { label: string; unit: string }> = {
  v: { label: "Vehicle speed", unit: "km/h" },
  coolant: { label: "Coolant temperature", unit: "°C" },
  disc: { label: "Front brake disc temperature", unit: "°C" },
  power: { label: "Engine power", unit: "kW" },
  torque: { label: "Engine torque", unit: "N·m" },
  rpm: { label: "Engine speed", unit: "rpm" },
  gear: { label: "Gear", unit: "gear" },
  load: { label: "Engine load", unit: "share" },
  brake_power: { label: "Braking power", unit: "kW" },
  heat_to_coolant: { label: "Heat into coolant", unit: "kW" },
  heat_rejected: { label: "Heat rejected by radiator", unit: "kW" },
};

function eventText(e: EventStat) {
  if (e.probability === 0) return "Not reached";
  return `${pct(e.probability)} chance · typically after ${fmt(e.median_time_s, 0)} s`;
}

function eventStatus(e: EventStat) {
  return e.probability === 0 ? "ok" : e.probability < 0.05 ? "warning" : e.probability < 0.5 ? "critical" : "failure";
}

export function ScenarioEditor({ scenario, onChange }: { scenario: Scenario; onChange: (s: Scenario) => void }) {
  const w = scenario.weather;
  const setW = (patch: Partial<Scenario["weather"]>) => onChange({ ...scenario, weather: { ...w, ...patch } });
  const setSeg = (i: number, patch: Partial<Scenario["segments"][number]>) =>
    onChange({ ...scenario, segments: scenario.segments.map((s, j) => (i === j ? { ...s, ...patch } : s)) });
  const duration = scenario.segments.reduce((a, s) => a + s.duration_s, 0) * scenario.repeats;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Field label="Ambient temperature (°C)"><Input type="number" value={w.ambient_temp_c} onChange={(e) => setW({ ambient_temp_c: Number(e.target.value) })} /></Field>
        <Field label="Altitude (m)"><Input type="number" value={w.altitude_m} onChange={(e) => setW({ altitude_m: Number(e.target.value) })} /></Field>
        <Field label="Headwind (km/h)"><Input type="number" value={w.headwind_kmh} onChange={(e) => setW({ headwind_kmh: Number(e.target.value) })} /></Field>
        <Field label="Road surface">
          <Select value={w.surface} onChange={(e) => setW({ surface: e.target.value as "dry" | "wet" | "snow" })}>
            <option value="dry">Dry</option>
            <option value="wet">Wet</option>
            <option value="snow">Snow</option>
          </Select>
        </Field>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-xs text-ink-2">
            <tr>
              <th className="py-1 font-medium">Segment</th>
              <th className="py-1 font-medium">Duration (s)</th>
              <th className="py-1 font-medium">Speed (km/h)</th>
              <th className="py-1 font-medium">Rate (g)</th>
              <th className="py-1 font-medium">Grade (%)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {scenario.segments.map((s, i) => (
              <tr key={i} className="border-t border-line">
                <td className="py-1 pr-2">
                  <Select value={s.mode} onChange={(e) => setSeg(i, { mode: e.target.value as typeof s.mode })}>
                    <option value="cruise">Cruise at speed</option>
                    <option value="full_throttle">Full throttle</option>
                    <option value="accelerate">Accelerate to speed</option>
                    <option value="brake">Brake to speed</option>
                    <option value="idle">Stop / idle</option>
                  </Select>
                </td>
                <td className="py-1 pr-2"><Input type="number" min={0.1} value={s.duration_s} onChange={(e) => setSeg(i, { duration_s: Number(e.target.value) })} /></td>
                <td className="py-1 pr-2"><Input type="number" min={0} value={s.speed_kmh} disabled={s.mode === "full_throttle" || s.mode === "idle"} onChange={(e) => setSeg(i, { speed_kmh: Number(e.target.value) })} /></td>
                <td className="py-1 pr-2"><Input type="number" min={0.01} step={0.05} value={s.rate_g} disabled={!["brake", "accelerate"].includes(s.mode)} onChange={(e) => setSeg(i, { rate_g: Number(e.target.value) })} /></td>
                <td className="py-1 pr-2"><Input type="number" value={s.grade_pct} onChange={(e) => setSeg(i, { grade_pct: Number(e.target.value) })} /></td>
                <td className="py-1">
                  <button type="button" onClick={() => onChange({ ...scenario, segments: scenario.segments.filter((_, j) => j !== i) })} disabled={scenario.segments.length === 1} className="text-ink-3 hover:text-[var(--critical)] disabled:opacity-30" aria-label="Remove segment">
                    <Trash2 className="size-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Button size="sm" onClick={() => onChange({ ...scenario, segments: [...scenario.segments, { mode: "cruise", duration_s: 60, speed_kmh: 100, rate_g: 0.3, grade_pct: 0 }] })}>
          <Plus className="size-3.5" /> Add segment
        </Button>
        <Field label="Repeat"><Input type="number" min={1} max={200} value={scenario.repeats} onChange={(e) => onChange({ ...scenario, repeats: Math.max(1, Number(e.target.value)) })} className="w-20" /></Field>
        <Field label="Start speed (km/h)"><Input type="number" min={0} value={scenario.initial_speed_kmh} onChange={(e) => onChange({ ...scenario, initial_speed_kmh: Number(e.target.value) })} className="w-24" /></Field>
        <Field label="Time step (s)"><Input type="number" min={0.02} max={1} step={0.05} value={scenario.dt_s} onChange={(e) => onChange({ ...scenario, dt_s: Number(e.target.value) })} className="w-24" /></Field>
        <label className="mb-2 flex items-center gap-1.5 text-xs text-ink-2">
          <input type="checkbox" checked={scenario.cold_start} onChange={(e) => onChange({ ...scenario, cold_start: e.target.checked })} /> Cold start
        </label>
        <span className="mb-2 text-xs text-ink-3">Total {fmt(duration / 60, 1)} min · {Math.round(duration / scenario.dt_s).toLocaleString()} steps</span>
      </div>
    </div>
  );
}

export function ScenarioResultView({ res, pointIndex = 0 }: { res: ScenarioResult; pointIndex?: number }) {
  const p = res.points[pointIndex];
  const [panels, setPanels] = useState<string[]>(["v", "coolant", "disc", "power"]);
  const trace = res.trace;
  const limitsFor: Record<string, RefLine[]> = {
    coolant: [{ y: res.limits.max_coolant_temp_c, label: "Coolant limit", kind: "limit" }],
    disc: [{ y: res.limits.max_disc_temp_c, label: "Disc fade limit", kind: "limit" }],
    torque: [{ y: res.limits.gearbox_torque_nm, label: "Gearbox rating", kind: "limit" }],
  };
  const t = useMemo(() => trace?.t ?? [], [trace]);
  const seriesFor = (key: string): Series[] => {
    if (!trace) return [];
    const out: Series[] = [];
    const band = trace.bands?.[key];
    out.push({
      id: key,
      label: `${TRACE_SERIES[key]?.label ?? key}${band ? " (nominal)" : ""}`,
      color: "var(--s1)",
      values: trace.nominal[key][pointIndex],
      band: band ? { lo: band.p05[pointIndex], hi: band.p95[pointIndex] } : undefined,
    });
    if (key === "v") out.push({ id: "target", label: "Requested speed", color: "var(--ink-2)", values: trace.target_kmh, dashed: true });
    return out;
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Overheating (coolant limit)" value={p.coolant_limit.probability === 0 ? "No" : pct(p.coolant_limit.probability)} sub={eventText(p.coolant_limit)} status={eventStatus(p.coolant_limit)} />
        <Stat label="Brake fade (disc limit)" value={p.disc_limit.probability === 0 ? "No" : pct(p.disc_limit.probability)} sub={eventText(p.disc_limit)} status={eventStatus(p.disc_limit)} />
        <Stat label="Cannot hold the requested speed" value={p.speed_deficit.probability === 0 ? "No" : pct(p.speed_deficit.probability)} sub={eventText(p.speed_deficit)} status={eventStatus(p.speed_deficit)} />
        <Stat label="Peak coolant temperature" value={fmt(p.max_coolant_c.nominal, 0)} unit="°C" sub={`90 % range ${fmt(p.max_coolant_c.p05, 0)}–${fmt(p.max_coolant_c.p95, 0)}`} />
        <Stat label="Peak disc temperature" value={fmt(p.max_disc_c.nominal, 0)} unit="°C" sub={`90 % range ${fmt(p.max_disc_c.p05, 0)}–${fmt(p.max_disc_c.p95, 0)}`} />
        <Stat label="Engine power at these conditions" value={fmt(p.engine_peak_power_kw.nominal, 0)} unit="kW" sub={`${fmt(p.distance_km.p50, 1)} km · fuel ${fmt(p.fuel_energy_mj.p50, 0)} MJ`} />
      </div>
      {trace ? (
        <>
          <div className="flex flex-wrap items-center gap-2 border border-line bg-surface px-3 py-2">
            <span className="text-xs font-medium text-ink-2">Charts</span>
            {panels.map((k) => (
              <span key={k} className="inline-flex items-center gap-1 rounded bg-surface-2 px-2 py-0.5 text-xs">
                {TRACE_SERIES[k]?.label}
                <button type="button" onClick={() => setPanels(panels.filter((x) => x !== k))} aria-label={`Remove ${k}`}><X className="size-3" /></button>
              </span>
            ))}
            <Select value="" onChange={(e) => e.target.value && setPanels([...panels, e.target.value])} className="h-7 w-56 text-xs" aria-label="Add a chart">
              <option value="">Add a quantity vs time…</option>
              {Object.entries(TRACE_SERIES).filter(([k]) => !panels.includes(k)).map(([k, s]) => (
                <option key={k} value={k}>{s.label} ({s.unit})</option>
              ))}
            </Select>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {panels.map((k) => (
              <LineChartBands
                key={k}
                title={TRACE_SERIES[k]?.label ?? k}
                x={t}
                xLabel="Time"
                xUnit="s"
                unit={TRACE_SERIES[k]?.unit ?? ""}
                series={seriesFor(k)}
                refs={limitsFor[k]}
                syncId="scenario"
                height={220}
              />
            ))}
          </div>
        </>
      ) : (
        <Note>Time traces are omitted for large weather studies; see the per-condition results.</Note>
      )}
      <Card title="Checks over the whole scenario">
        <LimitsTable limits={p.checks} componentName={(id) => id} />
      </Card>
      <p className="text-xs text-ink-3">
        {res.samples} Monte Carlo samples · computed on {res.compute.device}. {res.trust.disclaimer}
      </p>
    </div>
  );
}

export function ScenarioTab({ design, target, setTarget }: { design: VehicleDesign; target: string; setTarget: (t: string) => void }) {
  const { meta } = useSession();
  const builtins = meta?.scenarios ?? [];
  const [scenarioId, setScenarioId] = useState(builtins[0]?.id ?? "");
  const [scenario, setScenario] = useState<Scenario | null>(builtins[0] ? strip(builtins[0]) : null);
  const [samples, setSamples] = useState(100);
  const [res, setRes] = useState<ScenarioResult | null>(null);
  const [status, setStatus] = useState("");
  const act = useAsync();

  const pick = (id: string) => {
    setScenarioId(id);
    const s = builtins.find((b) => b.id === id);
    if (s) setScenario(strip(s));
  };

  const run = () => act.run(async () => setRes(await runJob<ScenarioResult>("scenario", { vehicle: design, scenario, samples }, target, setStatus)));

  return (
    <div className="space-y-4">
      <Card
        title="Drive a scenario through time"
        subtitle="The vehicle follows the schedule second by second: speed, gears, engine load, coolant and brake temperatures, with uncertainty. Large ensembles run on a GPU."
        actions={<ComputePicker value={target} onChange={setTarget} />}
      >
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <Field label="Start from">
            <Select value={scenarioId} onChange={(e) => pick(e.target.value)} className="w-72">
              {builtins.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </Select>
          </Field>
          <Field label="Samples"><Input type="number" min={1} max={2000} value={samples} onChange={(e) => setSamples(Number(e.target.value))} className="w-24" /></Field>
          <Button variant="primary" onClick={run} loading={act.busy} disabled={!scenario}>Run scenario</Button>
          {act.busy && <span className="mb-2 text-xs text-ink-3">{status}</span>}
        </div>
        {scenario && (
          <>
            <p className="mb-2 text-xs text-ink-2">{builtins.find((b) => b.id === scenarioId)?.description}</p>
            <ScenarioEditor scenario={scenario} onChange={setScenario} />
          </>
        )}
      </Card>
      <ErrorNote error={act.error} />
      {act.busy && <Spinner label="Driving the scenario…" />}
      {res && <ScenarioResultView res={res} />}
    </div>
  );
}

export function strip(s: Scenario): Scenario {
  const { id: _id, duration_s: _d, ...rest } = s as Scenario & { id?: string };
  void _id;
  void _d;
  return structuredClone(rest);
}
