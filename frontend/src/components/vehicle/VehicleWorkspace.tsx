"use client";

import { Activity, CarFront, CloudSun, Compass, FlaskConical, GitBranch, Network, Play, Timer, Wind } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { HistoryPanel, TrustPanel } from "@/components/project/Panels";
import { Container, type FigureItem, StickyTabs } from "@/components/layout";
import { ComputePicker, ProjectBar } from "@/components/project/ProjectBar";
import type { ProjectState } from "@/components/project/useProject";
import { Button, Empty, ErrorNote, Field, Input, Spinner, Tabs, useAsync } from "@/components/ui";
import { api, runJob } from "@/lib/api";
import { fmt, kwToHp } from "@/lib/format";
import type { Status, VehicleDesign } from "@/lib/types";
import { ArchitectureTab } from "./Architecture";
import { BodyDesigner } from "./BodyDesigner";
import { PerformanceTab, type VehicleResult } from "./PerformanceTab";
import { ScenarioTab } from "./ScenarioTab";
import { MaterialStudy, WeatherStudy } from "./StudiesTab";
import { WindTunnel } from "./WindTunnel";

type Tab = "architecture" | "body" | "aero" | "performance" | "scenarios" | "weather" | "materials" | "history" | "trust";

const WORST = ["no_data", "ok", "warning", "critical", "failure"];

