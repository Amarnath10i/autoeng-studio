"use client";

import { Share2, Sparkles, Upload } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Heatmap, LineChartBands } from "@/components/charts/Charts";
import { ComputePicker } from "@/components/project/ProjectBar";
import type { ProjectState } from "@/components/project/useProject";
import { Button, Card, Empty, ErrorNote, Field, Input, Note, Select, SourceBadge, Spinner, useAsync } from "@/components/ui";
import { api, runJob } from "@/lib/api";
import { fmt, getAt, setAt } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Json, Param } from "@/lib/types";

interface SweepResult {
  x: { path: string; label: string; values: number[] };
  y: { path: string; label: string; values: number[] } | null;
  samples: number;
  evaluations: number;
  metrics: Record<string, { p05: number[][]; p50: number[][]; p95: number[][] }>;
  probability_any_failure: number[][];
  most_likely_limit: (string | null)[][];
  probability_target: number[][] | null;
  seconds: number;
  compute: { backend: string; device: string };
  notes: string[];
}

function linspace(a: number, b: number, n: number) {
  return Array.from({ length: n }, (_, i) => (n === 1 ? a : a + ((b - a) * i) / (n - 1)));
}

function Range({
  label,
  path,
  setPath,
  lo,
  hi,
  n,
  set,
  options,
  optional,
}: {
  label: string;
  path: string;
  setPath: (p: string) => void;
  lo: number;
  hi: number;
  n: number;
  set: (v: { lo?: number; hi?: number; n?: number }) => void;
  options: { path: string; label: string; unit: string }[];
  optional?: boolean;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-[1.6fr_1fr_1fr_0.7fr]">
      <Field label={label}>
        <Select value={path} onChange={(e) => setPath(e.target.value)}>
          {optional && <option value="">None (1-D sweep)</option>}
          {options.map((o) => (
            <option key={o.path} value={o.path}>{o.label} ({o.unit})</option>
          ))}
        </Select>
      </Field>
      {(path || !optional) && (
        <>
          <Field label="From"><Input type="number" value={lo} onChange={(e) => set({ lo: Number(e.target.value) })} /></Field>
          <Field label="To"><Input type="number" value={hi} onChange={(e) => set({ hi: Number(e.target.value) })} /></Field>
          <Field label="Steps"><Input type="number" min={2} max={60} value={n} onChange={(e) => set({ n: Math.max(2, Math.min(60, Number(e.target.value))) })} /></Field>
        </>
      )}
    </div>
  );
}

