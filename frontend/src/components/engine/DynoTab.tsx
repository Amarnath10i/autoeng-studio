"use client";

import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { LineChartBands, type RefLine, type Series } from "@/components/charts/Charts";
import { Button, Note, Select, Stat, StatusBadge, useAsync } from "@/components/ui";
import { api } from "@/lib/api";
import { fmt, kwToHp, pct, SERIES } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { EngineResult, Json, Limit, Version } from "@/lib/types";

interface Overlay {
  versionId: string;
  label: string;
  result: EngineResult;
}

const DEFAULT_PANELS = ["torque", "power", "boost", "air_flow", "egt", "peak_pressure", "charge_temp", "bsfc"];

export function DynoTab({
  result,
  design,
  versions,
  headId,
  projectId,
}: {
  result: EngineResult;
  design: Json;
  versions: Version[];
  headId?: string;
  projectId: string;
}) {
  const { meta } = useSession();
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const [pick, setPick] = useState("");
  const [custom, setCustom] = useState<string[]>([]);
  const act = useAsync();
  const channels = meta?.channels ?? [];
  const chan = (id: string) => channels.find((c) => c.id === id);
  const limits = (design.limits as Limit[]) ?? [];
  const s = result.summary;

  const addOverlay = () =>
    act.run(async () => {
      const v = versions.find((x) => x.id === pick);
      if (!v || overlays.length >= 3) return;
      const vd = await api<Version>(`/api/v1/projects/${projectId}/versions/${v.id}`);
      const r = await api<EngineResult>("/api/v1/engine/simulate", { method: "POST", json: { design: vd.design, samples: 1 } });
      setOverlays((o) => [...o, { versionId: v.id, label: `v${v.number} · ${v.message.slice(0, 24)}`, result: r }]);
      setPick("");
    });

  const panels = useMemo(() => {
    const ids = custom.length ? custom : DEFAULT_PANELS;
    // Group the chosen channels by unit: one panel per unit, never two y-scales on one plot.
    const byUnit = new Map<string, string[]>();
    for (const id of ids) {
      const c = chan(id);
      if (!c) continue;
      byUnit.set(c.unit, [...(byUnit.get(c.unit) ?? []), id]);
    }
    return custom.length ? [...byUnit.values()] : ids.map((id) => [id]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [custom, channels]);

  const seriesFor = (ids: string[]): Series[] => {
    const out: Series[] = [];
    ids.forEach((id, k) => {
      const c = result.channels[id];
      if (!c) return;
      out.push({
        id: `cur_${id}`,
        label: ids.length > 1 ? chan(id)?.label ?? id : overlays.length ? "Current design" : chan(id)?.label ?? id,
        color: SERIES[k % SERIES.length],
        values: c.nominal,
        band: { lo: c.p05, hi: c.p95 },
      });
      if (ids.length === 1)
        overlays.forEach((o, j) =>
          out.push({ id: `ov_${o.versionId}_${id}`, label: o.label, color: SERIES[(j + 1) % SERIES.length], values: o.result.channels[id]?.nominal ?? [] }),
        );
    });
    return out;
  };

  const refsFor = (ids: string[]): RefLine[] => {
    const refs: RefLine[] = [];
    for (const id of ids) {
      for (const l of limits.filter((x) => x.channel === id)) refs.push({ y: l.allowable.value, label: `Limit: ${l.label ?? id}`, kind: "limit" });
      for (const t of result.targets.filter((x) => x.channel === id)) refs.push({ y: t.target, label: "Target", kind: "target" });
    }
    return refs;
  };

  const powerTarget = result.targets.find((t) => t.id === "peak_power");
  const torqueTarget = result.targets.find((t) => t.id === "peak_torque");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat
          label="Peak power"
          value={fmt(s.peak_power.nominal, 0)}
          unit="kW"
          sub={`${fmt(kwToHp(s.peak_power.nominal), 0)} hp · 90 % range ${fmt(s.peak_power.p05, 0)}–${fmt(s.peak_power.p95, 0)} kW`}
        />
        <Stat label="Peak torque" value={fmt(s.peak_torque.nominal, 0)} unit="N·m" sub={`at ${fmt(s.peak_torque.rpm, 0)} rpm · ${fmt(s.peak_torque.p05, 0)}–${fmt(s.peak_torque.p95, 0)}`} />
        <Stat label="Max boost" value={fmt(s.max_boost.nominal, 2)} unit="bar" sub={`at ${fmt(s.max_boost.rpm, 0)} rpm`} />
        <Stat label="Specific output" value={fmt(s.specific_power_kw_per_l, 0)} unit="kW/L" sub={`${fmt(s.displacement_l, 2)} L displacement`} />
        <Stat label="Best BSFC" value={fmt(s.min_bsfc.nominal, 0)} unit="g/kWh" sub={`at ${fmt(s.min_bsfc.rpm, 0)} rpm`} />
        <Stat
          label="Meets power target"
          value={powerTarget ? pct(powerTarget.probability_met) : "–"}
          sub={powerTarget ? `target ${fmt(powerTarget.target, 0)} kW${torqueTarget ? ` · torque ${pct(torqueTarget.probability_met)}` : ""}` : "Set targets in Design"}
          status={powerTarget ? (powerTarget.probability_met >= 0.9 ? "ok" : powerTarget.probability_met >= 0.5 ? "warning" : "critical") : undefined}
        />
      </div>

      {result.warnings.map((w) => (
        <Note key={w} tone="warning">{w}</Note>
      ))}

      <div className="flex flex-wrap items-center gap-2 border border-line bg-surface px-3 py-2">
        <span className="text-xs font-medium text-ink-2">Compare with</span>
        <Select value={pick} onChange={(e) => setPick(e.target.value)} className="h-7 w-64 text-xs" aria-label="Version to compare">
          <option value="">Pick a saved version (e.g. stock)…</option>
          {versions.filter((v) => v.id !== headId && !overlays.some((o) => o.versionId === v.id)).map((v) => (
            <option key={v.id} value={v.id}>v{v.number} · {v.branch} · {v.message.slice(0, 40)}</option>
          ))}
        </Select>
        <Button size="sm" onClick={addOverlay} disabled={!pick || overlays.length >= 3} loading={act.busy}>Add</Button>
        {overlays.map((o) => (
          <span key={o.versionId} className="inline-flex items-center gap-1 rounded bg-surface-2 px-2 py-0.5 text-xs">
            {o.label}
            <button type="button" onClick={() => setOverlays((x) => x.filter((y) => y.versionId !== o.versionId))} aria-label={`Remove ${o.label}`}>
              <X className="size-3" />
            </button>
          </span>
        ))}
        <span className="mx-1 h-5 w-px bg-[var(--border)]" aria-hidden />
        <span className="text-xs font-medium text-ink-2">Chart builder</span>
        <Select
          value=""
          onChange={(e) => e.target.value && setCustom((c) => [...new Set([...c, e.target.value])])}
          className="h-7 w-52 text-xs"
          aria-label="Add a channel to plot"
        >
          <option value="">Plot a quantity vs rpm…</option>
          {channels.filter((c) => c.id !== "rpm" && result.channels[c.id]).map((c) => (
            <option key={c.id} value={c.id}>{c.label} ({c.unit})</option>
          ))}
        </Select>
        {custom.map((id) => (
          <span key={id} className="inline-flex items-center gap-1 rounded bg-surface-2 px-2 py-0.5 text-xs">
            {chan(id)?.label}
            <button type="button" onClick={() => setCustom((c) => c.filter((x) => x !== id))} aria-label={`Remove ${id}`}>
              <X className="size-3" />
            </button>
          </span>
        ))}
        {custom.length > 0 && <Button size="sm" variant="ghost" onClick={() => setCustom([])}>Reset</Button>}
      </div>
      {act.error && <Note tone="warning">{act.error}</Note>}

      <div className="grid gap-4 xl:grid-cols-2">
        {panels.map((ids) => {
          const c = chan(ids[0]);
          if (!c) return null;
          return (
            <LineChartBands
              key={ids.join("+")}
              title={ids.length > 1 ? ids.map((i) => chan(i)?.label).join(", ") : c.label}
              subtitle={ids.length === 1 ? c.description : undefined}
              x={result.rpm}
              xLabel="Engine speed"
              xUnit="rpm"
              unit={c.unit}
              series={seriesFor(ids)}
              refs={refsFor(ids)}
              syncId="dyno"
            />
          );
        })}
      </div>
      <p className="text-xs text-ink-3">
        Shaded bands show the 5–95 % range from input uncertainty (Monte Carlo). They do not include model-form error;
        see the Trust tab.
      </p>
    </div>
  );
}

export function ComponentStatusList({ result }: { result: EngineResult }) {
  const { meta } = useSession();
  return (
    <ul className="divide-y divide-[var(--border)]">
      {(meta?.components ?? []).map((c) => (
        <li key={c.id} className="flex items-center justify-between gap-2 py-1.5 text-sm">
          <span title={c.beginner}>{c.name}</span>
          <StatusBadge status={result.component_status[c.id] ?? "unchecked"} />
        </li>
      ))}
    </ul>
  );
}