export function VehicleWorkspace({ state }: { state: ProjectState }) {
  const design = state.design as VehicleDesign;
  const [tab, setTab] = useState<Tab>("architecture");
  const [result, setResult] = useState<VehicleResult | null>(null);
  const [target, setTarget] = useState("server");
  const [samples, setSamples] = useState(150);
  const sim = useAsync();

  const simulate = () =>
    sim.run(async () => {
      const r =
        target === "server" && samples <= 500
          ? await api<VehicleResult>("/api/v1/vehicle/simulate", { method: "POST", json: { design, samples } })
          : await runJob<VehicleResult>("vehicle", { design, samples }, target);
      if (r.error) throw new Error(r.error);
      setResult(r);
    });

  useEffect(() => {
    if (!result) simulate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.head?.id]);

  // Status per vehicle component: driveline limits, plus the engine's worst internal status.
  const status = useMemo(() => {
    const s: Record<string, Status> = {};
    if (!result) return s;
    for (const l of result.limits) if (WORST.indexOf(l.status) > WORST.indexOf(s[l.component] ?? "no_data")) s[l.component] = l.status;
    const eng = Object.values(result.engine.component_status).reduce<Status>(
      (w, x) => (WORST.indexOf(x) > WORST.indexOf(w) ? x : w),
      "no_data",
    );
    s[result.engine_component] = eng;
    return s;
  }, [result]);

  const setTargets = (key: string, v: string) => {
    const t = { ...design.targets };
    if (v === "") delete t[key];
    else t[key] = Number(v);
    state.edit({ ...design, targets: t });
  };

  const perf = result?.performance;
  const bodyParams = Object.values(design.components).find((c) => c.type === "body")?.params as
    | Record<string, { value: number }>
    | null
    | undefined;
  const figures: FigureItem[] = result
    ? [
        {
          label: "0–100 km/h",
          value: perf ? fmt(perf.accel_0_100_s.nominal, 1) : "–",
          unit: "s",
          sub: perf ? `90 % range ${fmt(perf.accel_0_100_s.p05, 1)}–${fmt(perf.accel_0_100_s.p95, 1)} s` : "Complete the driveline",
        },
        { label: "Top speed", value: perf ? fmt(perf.top_speed_kmh.nominal, 0) : "–", unit: "km/h", sub: perf ? `in gear ${perf.top_speed_gear}` : undefined },
        {
          label: "Power",
          value: fmt(result.engine.summary.peak_power.nominal, 0),
          unit: "kW",
          sub: `${fmt(kwToHp(result.engine.summary.peak_power.nominal), 0)} hp · ${fmt(result.engine.summary.peak_torque.nominal, 0)} N·m`,
        },
        {
          label: "Mass",
          value: bodyParams?.mass ? fmt(bodyParams.mass.value, 0) : "–",
          unit: "kg",
          sub: bodyParams?.mass ? `${fmt((result.engine.summary.peak_power.nominal / bodyParams.mass.value) * 1000, 0)} W/kg` : undefined,
        },
      ]
    : ["0–100 km/h", "Top speed", "Power", "Mass"].map((label) => ({
        label,
        value: "—",
        sub: sim.busy ? "Simulating…" : "Run a simulation",
      }));

  return (
    <div>
      <ProjectBar state={state} figures={figures}>
        <label className="inline-flex items-center gap-2" title="Monte Carlo samples for uncertainty">
          <span className="eyebrow">Samples</span>
          <Input type="number" min={1} max={2000} value={samples} onChange={(e) => setSamples(Number(e.target.value))} className="h-10 w-24" />
        </label>
        <ComputePicker value={target} onChange={setTarget} />
        <Button variant="primary" size="lg" onClick={simulate} loading={sim.busy}>
          <Play className="size-3.5" aria-hidden /> Run simulation
        </Button>
      </ProjectBar>
      <StickyTabs>
        <Tabs
          tabs={[
            { id: "architecture", label: "Architecture", icon: Network },
            { id: "body", label: "Body design", icon: CarFront },
            { id: "aero", label: "Wind tunnel (GPU)", icon: Wind },
            { id: "performance", label: "Performance", icon: Activity },
            { id: "scenarios", label: "Scenarios", icon: Timer },
            { id: "weather", label: "Weather study (GPU)", icon: CloudSun },
            { id: "materials", label: "Materials", icon: FlaskConical },
            { id: "history", label: "History", icon: GitBranch },
            { id: "trust", label: "Trust", icon: Compass },
          ]}
          value={tab}
          onChange={setTab}
        />
      </StickyTabs>
      <Container className="space-y-6 py-10">
      <ErrorNote error={sim.error} onClose={() => sim.setError(null)} />
      {tab === "architecture" && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-end gap-6 border border-line bg-surface px-5 py-4">
            <div className="mr-4">
              <div className="eyebrow">Requirements</div>
              <div className="display mt-1 text-[15px]">Vehicle targets</div>
            </div>
            <Field label="0–100 km/h ≤ (s)">
              <Input type="number" value={design.targets.accel_0_100_s ?? ""} onChange={(e) => setTargets("accel_0_100_s", e.target.value)} className="w-28" />
            </Field>
            <Field label="Top speed ≥ (km/h)">
              <Input type="number" value={design.targets.top_speed_kmh ?? ""} onChange={(e) => setTargets("top_speed_kmh", e.target.value)} className="w-28" />
            </Field>
            <Field label="Quarter mile ≤ (s)">
              <Input type="number" value={design.targets.quarter_mile_s ?? ""} onChange={(e) => setTargets("quarter_mile_s", e.target.value)} className="w-28" />
            </Field>
          </div>
          <ArchitectureTab design={design} onChange={(d) => state.edit(d)} status={status} />
        </div>
      )}
      {tab === "body" && <BodyDesigner design={design} onChange={(d) => state.edit(d)} />}
      {tab === "aero" && <WindTunnel design={design} onChange={(d) => state.edit(d)} target={target} setTarget={setTarget} />}
      {tab === "performance" &&
        (result ? <PerformanceTab result={result} design={design} /> : sim.busy ? <Spinner label="Simulating…" /> : <Empty title="Press Simulate" />)}
      {tab === "scenarios" && <ScenarioTab design={design} target={target} setTarget={setTarget} />}
      {tab === "weather" && <WeatherStudy design={design} target={target} setTarget={setTarget} />}
      {tab === "materials" && <MaterialStudy design={design} target={target} setTarget={setTarget} />}
      {tab === "history" && <HistoryPanel state={state} />}
      {tab === "trust" && (result ? <TrustPanel trust={{ ...result.engine.trust, ...result.trust }} compute={result.engine.compute} /> : <Empty title="Press Simulate" />)}
      </Container>
    </div>
  );
}