export function ExploreTab({ state }: { state: ProjectState }) {
  const { meta } = useSession();
  const options = useMemo(
    () => (meta?.params ?? []).filter((p) => meta?.sweepable.includes(p.path)).map((p) => ({ path: p.path, label: p.label, unit: p.unit })),
    [meta],
  );
  const current = (path: string) => (getAt(state.design, path) as Param | undefined)?.value ?? 1;
  const [x, setX] = useState({ path: "turbo.boost_target", lo: 0.6, hi: 2.2, n: 20 });
  const [y, setY] = useState({ path: "turbo.turbine_flow_area", lo: 3, hi: 7, n: 15 });
  const [samples, setSamples] = useState(200);
  const [target, setTarget] = useState("server");
  const [status, setStatus] = useState("");
  const [res, setRes] = useState<SweepResult | null>(null);
  const act = useAsync();

  const initRange = (path: string) => {
    const v = current(path);
    const spec = meta?.params.find((p) => p.path === path);
    const lo = Math.max(spec?.min ?? 0, +(v * 0.7).toFixed(3));
    const hi = Math.min(spec?.max ?? v * 2, +(v * 1.4).toFixed(3));
    return { lo, hi };
  };

  const total = x.n * (y.path ? y.n : 1) * samples;
  const run = () =>
    act.run(async () => {
      setRes(null);
      const payload = {
        design: state.design,
        x_path: x.path,
        x_values: linspace(x.lo, x.hi, x.n),
        y_path: y.path || null,
        y_values: y.path ? linspace(y.lo, y.hi, y.n) : null,
        samples,
      };
      setRes(await runJob<SweepResult>("sweep", payload, target, setStatus, state.project?.id));
    });

  const one = res && !res.y;
  return (
    <div className="space-y-4">
      <Card
        title="Design-space explorer"
        subtitle="Evaluate a grid of design variants, each with full Monte Carlo uncertainty. Large sweeps are GPU work: run them on this server or on your own paired GPU (PC, Kaggle, Colab)."
        actions={<ComputePicker value={target} onChange={setTarget} />}
      >
        <div className="space-y-3">
          <Range label="Vary (x)" {...x} setPath={(p) => setX({ path: p, n: x.n, ...initRange(p) })} set={(v) => setX({ ...x, ...v })} options={options} />
          <Range label="…and (y)" {...y} setPath={(p) => setY(p ? { path: p, n: y.n, ...initRange(p) } : { ...y, path: "" })} set={(v) => setY({ ...y, ...v })} options={options} optional />
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Samples per point">
              <Input type="number" min={10} max={2000} value={samples} onChange={(e) => setSamples(Number(e.target.value))} className="w-32" />
            </Field>
            <Button variant="primary" onClick={run} loading={act.busy}>Run sweep</Button>
            <span className="mb-2 text-xs text-ink-3">
              {total.toLocaleString()} engine evaluations{act.busy && status ? ` · ${status}` : ""}
            </span>
          </div>
        </div>
      </Card>
      <ErrorNote error={act.error} />
      {act.busy && <Spinner label={`Sweep ${status || "queued"}…`} />}
      {res && (
        <>
          <p className="text-xs text-ink-3">
            {res.evaluations.toLocaleString()} evaluations in {fmt(res.seconds, 1)} s on {res.compute.device}.
          </p>
          {one ? (
            <div className="grid gap-4 xl:grid-cols-2">
              <LineChartBands
                title="Peak power"
                x={res.x.values}
                xLabel={res.x.label}
                unit="kW"
                syncId="sweep"
                series={[{ id: "p", label: "Peak power", color: "var(--s1)", values: res.metrics.peak_power.p50[0], band: { lo: res.metrics.peak_power.p05[0], hi: res.metrics.peak_power.p95[0] } }]}
              />
              <LineChartBands
                title="Probability that any limit is exceeded"
                x={res.x.values}
                xLabel={res.x.label}
                unit="%"
                syncId="sweep"
                yDomain={[0, 100]}
                series={[{ id: "f", label: "P(any failure)", color: "var(--s2)", values: res.probability_any_failure[0].map((v) => v * 100) }]}
              />
            </div>
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              <Heatmap title="Peak power (median)" xValues={res.x.values} yValues={res.y!.values} xLabel={res.x.label} yLabel={res.y!.label} values={res.metrics.peak_power.p50} unit="kW" digits={0} />
              <Heatmap
                title="Probability that any limit is exceeded"
                subtitle="Darker = riskier. Hover for the most likely limit."
                xValues={res.x.values}
                yValues={res.y!.values}
                xLabel={res.x.label}
                yLabel={res.y!.label}
                values={res.probability_any_failure.map((r) => r.map((v) => v * 100))}
                unit="%"
                digits={0}
                annotate={(xi, yi) => (res.most_likely_limit[yi][xi] ? `most likely: ${res.most_likely_limit[yi][xi]}` : null)}
              />
              {res.probability_target && (
                <Heatmap title="Probability of meeting the power target" xValues={res.x.values} yValues={res.y!.values} xLabel={res.x.label} yLabel={res.y!.label} values={res.probability_target.map((r) => r.map((v) => v * 100))} unit="%" digits={0} />
              )}
              <Heatmap title="Peak cylinder pressure (median)" xValues={res.x.values} yValues={res.y!.values} xLabel={res.x.label} yLabel={res.y!.label} values={res.metrics.max_peak_pressure.p50} unit="bar" digits={0} />
            </div>
          )}
          {res.notes.map((n) => <p key={n} className="text-xs text-ink-3">{n}</p>)}
        </>
      )}
    </div>
  );
}

interface Measurement {
  id: string;
  name: string;
  data: { rpm: number[]; torque: number[]; boost: number[] | null };
  meta: Json;
  created_at: string;
}

interface Calibration {
  parameters: { path: string; label: string; unit: string; before: number; after: number; ci95: number }[];
  torque_rmse_before: number;
  torque_rmse_after: number;
  boost_rmse_before: number | null;
  boost_rmse_after: number | null;
  curves: Record<string, number[] | null>;
  warnings: string[];
  calibrated_design: Json;
  notes: string[];
}

const SAMPLE_CSV = "rpm,torque,boost\n2500,300,0.95\n3000,318,1.0\n3500,320,1.0\n4000,316,1.0";

