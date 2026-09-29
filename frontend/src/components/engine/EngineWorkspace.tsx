"use client";

import { Activity, Compass, FlaskRound, GitBranch, Grid3x3, Play, ShieldCheck, SlidersHorizontal, Split, Wand2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ComputePicker, ProjectBar } from "@/components/project/ProjectBar";
import { HistoryPanel, TrustPanel } from "@/components/project/Panels";
import type { ProjectState } from "@/components/project/useProject";
import { Button, Card, Empty, ErrorNote, Input, Spinner, Stat, Tabs, useAsync } from "@/components/ui";
import { api, runJob } from "@/lib/api";
import { fmt } from "@/lib/format";
import type { EngineResult, Param } from "@/lib/types";
import { AdvisorTab, LimitsTab, WhatIfTab } from "./AnalyzeTabs";
import { ComponentStatusList, DynoTab } from "./DynoTab";
import { Engine3D } from "./Engine3D";
import { EngineEditor } from "./EngineEditor";
import { ExploreTab, TestTab } from "./ExploreTestTabs";
import type { Level } from "./ParamEditor";

type Tab = "design" | "dyno" | "limits" | "whatif" | "advisor" | "explore" | "test" | "history" | "trust";

export function EngineWorkspace({ state }: { state: ProjectState }) {
  const [tab, setTab] = useState<Tab>("design");
  const [group, setGroup] = useState("turbo");
  const [level, setLevel] = useState<Level>("engineer");
  const [result, setResult] = useState<EngineResult | null>(null);
  const [samples, setSamples] = useState(200);
  const [target, setTarget] = useState("server");
  const [jobStatus, setJobStatus] = useState("");
  const sim = useAsync();
  const design = state.design!;

  const simulate = useCallback(
    () =>
      sim.run(async () => {
        const r =
          target === "server" && samples <= 500
            ? await api<EngineResult>("/api/v1/engine/simulate", { method: "POST", json: { design, samples } })
            : await runJob<EngineResult>("simulate", { design, samples }, target, setJobStatus, state.project?.id);
        setResult(r);
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [design, samples, target],
  );

  useEffect(() => {
    if (!result) simulate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.head?.id]);

  const g = design.engine as { cylinders: number; bore: Param; stroke: Param; rod_length: Param };
  const geometry = { cylinders: g.cylinders, bore: g.bore.value, stroke: g.stroke.value, rod: g.rod_length.value };

  const runBar = (
    <>
      <label className="inline-flex items-center gap-1 text-xs text-ink-2" title="Monte Carlo samples for uncertainty">
        Samples
        <Input type="number" min={1} max={2000} value={samples} onChange={(e) => setSamples(Number(e.target.value))} className="h-8 w-20 text-xs" />
      </label>
      <ComputePicker value={target} onChange={setTarget} />
      <Button variant="primary" onClick={simulate} loading={sim.busy}>
        <Play className="size-3.5" aria-hidden /> Run simulation
      </Button>
    </>
  );

  const needsResult = (node: React.ReactNode) =>
    result ? node : sim.busy ? <Spinner label={`Simulating${jobStatus ? ` (${jobStatus})` : ""}…`} /> : <Empty title="Run a simulation first">Press Simulate.</Empty>;

  return (
    <div className="space-y-4">
      <ProjectBar state={state}>{runBar}</ProjectBar>
      <ErrorNote error={sim.error} onClose={() => sim.setError(null)} />
      <Tabs
        tabs={[
          { id: "design", label: "Design", icon: SlidersHorizontal },
          { id: "dyno", label: "Virtual dyno", icon: Activity },
          { id: "limits", label: "Limits", icon: ShieldCheck },
          { id: "whatif", label: "What-if", icon: Split },
          { id: "advisor", label: "Upgrade advisor", icon: Wand2 },
          { id: "explore", label: "Explore (GPU)", icon: Grid3x3 },
          { id: "test", label: "Test & calibrate", icon: FlaskRound },
          { id: "history", label: "History", icon: GitBranch },
          { id: "trust", label: "Trust", icon: Compass },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "design" && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_440px]">
          <EngineEditor design={design} onChange={state.edit} group={group} setGroup={setGroup} level={level} setLevel={setLevel} />
          <div className="space-y-4">
            <Engine3D geometry={geometry} status={result?.component_status ?? {}} />
            {result && (
              <div className="grid grid-cols-2 gap-3">
                <Stat label="Peak power" value={fmt(result.summary.peak_power.nominal, 0)} unit="kW" sub={`${fmt(result.summary.peak_power.p05, 0)}–${fmt(result.summary.peak_power.p95, 0)} kW`} />
                <Stat label="Peak torque" value={fmt(result.summary.peak_torque.nominal, 0)} unit="N·m" sub={`${fmt(result.summary.peak_torque.p05, 0)}–${fmt(result.summary.peak_torque.p95, 0)}`} />
              </div>
            )}
            {result && (
              <Card title="Component status" subtitle={state.dirty ? "From the last simulation; press Simulate to refresh after edits." : undefined}>
                <ComponentStatusList result={result} />
              </Card>
            )}
          </div>
        </div>
      )}
      {tab === "dyno" && needsResult(result && <DynoTab result={result} design={design} versions={state.versions} headId={state.head?.id} projectId={state.project!.id} />)}
      {tab === "limits" && needsResult(result && <LimitsTab result={result} />)}
      {tab === "whatif" && <WhatIfTab state={state} projectId={state.project!.id} />}
      {tab === "advisor" && <AdvisorTab state={state} result={result} />}
      {tab === "explore" && <ExploreTab state={state} />}
      {tab === "test" && <TestTab state={state} />}
      {tab === "history" && <HistoryPanel state={state} />}
      {tab === "trust" && needsResult(result && <TrustPanel trust={result.trust} compute={result.compute} />)}
    </div>
  );
}
