"use client";

import { Activity, Cog, Compass, FlaskRound, GitBranch, Grid3x3, Play, ShieldCheck, SlidersHorizontal, Split, Wand2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Container, type FigureItem, StickyTabs } from "@/components/layout";
import { ComputePicker, ProjectBar } from "@/components/project/ProjectBar";
import { HistoryPanel, TrustPanel } from "@/components/project/Panels";
import type { ProjectState } from "@/components/project/useProject";
import { Button, Card, Empty, ErrorNote, Input, Spinner, Tabs, useAsync } from "@/components/ui";
import { api, runJob } from "@/lib/api";
import { normalizeLayout } from "@/lib/engineLayout";
import { fmt, kwToHp } from "@/lib/format";
import type { EngineResult, Param } from "@/lib/types";
import { AdvisorTab, LimitsTab, WhatIfTab } from "./AnalyzeTabs";
import { BalancePanel, useLayout } from "./BalancePanel";
import { ComponentStatusList, DynoTab } from "./DynoTab";
import { Engine3D } from "./Engine3D";
import { EngineEditor } from "./EngineEditor";
import { ExploreTab, TestTab } from "./ExploreTestTabs";
import type { Level } from "./ParamEditor";

type Tab = "design" | "balance" | "dyno" | "limits" | "whatif" | "advisor" | "explore" | "test" | "history" | "trust";

export function EngineWorkspace({ state }: { state: ProjectState }) {
  const [tab, setTab] = useState<Tab>("design");
  const [group, setGroup] = useState("architecture");
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
  const arch = (design.architecture ?? {}) as { layout?: string; induction?: string; bank_angle?: Param };
  const { layout, error: layoutError } = useLayout(design);
  const naturallyAspirated = arch.induction === "naturally_aspirated";

  const runBar = (
    <>
      <label className="inline-flex items-center gap-2" title="Monte Carlo samples for uncertainty">
        <span className="eyebrow">Samples</span>
        <Input type="number" min={1} max={2000} value={samples} onChange={(e) => setSamples(Number(e.target.value))} className="h-10 w-24" />
      </label>
      <ComputePicker value={target} onChange={setTarget} />
      <Button variant="primary" size="lg" onClick={simulate} loading={sim.busy}>
        <Play className="size-3.5" aria-hidden /> Run simulation
      </Button>
    </>
  );

  const figures: FigureItem[] = result
    ? [
        { label: "Peak power", value: fmt(result.summary.peak_power.nominal, 0), unit: "kW", sub: `${fmt(kwToHp(result.summary.peak_power.nominal), 0)} hp · ${fmt(result.summary.peak_power.p05, 0)}–${fmt(result.summary.peak_power.p95, 0)} kW` },
        { label: "Peak torque", value: fmt(result.summary.peak_torque.nominal, 0), unit: "N·m", sub: `at ${fmt(result.summary.peak_torque.rpm, 0)} rpm` },
        { label: "Displacement", value: fmt(result.summary.displacement_l, 2), unit: "L", sub: `${g.cylinders} cylinders · ${fmt(result.summary.specific_power_kw_per_l, 0)} kW/L` },
        naturallyAspirated
          ? { label: "Max boost", value: "0", unit: "bar", sub: "Naturally aspirated" }
          : { label: "Max boost", value: fmt(result.summary.max_boost.nominal, 2), unit: "bar", sub: `from ${fmt(result.summary.max_boost.rpm, 0)} rpm` },
      ]
    : ["Peak power", "Peak torque", "Displacement", "Max boost"].map((label) => ({
        label,
        value: "—",
        sub: sim.busy ? "Simulating…" : "Run a simulation",
      }));

  const needsResult = (node: React.ReactNode) =>
    result ? node : sim.busy ? <Spinner label={`Simulating${jobStatus ? ` (${jobStatus})` : ""}…`} /> : <Empty title="Run a simulation first">Press Simulate.</Empty>;

  return (
    <div>
      <ProjectBar state={state} figures={figures}>
        {runBar}
      </ProjectBar>
      <StickyTabs>
        <Tabs
          tabs={[
            { id: "design", label: "Design", icon: SlidersHorizontal },
            { id: "balance", label: "Balance & firing", icon: Cog },
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
      </StickyTabs>
      <Container className="space-y-6 py-10">
      <ErrorNote error={sim.error} onClose={() => sim.setError(null)} />
      {tab === "design" && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_460px]">
          <EngineEditor design={design} onChange={(d) => state.edit(normalizeLayout(design, d))} group={group} setGroup={setGroup} level={level} setLevel={setLevel} />
          <div className="space-y-4">
            <Engine3D geometry={geometry} layout={layout?.cylinders} induction={arch.induction} status={result?.component_status ?? {}} height={440} />
            {layoutError && <ErrorNote error={layoutError} />}
            {layout && !layoutError && (
              <p className="text-xs text-ink-3">
                {layout.summary.join(" · ")} · {layout.even_firing ? "even firing" : "uneven firing"}
              </p>
            )}
            {result && (
              <Card title="Component status" subtitle={state.dirty ? "From the last simulation; press Simulate to refresh after edits." : undefined}>
                <ComponentStatusList result={result} />
              </Card>
            )}
          </div>
        </div>
      )}
      {tab === "balance" &&
        (layout ? (
          <BalancePanel layout={layout} cylinders={g.cylinders} bankAngle={arch.bank_angle?.value ?? 90} />
        ) : layoutError ? (
          <ErrorNote error={layoutError} />
        ) : (
          <Spinner label="Analysing layout" />
        ))}
      {tab === "dyno" && needsResult(result && <DynoTab result={result} design={design} versions={state.versions} headId={state.head?.id} projectId={state.project!.id} />)}
      {tab === "limits" && needsResult(result && <LimitsTab result={result} />)}
      {tab === "whatif" && <WhatIfTab state={state} projectId={state.project!.id} />}
      {tab === "advisor" && <AdvisorTab state={state} result={result} />}
      {tab === "explore" && <ExploreTab state={state} />}
      {tab === "test" && <TestTab state={state} />}
      {tab === "history" && <HistoryPanel state={state} />}
      {tab === "trust" && needsResult(result && <TrustPanel trust={result.trust} compute={result.compute} />)}
      </Container>
    </div>
  );
}