export function TestTab({ state }: { state: ProjectState }) {
  const { meta } = useSession();
  const pid = state.project!.id;
  const [items, setItems] = useState<Measurement[] | null>(null);
  const [name, setName] = useState("Dyno run");
  const [csv, setCsv] = useState("");
  const [dyno, setDyno] = useState("");
  const [selected, setSelected] = useState("");
  const [params, setParams] = useState<string[]>(["combustion.efficiency_ratio", "friction.a"]);
  const [cal, setCal] = useState<Calibration | null>(null);
  const [consent, setConsent] = useState(false);
  const [shared, setShared] = useState(false);
  const [suggest, setSuggest] = useState<{ total_records: number; suggestions: { path: string; label: string; unit: string; value: number; tol: number; n_effective: number; ref: string }[]; note: string } | null>(null);
  const act = useAsync();

  const load = () => act.run(async () => setItems(await api<Measurement[]>(`/api/v1/projects/${pid}/measurements`)));
  useEffect(() => {
    load();
    api<typeof suggest>("/api/v1/community/suggest", { method: "POST", json: { design: state.design } }).then(setSuggest).catch(() => null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  const upload = () =>
    act.run(async () => {
      await api(`/api/v1/projects/${pid}/measurements`, {
        method: "POST",
        json: { name, csv, version_id: state.head?.id, meta: { dyno_type: dyno, note: "Crank torque" } },
      });
      setCsv("");
      await load();
    });

  const onFile = async (f: File | undefined) => {
    if (f) setCsv(await f.text());
  };

  const m = items?.find((x) => x.id === (selected || items[0]?.id));
  const calibrate = () =>
    act.run(async () => {
      setShared(false);
      setCal(await api<Calibration>("/api/v1/engine/calibrate", { method: "POST", json: { design: state.design, run: { name: m!.name, ...m!.data }, parameters: params } }));
    });

  const apply = () => act.run(() => state.commit(`Calibrated to measurement '${m?.name}'`, cal!.calibrated_design));
  const share = () =>
    act.run(async () => {
      await api("/api/v1/community/share", { method: "POST", json: { design: state.design, calibration: cal, project_id: pid, consent } });
      setShared(true);
    });
  const applySuggestion = (s: { path: string; value: number; tol: number; ref: string }) =>
    state.edit(setAt(state.design!, s.path, { value: +s.value.toFixed(4), tol: +s.tol.toFixed(4), source: "community", ref: s.ref }));

  return (
    <div className="space-y-4">
      <ErrorNote error={act.error} onClose={() => act.setError(null)} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Real-world measurements" subtitle="Upload dyno data (crank torque in N·m; boost in bar gauge optional). Wheel figures must be converted to crank first.">
          <div className="space-y-2">
            <div className="grid gap-2 sm:grid-cols-2">
              <Field label="Run name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Dyno / correction"><Input value={dyno} onChange={(e) => setDyno(e.target.value)} placeholder="e.g. hub dyno, SAE J1349" /></Field>
            </div>
            <textarea value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={SAMPLE_CSV} rows={5} className="w-full border border-line bg-surface p-2 font-mono text-xs" aria-label="CSV data" />
            <div className="flex flex-wrap items-center gap-2">
              <label className="inline-flex cursor-pointer items-center gap-1.5 border border-line px-2.5 py-1 text-xs hover:bg-surface-2">
                <Upload className="size-3.5" /> Choose CSV file
                <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
              </label>
              <Button size="sm" variant="primary" onClick={upload} disabled={!csv.trim()} loading={act.busy}>Save measurement</Button>
            </div>
          </div>
          <ul className="mt-3 divide-y divide-[var(--border)] text-sm">
            {items?.map((it) => (
              <li key={it.id} className="flex items-center justify-between py-1.5">
                <label className="flex items-center gap-2">
                  <input type="radio" name="meas" checked={(selected || items[0]?.id) === it.id} onChange={() => setSelected(it.id)} />
                  {it.name}
                  <SourceBadge source="measured" />
                </label>
                <span className="text-xs text-ink-3">{it.data.rpm.length} points{it.data.boost ? " · with boost" : ""}</span>
              </li>
            ))}
            {items?.length === 0 && <li className="py-2 text-xs text-ink-3">No measurements yet.</li>}
          </ul>
        </Card>
        <Card title="Calibrate the model" subtitle="Fit model parameters so the simulation reproduces your measurement. The fitted values carry their own uncertainty.">
          {!m ? (
            <Empty title="Add a measurement first" />
          ) : (
            <div className="space-y-2">
              <div className="grid gap-1 sm:grid-cols-2">
                {(meta?.calibratable ?? []).map((p) => (
                  <label key={p} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={params.includes(p)} onChange={(e) => setParams(e.target.checked ? [...params, p] : params.filter((x) => x !== p))} />
                    {meta?.params.find((s) => s.path === p)?.label ?? p}
                  </label>
                ))}
              </div>
              <Button variant="primary" onClick={calibrate} disabled={!params.length} loading={act.busy}>Calibrate to “{m.name}”</Button>
            </div>
          )}
        </Card>
      </div>
      {cal && (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            <LineChartBands
              title="Torque: measured vs model"
              subtitle={`RMS error ${fmt(cal.torque_rmse_before, 1)} → ${fmt(cal.torque_rmse_after, 1)} N·m`}
              x={cal.curves.rpm as number[]}
              xLabel="Engine speed"
              xUnit="rpm"
              unit="N·m"
              syncId="cal"
              series={[
                { id: "meas", label: "Measured", color: "var(--s2)", values: cal.curves.torque_measured as number[] },
                { id: "before", label: "Model before", color: "var(--s3)", values: cal.curves.torque_before as number[], dashed: true },
                { id: "after", label: "Model calibrated", color: "var(--s1)", values: cal.curves.torque_after as number[] },
              ]}
            />
            {cal.curves.boost_measured && (
              <LineChartBands
                title="Boost: measured vs model"
                x={cal.curves.rpm as number[]}
                xLabel="Engine speed"
                xUnit="rpm"
                unit="bar"
                syncId="cal"
                series={[
                  { id: "meas", label: "Measured", color: "var(--s2)", values: cal.curves.boost_measured as number[] },
                  { id: "before", label: "Model before", color: "var(--s3)", values: cal.curves.boost_before as number[], dashed: true },
                  { id: "after", label: "Model calibrated", color: "var(--s1)", values: cal.curves.boost_after as number[] },
                ]}
              />
            )}
          </div>
          <Card title="Fitted parameters" actions={<Button variant="primary" size="sm" onClick={apply} loading={act.busy}>Save calibrated design as a new version</Button>}>
            <table className="w-full text-sm tabular">
              <tbody>
                {cal.parameters.map((p) => (
                  <tr key={p.path} className="border-t border-line">
                    <td className="py-1.5">{p.label}</td>
                    <td className="py-1.5 text-right">{fmt(p.before, 3)} → <span className="font-medium">{fmt(p.after, 3)}</span> ± {fmt(p.ci95, 3)} {p.unit !== "-" && p.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cal.warnings.map((w) => <div key={w} className="mt-2"><Note tone="warning">{w}</Note></div>)}
            {cal.notes.map((n) => <p key={n} className="mt-2 text-xs text-ink-3">{n}</p>)}
            <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-3">
              <label className="flex items-center gap-2 text-xs text-ink-2">
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                Share these fitted values anonymously (engine size, compression, boost and fuel only; no names or raw data) to improve defaults for everyone.
              </label>
              <Button size="sm" onClick={share} disabled={!consent || shared} loading={act.busy}>
                <Share2 className="size-3.5" /> {shared ? "Shared, thank you" : "Share"}
              </Button>
            </div>
          </Card>
        </>
      )}
      <Card title={<span className="inline-flex items-center gap-1.5"><Sparkles className="size-4" /> Learned from real engines</span>} subtitle={suggest?.note}>
        {!suggest || suggest.suggestions.length === 0 ? (
          <p className="text-sm text-ink-2">
            Not enough similar shared calibrations yet ({suggest?.total_records ?? 0} in total). Suggestions appear once at least three comparable real engines are available.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {suggest.suggestions.map((s) => {
              const cur = getAt(state.design, s.path) as Param | undefined;
              return (
                <li key={s.path} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                  <span>{s.label}</span>
                  <span className="text-xs text-ink-2">
                    yours {fmt(cur?.value, 3)} · learned <span className="font-medium text-ink">{fmt(s.value, 3)} ± {fmt(s.tol, 3)}</span> from ≈{fmt(s.n_effective, 0)} engines
                  </span>
                  <Button size="sm" onClick={() => applySuggestion(s)}>Use</Button>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
