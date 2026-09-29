"use client";

import { useMemo, useState } from "react";
import { BarList, LineChartBands, type Series } from "@/components/charts/Charts";
import { ComputePicker } from "@/components/project/ProjectBar";
import { Button, Card, ErrorNote, Field, Input, Note, Segmented, Select, Spinner, StatusBadge, useAsync } from "@/components/ui";
import { runJob } from "@/lib/api";
import { fmt, pct, SERIES } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Dist, Json, LimitResult, Status, VehicleDesign } from "@/lib/types";
import { type ScenarioResult, ScenarioResultView, strip } from "./ScenarioTab";

function parseList(s: string) {
  return s.split(/[,;\s]+/).map(Number).filter((x) => Number.isFinite(x));
}

export function WeatherStudy({ design, target, setTarget }: { design: VehicleDesign; target: string; setTarget: (t: string) => void }) {
  const { meta } = useSession();
  const builtins = meta?.scenarios ?? [];
  const [scenarioId, setScenarioId] = useState(builtins.find((b) => b.id === "mountain_pass")?.id ?? builtins[0]?.id ?? "");
  const [temps, setTemps] = useState("-10, 0, 10, 20, 30, 40, 45");
  const [alts, setAlts] = useState("0, 1500, 3000");
  const [surface, setSurface] = useState("dry");
  const [samples, setSamples] = useState(200);
  const [res, setRes] = useState<ScenarioResult | null>(null);
  const [status, setStatus] = useState("");
  const [detail, setDetail] = useState<number | null>(null);
  const act = useAsync();

  const temperatures = parseList(temps);
  const altitudes = parseList(alts);
  const run = () =>
    act.run(async () => {
      setDetail(null);
      const scenario = strip(builtins.find((b) => b.id === scenarioId)!);
      setRes(
        await runJob<ScenarioResult>(
          "weather_study",
          { vehicle: design, scenario, temperatures_c: temperatures, altitudes_m: altitudes, surface, samples },
          target,
          setStatus,
        ),
      );
    });

  const byAltitude = useMemo(() => {
    if (!res?.study) return [];
    const t = res.study.temperatures_c.length;
    return res.study.altitudes_m.map((a, i) => ({ altitude: a, points: res.points.slice(i * t, (i + 1) * t), offset: i * t }));
  }, [res]);

  const chart = (title: string, unit: string, pickValue: (p: ScenarioResult["points"][number]) => number | null, band?: (p: ScenarioResult["points"][number]) => Dist) => (
    <LineChartBands
      title={title}
      x={res!.study!.temperatures_c}
      xLabel="Ambient temperature"
      xUnit="°C"
      unit={unit}
      syncId="weather"
      series={byAltitude.map<Series>((g, i) => ({
        id: `a${g.altitude}`,
        label: `${fmt(g.altitude, 0)} m altitude`,
        color: SERIES[i % SERIES.length],
        values: g.points.map(pickValue),
        band: band && byAltitude.length === 1 ? { lo: g.points.map((p) => band(p).p05), hi: g.points.map((p) => band(p).p95) } : undefined,
      }))}
    />
  );

  return (
    <div className="space-y-4">
      <Card
        title="Weather study"
        subtitle="Run one scenario across a grid of ambient temperatures and altitudes. Every condition × every Monte Carlo sample is one batched ensemble: a natural GPU job."
        actions={<ComputePicker value={target} onChange={setTarget} />}
      >
        <div className="grid gap-3 md:grid-cols-[1.4fr_1.4fr_1fr_0.8fr_0.6fr]">
          <Field label="Scenario">
            <Select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
              {builtins.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </Select>
          </Field>
          <Field label="Ambient temperatures (°C)"><Input value={temps} onChange={(e) => setTemps(e.target.value)} /></Field>
          <Field label="Altitudes (m)"><Input value={alts} onChange={(e) => setAlts(e.target.value)} /></Field>
          <Field label="Surface">
            <Select value={surface} onChange={(e) => setSurface(e.target.value)}>
              <option value="dry">Dry</option>
              <option value="wet">Wet</option>
              <option value="snow">Snow</option>
            </Select>
          </Field>
          <Field label="Samples"><Input type="number" min={1} value={samples} onChange={(e) => setSamples(Number(e.target.value))} /></Field>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Button variant="primary" onClick={run} loading={act.busy} disabled={!temperatures.length || temperatures.length * Math.max(1, altitudes.length) > 60}>
            Run study
          </Button>
          <span className="text-xs text-ink-3">
            {temperatures.length * Math.max(1, altitudes.length)} conditions × {samples} samples
            {act.busy && status ? ` · ${status}` : ""}
          </span>
        </div>
      </Card>
      <ErrorNote error={act.error} />
      {act.busy && <Spinner label="Running every condition…" />}
      {res?.study && (
        <>
          <p className="text-xs text-ink-3">
            {res.points.length} conditions × {res.samples} samples in {fmt(res.study.seconds, 1)} s on {res.compute.device}.
          </p>
          <div className="grid gap-4 xl:grid-cols-2">
            {chart("Engine peak power", "kW", (p) => p.engine_peak_power_kw.nominal, (p) => p.engine_peak_power_kw)}
            {chart("Peak coolant temperature", "°C", (p) => p.max_coolant_c.nominal, (p) => p.max_coolant_c)}
            {chart("Chance of overheating", "%", (p) => p.coolant_limit.probability * 100)}
            {chart("Peak front disc temperature", "°C", (p) => p.max_disc_c.nominal, (p) => p.max_disc_c)}
          </div>
          <Card title="Every condition">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm tabular">
                <thead className="text-left text-xs text-ink-2">
                  <tr>
                    <th className="py-1 font-medium">Ambient</th>
                    <th className="py-1 font-medium">Altitude</th>
                    <th className="py-1 text-right font-medium">Engine power</th>
                    <th className="py-1 text-right font-medium">Peak coolant</th>
                    <th className="py-1 text-right font-medium">P(overheat)</th>
                    <th className="py-1 text-right font-medium">Peak disc</th>
                    <th className="py-1 text-right font-medium">P(fade)</th>
                    <th className="py-1 text-right font-medium">Can’t hold speed</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {res.points.map((p, i) => (
                    <tr key={i} className="border-t border-line">
                      <td className="py-1">{fmt(p.weather.ambient_temp_c, 0)} °C</td>
                      <td className="py-1">{fmt(p.weather.altitude_m, 0)} m</td>
                      <td className="py-1 text-right">{fmt(p.engine_peak_power_kw.nominal, 0)} kW</td>
                      <td className="py-1 text-right">{fmt(p.max_coolant_c.nominal, 0)} °C</td>
                      <td className="py-1 text-right">{pct(p.coolant_limit.probability)}</td>
                      <td className="py-1 text-right">{fmt(p.max_disc_c.nominal, 0)} °C</td>
                      <td className="py-1 text-right">{pct(p.disc_limit.probability)}</td>
                      <td className="py-1 text-right">{pct(p.speed_deficit.probability)}</td>
                      <td className="py-1 text-right">
                        {res.trace && <Button size="sm" variant="ghost" onClick={() => setDetail(i)}>Details</Button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          {detail !== null && res.trace && (
            <Card title={`Details: ${fmt(res.points[detail].weather.ambient_temp_c, 0)} °C at ${fmt(res.points[detail].weather.altitude_m, 0)} m`}>
              <ScenarioResultView res={res} pointIndex={detail} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}

interface MaterialRow {
  material_id: string;
  name: string;
  custom: boolean;
  sources: string[];
  rod_mass_g?: Dist;
  disc_mass_kg?: number;
  max_disc_c?: Dist;
  disc_limit?: { probability: number };
  homologous_temp_p95?: number;
  warning?: string;
  checks?: LimitResult[];
  error?: string;
}

export function MaterialStudy({ design, target, setTarget }: { design: VehicleDesign; target: string; setTarget: (t: string) => void }) {
  const { meta, materials } = useSession();
  const [component, setComponent] = useState<"conrod" | "brake_disc">("brake_disc");
  const [chosen, setChosen] = useState<string[]>([]);
  const [scenarioId, setScenarioId] = useState("track_day");
  const [res, setRes] = useState<{ rows: MaterialRow[]; notes: string[] } | null>(null);
  const act = useAsync();
  const engine = Object.values(design.components).find((c) => c.type === "engine_turbo_si")?.params as Json | undefined;

  const eligible = materials.filter((m) =>
    component === "conrod"
      ? ["density", "youngs_modulus", "yield_strength", "ultimate_strength"].every((k) => k in m.properties)
      : "specific_heat" in m.properties && "density" in m.properties,
  );
  const ids = chosen.length ? chosen.filter((c) => eligible.some((m) => m.id === c)) : eligible.map((m) => m.id);

  const run = () =>
    act.run(async () => {
      const scenario = meta?.scenarios.find((s) => s.id === scenarioId);
      setRes(
        await runJob("material_study", {
          target: component,
          material_ids: ids,
          engine: component === "conrod" ? engine : undefined,
          vehicle: component === "brake_disc" ? design : undefined,
          scenario: component === "brake_disc" && scenario ? strip(scenario) : undefined,
          samples: 100,
        }, target),
      );
    });

  const worst = (checks?: LimitResult[]): Status =>
    (checks ?? []).reduce<Status>((w, c) => (["no_data", "ok", "warning", "critical", "failure"].indexOf(c.status) > ["no_data", "ok", "warning", "critical", "failure"].indexOf(w) ? c.status : w), "no_data");

  return (
    <div className="space-y-4">
      <Card
        title="What if I use a different material?"
        subtitle="Same geometry, different material: compare mass, temperatures and structural safety. Materials are only as good as their data; check the source badges in the material library."
        actions={<ComputePicker value={target} onChange={setTarget} />}
      >
        <div className="flex flex-wrap items-end gap-3">
          <Segmented options={[{ id: "brake_disc", label: "Brake discs" }, { id: "conrod", label: "Connecting rods" }]} value={component} onChange={(v) => { setComponent(v); setChosen([]); setRes(null); }} />
          {component === "brake_disc" && (
            <Field label="Under scenario">
              <Select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)} className="w-64">
                {(meta?.scenarios ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </Field>
          )}
          <Button variant="primary" onClick={run} loading={act.busy} disabled={!ids.length || (component === "conrod" && !engine)}>Compare materials</Button>
        </div>
        <div className="mt-3 flex flex-wrap gap-3">
          {eligible.map((m) => (
            <label key={m.id} className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={ids.includes(m.id)} onChange={(e) => setChosen(e.target.checked ? [...new Set([...ids, m.id])] : ids.filter((x) => x !== m.id))} />
              {m.name} <span className="text-xs text-ink-3">{m.condition}</span>
            </label>
          ))}
        </div>
      </Card>
      <ErrorNote error={act.error} />
      {act.busy && <Spinner label="Evaluating each material…" />}
      {res && (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            {component === "brake_disc" ? (
              <>
                <BarList title="Peak disc temperature" subtitle="Nominal, with the 90 % range as a line" unit="°C" digits={0} rows={res.rows.filter((r) => r.max_disc_c).map((r) => ({ label: r.name, value: r.max_disc_c!.nominal, lo: r.max_disc_c!.p05, hi: r.max_disc_c!.p95 }))} />
                <BarList title="Disc mass (each, same geometry)" unit="kg" digits={2} rows={res.rows.filter((r) => r.disc_mass_kg).map((r) => ({ label: r.name, value: r.disc_mass_kg! }))} />
              </>
            ) : (
              <>
                <BarList title="Rod mass" unit="g" digits={0} rows={res.rows.filter((r) => r.rod_mass_g).map((r) => ({ label: r.name, value: r.rod_mass_g!.nominal }))} />
                <BarList title="Lowest structural safety factor" subtitle="Minimum of buckling, tensile yield and fatigue (when fatigue data exists)" unit="" digits={2} rows={res.rows.filter((r) => r.checks?.length).map((r) => ({ label: r.name, value: Math.min(...r.checks!.map((c) => c.sf_nominal ?? Infinity)) }))} />
              </>
            )}
          </div>
          <Card title="Verdict per material">
            <ul className="divide-y divide-[var(--border)]">
              {res.rows.map((r) => (
                <li key={r.material_id} className="flex flex-wrap items-start justify-between gap-2 py-2 text-sm">
                  <div>
                    <div className="font-medium">{r.name}{r.custom && <span className="ml-1 text-xs text-ink-3">(custom)</span>}</div>
                    <div className="text-xs text-ink-3">Data: {r.sources.join(", ")}</div>
                    {r.warning && <div className="mt-1"><Note tone="warning">{r.warning}</Note></div>}
                    {r.error && <div className="text-xs text-[var(--critical)]">{r.error}</div>}
                    {r.homologous_temp_p95 != null && <div className="text-xs text-ink-3">Homologous temperature (95 %): {fmt(r.homologous_temp_p95, 2)}</div>}
                  </div>
                  <StatusBadge status={r.warning?.includes("melting") ? "failure" : worst(r.checks)} />
                </li>
              ))}
            </ul>
          </Card>
          {res.notes.map((n) => <p key={n} className="text-xs text-ink-3">{n}</p>)}
        </>
      )}
    </div>
  );
}
