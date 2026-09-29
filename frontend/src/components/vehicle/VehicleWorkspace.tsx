"use client";

import { Activity, CarFront, CloudSun, Compass, FlaskConical, GitBranch, Network, Play, Timer } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { HistoryPanel, TrustPanel } from "@/components/project/Panels";
import { ComputePicker, ProjectBar } from "@/components/project/ProjectBar";
import type { ProjectState } from "@/components/project/useProject";
import { Button, Empty, ErrorNote, Field, Input, Spinner, Tabs, useAsync } from "@/components/ui";
import { api, runJob } from "@/lib/api";
import type { Status, VehicleDesign } from "@/lib/types";
import { ArchitectureTab } from "./Architecture";
import { BodyDesigner } from "./BodyDesigner";
import { PerformanceTab, type VehicleResult } from "./PerformanceTab";
import { ScenarioTab } from "./ScenarioTab";
import { MaterialStudy, WeatherStudy } from "./StudiesTab";

type Tab = "architecture" | "body" | "performance" | "scenarios" | "weather" | "materials" | "history" | "trust";

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

  return (
    <div className="space-y-4">
      <ProjectBar state={state}>
        <label className="inline-flex items-center gap-1 text-xs text-ink-2">
          Samples
          <Input type="number" min={1} max={2000} value={samples} onChange={(e) => setSamples(Number(e.target.value))} className="h-8 w-20 text-xs" />
        </label>
        <ComputePicker value={target} onChange={setTarget} />
        <Button variant="primary" onClick={simulate} loading={sim.busy}>
          <Play className="size-3.5" aria-hidden /> Run simulation
        </Button>
      </ProjectBar>
      <ErrorNote error={sim.error} onClose={() => sim.setError(null)} />
      <Tabs
        tabs={[
          { id: "architecture", label: "Architecture", icon: Network },
          { id: "body", label: "Body design", icon: CarFront },
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
      {tab === "architecture" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-3 border border-line bg-surface px-4 py-3">
            <span className="text-sm font-medium">Vehicle targets</span>
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
      {tab === "performance" &&
        (result ? <PerformanceTab result={result} design={design} /> : sim.busy ? <Spinner label="Simulating…" /> : <Empty title="Press Simulate" />)}
      {tab === "scenarios" && <ScenarioTab design={design} target={target} setTarget={setTarget} />}
      {tab === "weather" && <WeatherStudy design={design} target={target} setTarget={setTarget} />}
      {tab === "materials" && <MaterialStudy design={design} target={target} setTarget={setTarget} />}
      {tab === "history" && <HistoryPanel state={state} />}
      {tab === "trust" && (result ? <TrustPanel trust={{ ...result.engine.trust, ...result.trust }} compute={result.engine.compute} /> : <Empty title="Press Simulate" />)}
    </div>
  );
}
