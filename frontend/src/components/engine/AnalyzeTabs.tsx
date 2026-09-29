"use client";

import { ArrowDown, ArrowRight, ArrowUp, GitBranch, Wand2 } from "lucide-react";
import { useState } from "react";
import { BarList, LineChartBands } from "@/components/charts/Charts";
import { LimitsTable } from "@/components/project/Panels";
import type { ProjectState } from "@/components/project/useProject";
import { Button, Card, Empty, ErrorNote, Field, Input, Note, Select, Spinner, Stat, StatusBadge, useAsync } from "@/components/ui";
import { api } from "@/lib/api";
import { fmt, pct } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Dist, EngineResult, Json, Status, Version } from "@/lib/types";
import { ComponentStatusList } from "./DynoTab";

export function LimitsTab({ result }: { result: EngineResult }) {
  const { meta } = useSession();
  const name = (id: string) => meta?.components.find((c) => c.id === id)?.name ?? id;
  const sens = result.sensitivity?.peak_power ?? [];
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <Card
          title="Engineering limits and checks"
          subtitle="Safety factor = allowable ÷ load. Conservative values use the 95th-percentile load and the 5th-percentile safety factor."
        >
          <LimitsTable limits={result.limits} componentName={name} />
          <details className="mt-3 text-xs text-ink-2">
            <summary className="cursor-pointer">How statuses are assigned</summary>
            <ul className="ml-4 mt-1 list-disc space-y-0.5">
              {Object.entries(result.status_rules).map(([k, v]) => (
                <li key={k}>
                  <span className="font-medium capitalize">{k.replace("_", " ")}:</span> {v}
                </li>
              ))}
              <li>These bands are a project convention, not a certification standard.</li>
            </ul>
          </details>
        </Card>
        {sens.length > 0 && (
          <BarList
            title="What drives the uncertainty in peak power"
            subtitle="Rank correlation of each uncertain input with peak power. Measure the top inputs first to narrow the prediction."
            rows={sens.map((r) => ({ label: r.label, value: r.rho, note: `${r.path} · ${pct(r.share)} of explained variation` }))}
            unit="ρ"
            digits={2}
            diverging
          />
        )}
      </div>
      <Card title="Component status">
        <ComponentStatusList result={result} />
      </Card>
    </div>
  );
}

interface WhatIf {
  changes: { path: string; label: string; kind: string; before: unknown; after: unknown }[];
  propagation: { model: string; label: string; depth: number; triggered_by: string[]; outputs: string[]; output_changes: Record<string, number | null> }[];
  headline: { key: string; label: string; unit: string; before: Dist; after: Dist; delta: number; rel: number | null }[];
  components: {
    id: string;
    name: string;
    system: string;
    status_before: Status;
    status_after: Status;
    directly_modified: boolean;
    changed_channels: { channel: string; label: string; unit: string; max_before: number; max_after: number; max_rel_change: number | null }[];
  }[];
  newly_limiting: { id: string; label: string; component: string; status_before: Status; status_after: Status; sf_before: number | null; sf_after: number | null }[];
  limiting: { id: string; label: string; sf_after: number; status_after: Status }[];
  baseline: EngineResult;
  variant: EngineResult;
  notes: string[];
}

function Delta({ rel }: { rel: number | null }) {
  if (rel === null || Math.abs(rel) < 0.0005) return <span className="text-ink-3">no change</span>;
  const Icon = rel > 0 ? ArrowUp : ArrowDown;
  return (
    <span className="inline-flex items-center gap-0.5 text-ink">
      <Icon className="size-3" aria-hidden />
      {pct(Math.abs(rel), 1)}
    </span>
  );
}

export function WhatIfTab({ state, projectId }: { state: ProjectState; projectId: string }) {
  const { versions, design, head } = state;
  const [baselineId, setBaselineId] = useState("");
  const [res, setRes] = useState<WhatIf | null>(null);
  const act = useAsync();
  const { meta } = useSession();
  const chan = (id: string) => meta?.channels.find((c) => c.id === id);
  const baseChoice = baselineId || versions.find((v) => v.id !== head?.id)?.id || head?.id || "";

  const run = () =>
    act.run(async () => {
      const v = await api<Version>(`/api/v1/projects/${projectId}/versions/${baseChoice}`);
      setRes(await api<WhatIf>("/api/v1/engine/compare", { method: "POST", json: { baseline: v.design, variant: design, samples: 150 } }));
    });

  const physical = res?.changes.filter((c) => !["name", "description"].includes(c.path)) ?? [];
  return (
    <div className="space-y-4">
      <Card title="What happens if I change this?" subtitle="Compares your current working design against a saved version and traces the change through every model.">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Baseline">
            <Select value={baseChoice} onChange={(e) => setBaselineId(e.target.value)} className="w-80">
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.number} · {v.branch} · {v.message.slice(0, 40)}
                </option>
              ))}
            </Select>
          </Field>
          <ArrowRight className="mb-2 size-4 text-ink-3" aria-hidden />
          <span className="mb-2 text-sm">Current working design{state.dirty ? " (unsaved edits)" : ""}</span>
          <Button variant="primary" onClick={run} loading={act.busy} className="mb-0.5">
            Run what-if
          </Button>
        </div>
        <p className="mt-2 text-xs text-ink-3">Tip: edit parameters in the Design tab without saving, then run the what-if here.</p>
      </Card>
      <ErrorNote error={act.error} />
      {act.busy && <Spinner label="Simulating both designs with identical random streams…" />}
      {res && (
        <>
          {physical.length === 0 && <Note>The two designs have identical physics inputs.</Note>}
          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Headline effects">
              <table className="w-full text-sm tabular">
                <thead className="text-left text-xs text-ink-2">
                  <tr><th className="py-1 font-medium">Quantity</th><th className="py-1 text-right font-medium">Before</th><th className="py-1 text-right font-medium">After</th><th className="py-1 text-right font-medium">Change</th></tr>
                </thead>
                <tbody>
                  {res.headline.map((h) => (
                    <tr key={h.key} className="border-t border-line">
                      <td className="py-1.5">{h.label}</td>
                      <td className="py-1.5 text-right">{fmt(h.before.nominal, 1)} <span className="text-ink-3">{h.unit}</span></td>
                      <td className="py-1.5 text-right">{fmt(h.after.nominal, 1)} <span className="text-ink-3">{h.unit}</span></td>
                      <td className="py-1.5 text-right"><Delta rel={h.rel} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title="Propagation path" subtitle="How the change flows through the physics models">
              <p className="mb-2 text-xs text-ink-2">Changed: {physical.map((c) => c.label).join(", ") || "—"}</p>
              <ol className="space-y-2">
                {res.propagation.map((s) => (
                  <li key={s.model} className="flex gap-2" style={{ marginLeft: (s.depth - 1) * 16 }}>
                    <span className="mt-1 inline-block size-2 shrink-0 rounded-full bg-accent" aria-hidden />
                    <div className="text-sm">
                      <span className="font-medium">{s.label}</span>
                      <div className="flex flex-wrap gap-x-3 text-xs text-ink-2">
                        {Object.entries(s.output_changes).filter(([, v]) => v !== null && Math.abs(v) > 0.005).map(([k, v]) => (
                          <span key={k}>{chan(k)?.label ?? k} <Delta rel={v} /></span>
                        ))}
                        {Object.values(s.output_changes).every((v) => v === null || Math.abs(v) <= 0.005) && <span className="text-ink-3">no significant numeric change</span>}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          </div>
          {res.newly_limiting.length > 0 && (
            <Card title="Newly limiting components" subtitle="Limits whose status got worse with this change">
              <ul className="space-y-1.5">
                {res.newly_limiting.map((l) => (
                  <li key={l.id} className="flex flex-wrap items-center gap-2 text-sm">
                    <StatusBadge status={l.status_before} />
                    <ArrowRight className="size-3.5 text-ink-3" aria-hidden />
                    <StatusBadge status={l.status_after} />
                    <span className="font-medium">{l.label}</span>
                    <span className="text-xs text-ink-3">SF {fmt(l.sf_before, 2)} → {fmt(l.sf_after, 2)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <Card title="Affected components">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {res.components.map((c) => (
                <div key={c.id} className="border border-line p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{c.name}</span>
                    <span className="inline-flex items-center gap-1"><StatusBadge status={c.status_before} compact /><ArrowRight className="size-3 text-ink-3" /><StatusBadge status={c.status_after} /></span>
                  </div>
                  {c.directly_modified && <div className="text-xs text-accent">Directly modified</div>}
                  <ul className="mt-1 space-y-0.5 text-xs text-ink-2">
                    {c.changed_channels.map((ch) => (
                      <li key={ch.channel} className="flex justify-between gap-2">
                        <span>{ch.label}</span>
                        <span className="tabular">{fmt(ch.max_before, 1)} → {fmt(ch.max_after, 1)} {ch.unit} <Delta rel={ch.max_rel_change} /></span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Card>
          <div className="grid gap-4 xl:grid-cols-2">
            {(["torque", "power"] as const).map((id) => (
              <LineChartBands
                key={id}
                title={chan(id)?.label ?? id}
                x={res.variant.rpm}
                xLabel="Engine speed"
                xUnit="rpm"
                unit={chan(id)?.unit ?? ""}
                syncId="whatif"
                series={[
                  { id: "base", label: "Baseline", color: "var(--s2)", values: res.baseline.channels[id].nominal, band: { lo: res.baseline.channels[id].p05, hi: res.baseline.channels[id].p95 } },
                  { id: "var", label: "Changed", color: "var(--s1)", values: res.variant.channels[id].nominal, band: { lo: res.variant.channels[id].p05, hi: res.variant.channels[id].p95 } },
                ]}
              />
            ))}
          </div>
          {res.notes.map((n) => <p key={n} className="text-xs text-ink-3">{n}</p>)}
        </>
      )}
    </div>
  );
}

interface Strategy {
  id: string;
  label: string;
  boost_bar: number;
  turbine_flow_area_cm2: number;
  peak_power: Dist;
  peak_torque: Dist;
  spool_rpm: number | null;
  max_egt: Dist;
  probability_met: number | null;
  upgrades: { limit_id: string; component: string; label: string; unit: string; status: Status; current_allowable: number | null; required_allowable?: number; action: string }[];
  upgrade_count: number;
  rod_material_options: { material_id: string; name: string; rod_mass_g: number; worst: Status }[];
  design: Json;
  warnings: string[];
}

export function AdvisorTab({ state, result }: { state: ProjectState; result: EngineResult | null }) {
  const { meta } = useSession();
  const [target, setTarget] = useState<number>(Math.round((result?.summary.peak_power.nominal ?? 180) * 1.25));
  const [res, setRes] = useState<{ target_kw: number; current_peak_power: Dist; strategies: Strategy[]; notes: string[] } | null>(null);
  const act = useAsync();
  const name = (id: string) => meta?.components.find((c) => c.id === id)?.name ?? id;

  const run = () => act.run(async () => setRes(await api("/api/v1/engine/advise", { method: "POST", json: { design: state.design, target_kw: target, samples: 150 } })));

  const branchFrom = (s: Strategy) =>
    act.run(async () => {
      const p = state.project!;
      const name = `${Math.round(target)}kw-${s.id.replace(/_/g, "-")}`;
      await api(`/api/v1/projects/${p.id}/branches`, { method: "POST", json: { name, from_version_id: state.head!.id } });
      await state.commit(`Advisor: ${s.label} for ${Math.round(target)} kW`, s.design, name);
    });

  return (
    <div className="space-y-4">
      <Card title="Upgrade advisor" subtitle="What must change to reach a power target? Each strategy is a concrete candidate design with the parts that would need upgrading.">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Target peak power (kW)">
            <Input type="number" min={1} value={target} onChange={(e) => setTarget(Number(e.target.value))} className="w-36" />
          </Field>
          <span className="mb-2 text-xs text-ink-3">≈ {fmt(target * 1.34102, 0)} hp</span>
          <Button variant="primary" onClick={run} loading={act.busy} className="mb-0.5">
            <Wand2 className="size-4" /> Find strategies
          </Button>
        </div>
      </Card>
      <ErrorNote error={act.error} />
      {act.busy && <Spinner label="Searching boost and turbine options, then checking every limit…" />}
      {res && res.strategies.length === 0 && <Empty title="No strategy reaches this target">{res.notes[0]}</Empty>}
      {res && (
        <div className="grid gap-4 xl:grid-cols-2">
          {res.strategies.map((s) => (
            <Card
              key={s.id}
              title={s.label}
              subtitle={`${s.upgrade_count} part${s.upgrade_count === 1 ? "" : "s"} to upgrade`}
              actions={
                <Button size="sm" onClick={() => branchFrom(s)} loading={act.busy}>
                  <GitBranch className="size-3.5" /> Save as branch
                </Button>
              }
            >
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <Stat label="Boost" value={fmt(s.boost_bar, 2)} unit="bar" />
                <Stat label="Full boost from" value={s.spool_rpm ? fmt(s.spool_rpm, 0) : "–"} unit="rpm" />
                <Stat label="Peak power" value={fmt(s.peak_power.nominal, 0)} unit="kW" sub={`${fmt(s.peak_power.p05, 0)}–${fmt(s.peak_power.p95, 0)}`} />
                <Stat label="Chance to meet" value={pct(s.probability_met)} />
              </div>
              <div className="mt-3 space-y-1.5">
                {s.upgrades.map((u) => (
                  <div key={u.limit_id} className="flex items-start gap-2 text-sm">
                    <StatusBadge status={u.status} compact />
                    <div>
                      <span className="font-medium">{u.label}</span> <span className="text-xs text-ink-3">· {name(u.component)}</span>
                      <div className="text-xs text-ink-2">
                        {u.action}
                        {u.current_allowable != null && ` (now ${fmt(u.current_allowable, 1)} ${u.unit})`}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {s.rod_material_options.length > 0 && (
                <div className="mt-3">
                  <div className="text-xs font-medium text-ink-2">Rod material options at this load</div>
                  <ul className="mt-1 text-xs">
                    {s.rod_material_options.map((m) => (
                      <li key={m.material_id} className="flex justify-between gap-2 py-0.5">
                        <span>{m.name}</span>
                        <span className="inline-flex items-center gap-2">{fmt(m.rod_mass_g, 0)} g <StatusBadge status={m.worst} /></span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {s.warnings.map((w) => <p key={w} className="mt-2 text-xs text-ink-3">{w}</p>)}
            </Card>
          ))}
        </div>
      )}
      {res?.notes.map((n) => <Note key={n}>{n}</Note>)}
    </div>
  );
}

