"use client";

import { GitBranch, GitCompare, GitMerge, History as HistoryIcon, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Button, Card, ErrorNote, Input, Note, Select, SourceBadge, StatusBadge, useAsync } from "@/components/ui";
import { api } from "@/lib/api";
import { fmt, num, pct, SOURCE_LABEL, timeAgo } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { LimitResult, Source, Trust, Version } from "@/lib/types";
import type { ProjectState } from "./useProject";

function valueText(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object" && v && "value" in v) {
    const p = v as { value: number; tol: number; source: string };
    return `${num(p.value)}${p.tol ? ` ± ${num(p.tol)}` : ""} [${SOURCE_LABEL[p.source as Source] ?? p.source}]`;
  }
  if (typeof v === "object") return JSON.stringify(v).slice(0, 120);
  return String(v);
}

interface Change {
  path: string;
  kind: string;
  before: unknown;
  after: unknown;
}

export function DiffTable({ changes }: { changes: Change[] }) {
  if (!changes.length) return <p className="text-sm text-ink-2">No differences.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-left text-ink-2">
          <tr>
            <th className="py-1 pr-3 font-medium">Parameter</th>
            <th className="py-1 pr-3 font-medium">Before</th>
            <th className="py-1 font-medium">After</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((c) => (
            <tr key={c.path} className="border-t border-line align-top">
              <td className="py-1 pr-3 font-mono text-[11px]">{c.path}</td>
              <td className="py-1 pr-3 text-ink-2">{valueText(c.before)}</td>
              <td className="py-1 text-ink">{valueText(c.after)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function HistoryPanel({ state }: { state: ProjectState }) {
  const { project, versions, branch, reload, head, dirty } = state;
  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");
  const [diff, setDiff] = useState<Change[] | null>(null);
  const [newBranch, setNewBranch] = useState("");
  const [mergeFrom, setMergeFrom] = useState("");
  const [conflicts, setConflicts] = useState<{ path: string; base: unknown; ours: unknown; theirs: unknown }[] | null>(null);
  const [resolutions, setResolutions] = useState<Record<string, "ours" | "theirs">>({});
  const act = useAsync();
  if (!project) return null;

  const compare = () =>
    act.run(async () => {
      const r = await api<{ changes: Change[] }>(`/api/v1/projects/${project.id}/diff?a=${a}&b=${b}`);
      setDiff(r.changes);
    });

  const revert = (v: Version) => {
    if (dirty && !confirm("You have unsaved changes; reverting discards them. Continue?")) return;
    act.run(async () => {
      await api(`/api/v1/projects/${project.id}/revert`, { method: "POST", json: { branch, version_id: v.id } });
      await reload(branch);
    });
  };

  const createBranch = () =>
    act.run(async () => {
      await api(`/api/v1/projects/${project.id}/branches`, {
        method: "POST",
        json: { name: newBranch.trim(), from_version_id: head?.id },
      });
      await reload(newBranch.trim());
      setNewBranch("");
    });

  const merge = (withResolutions?: Record<string, string>) =>
    act.run(async () => {
      try {
        await api(`/api/v1/projects/${project.id}/merge`, {
          method: "POST",
          json: { source: mergeFrom, target: branch, resolutions: withResolutions },
        });
        setConflicts(null);
        setResolutions({});
        await reload(branch);
      } catch (e) {
        const detail = (e as { detail?: { conflicts?: typeof conflicts } }).detail;
        if (detail?.conflicts) {
          setConflicts(detail.conflicts);
          setResolutions(Object.fromEntries(detail.conflicts.map((c) => [c.path, "ours"])));
          return;
        }
        throw e;
      }
    });

  const otherBranches = project.branches.filter((x) => x.name !== branch);

  return (
    <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
      <Card title={<span className="inline-flex items-center gap-1.5"><HistoryIcon className="size-4" /> Version history</span>} subtitle="Every saved state is kept. Reverting creates a new version; history is never rewritten.">
        <ol className="space-y-1">
          {versions.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-2">
              <span className="w-10 font-mono text-xs text-ink-3">v{v.number}</span>
              <span className="rounded bg-surface-3 px-1.5 text-[11px] text-ink-2">{v.branch}</span>
              {v.merge_parent_id && <GitMerge className="size-3.5 text-ink-3" aria-label="Merge" />}
              <span className="min-w-0 flex-1 truncate">{v.message}</span>
              <span className="text-xs text-ink-3">{timeAgo(v.created_at)}</span>
              {v.id === head?.id ? (
                <span className="text-xs font-medium text-accent">current</span>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => revert(v)} title={`Make v${v.number} the new head of ${branch}`}>
                  <RotateCcw className="size-3.5" /> Restore
                </Button>
              )}
            </li>
          ))}
        </ol>
      </Card>
      <div className="space-y-4">
        <ErrorNote error={act.error} onClose={() => act.setError(null)} />
        <Card title={<span className="inline-flex items-center gap-1.5"><GitCompare className="size-4" /> Compare versions</span>}>
          <div className="flex flex-wrap gap-2">
            {[a, b].map((val, i) => (
              <Select key={i} value={val} onChange={(e) => (i ? setB : setA)(e.target.value)} className="w-40" aria-label={i ? "Version B" : "Version A"}>
                <option value="">{i ? "Version B" : "Version A"}</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.number} · {v.message.slice(0, 30)}
                  </option>
                ))}
              </Select>
            ))}
            <Button size="sm" onClick={compare} disabled={!a || !b} loading={act.busy}>
              Compare
            </Button>
          </div>
          {diff && <div className="mt-3"><DiffTable changes={diff} /></div>}
        </Card>
        <Card title={<span className="inline-flex items-center gap-1.5"><GitBranch className="size-4" /> Branches</span>} subtitle="Branch to try an idea without touching the main design.">
          <div className="flex gap-2">
            <Input value={newBranch} onChange={(e) => setNewBranch(e.target.value.replace(/\s+/g, "-"))} placeholder="e.g. e85-experiment" />
            <Button size="sm" onClick={createBranch} disabled={!newBranch.trim()} loading={act.busy}>
              Create from current
            </Button>
          </div>
          {otherBranches.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              <Select value={mergeFrom} onChange={(e) => setMergeFrom(e.target.value)} className="w-48" aria-label="Branch to merge">
                <option value="">Merge a branch into {branch}…</option>
                {otherBranches.map((x) => (
                  <option key={x.name} value={x.name}>
                    {x.name}
                  </option>
                ))}
              </Select>
              <Button size="sm" onClick={() => merge()} disabled={!mergeFrom || dirty} loading={act.busy}>
                <GitMerge className="size-3.5" /> Merge
              </Button>
            </div>
          )}
          {dirty && <p className="mt-2 text-xs text-ink-3">Save or discard your changes before merging.</p>}
          {conflicts && (
            <div className="mt-3 space-y-2">
              <Note tone="warning">Both branches changed these parameters differently. Choose which value to keep.</Note>
              {conflicts.map((c) => (
                <div key={c.path} className="border border-line p-2 text-xs">
                  <div className="font-mono text-[11px]">{c.path}</div>
                  <div className="mt-1 grid grid-cols-2 gap-2">
                    {(["ours", "theirs"] as const).map((side) => (
                      <label key={side} className="flex items-start gap-1.5">
                        <input type="radio" checked={resolutions[c.path] === side} onChange={() => setResolutions({ ...resolutions, [c.path]: side })} />
                        <span>
                          <span className="font-medium">{side === "ours" ? branch : mergeFrom}:</span> {valueText(c[side])}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
              <Button size="sm" variant="primary" onClick={() => merge(resolutions)} loading={act.busy}>
                Merge with these choices
              </Button>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export function LimitsTable({ limits, componentName }: { limits: LimitResult[]; componentName: (id: string) => string }) {
  const order = ["failure", "critical", "warning", "no_data", "ok"];
  const sorted = [...limits].sort((x, y) => order.indexOf(x.status) - order.indexOf(y.status));
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-sm">
        <thead className="text-left text-xs text-ink-2">
          <tr className="border-b border-line">
            <th className="py-2 pr-3 font-medium">Status</th>
            <th className="py-2 pr-3 font-medium">Component · check</th>
            <th className="py-2 pr-3 text-right font-medium">Load (nominal / 95 %)</th>
            <th className="py-2 pr-3 text-right font-medium">Allowable</th>
            <th className="py-2 pr-3 text-right font-medium">Safety factor (nom / 5 %)</th>
            <th className="py-2 pr-3 text-right font-medium">P(exceed)</th>
            <th className="py-2 font-medium">Where</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {sorted.map((r) => (
            <tr key={`${r.component}-${r.id}`} className="border-b border-line align-top">
              <td className="py-2 pr-3"><StatusBadge status={r.status} /></td>
              <td className="py-2 pr-3">
                <div className="text-ink">{r.label}</div>
                <div className="text-xs text-ink-3">{componentName(r.component)}</div>
                {r.note && <div className="text-xs text-ink-3">{r.note}</div>}
              </td>
              <td className="py-2 pr-3 text-right">
                {num(r.actual_nominal)} / {num(r.actual_p95)} <span className="text-ink-3">{r.unit}</span>
              </td>
              <td className="py-2 pr-3 text-right">
                {num(r.allowable_nominal)} <span className="text-ink-3">{r.unit}</span>
                {r.allowable_source && (
                  <div className="mt-0.5"><SourceBadge source={r.allowable_source as Source} reference={r.allowable_ref} /></div>
                )}
              </td>
              <td className="py-2 pr-3 text-right">
                {fmt(r.sf_nominal, 2)} / {fmt(r.sf_p05, 2)}
              </td>
              <td className="py-2 pr-3 text-right">{pct(r.p_exceed, 1)}</td>
              <td className="py-2 text-xs text-ink-2">{r.at_rpm ? `${fmt(r.at_rpm, 0)} rpm` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TrustPanel({ trust, compute }: { trust: Trust; compute?: { backend: string; device: string } }) {
  const { meta } = useSession();
  const label = (path: string) => meta?.params.find((p) => p.path === path)?.label ?? path;
  const assumptions = Array.isArray(trust.assumptions) ? { model: trust.assumptions } : trust.assumptions;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Where these results come from" subtitle={trust.disclaimer}>
        <div className="space-y-3 text-sm">
          <div>
            <div className="text-xs font-medium text-ink-2">Models</div>
            <ul className="mt-1 space-y-1">
              {trust.models.map((m) => (
                <li key={m.id}>
                  {m.name} <span className="text-ink-3">· {m.id} v{m.version} · fidelity level {m.fidelity_level}</span>
                </li>
              ))}
            </ul>
          </div>
          {trust.uncertainty && (
            <div>
              <div className="text-xs font-medium text-ink-2">Uncertainty</div>
              <p className="mt-1">
                {trust.uncertainty.method} · {trust.uncertainty.samples} samples · seed {trust.uncertainty.seed}
                {trust.uncertainty.uncertain_inputs && ` · ${trust.uncertainty.uncertain_inputs.length} uncertain inputs`}
              </p>
              <p className="text-xs text-ink-3">{trust.uncertainty.note}</p>
            </div>
          )}
          <div>
            <div className="text-xs font-medium text-ink-2">Validation</div>
            <p className="mt-1">{trust.validation?.status === "unvalidated" ? "Not yet validated against measurements for this design." : trust.validation?.status}</p>
          </div>
          {compute && (
            <div>
              <div className="text-xs font-medium text-ink-2">Computed on</div>
              <p className="mt-1">{compute.device} ({compute.backend})</p>
            </div>
          )}
          {trust.inputs_by_source && (
            <div>
              <div className="text-xs font-medium text-ink-2">Inputs by data source</div>
              <div className="mt-1 space-y-1.5">
                {Object.entries(trust.inputs_by_source).map(([source, paths]) => (
                  <details key={source} className="text-xs">
                    <summary className="cursor-pointer">
                      <SourceBadge source={source as Source} /> <span className="ml-1 text-ink-2">{paths.length} inputs</span>
                    </summary>
                    <ul className="ml-4 mt-1 list-disc text-ink-2">
                      {paths.map((p) => <li key={p}>{label(p)}</li>)}
                    </ul>
                  </details>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>
      <Card title="Assumptions and limitations">
        {Object.entries(assumptions).map(([k, list]) => (
          <div key={k} className="mb-3">
            {Object.keys(assumptions).length > 1 && <div className="text-xs font-medium capitalize text-ink-2">{k}</div>}
            <ul className="ml-4 mt-1 list-disc space-y-1 text-sm text-ink-2">
              {list.map((a) => <li key={a}>{a}</li>)}
            </ul>
          </div>
        ))}
        {trust.not_modelled && (
          <>
            <div className="mt-2 text-xs font-medium text-ink-2">Not modelled yet</div>
            <ul className="ml-4 mt-1 list-disc space-y-1 text-sm text-ink-2">
              {trust.not_modelled.map((a) => <li key={a}>{a}</li>)}
            </ul>
          </>
        )}
      </Card>
    </div>
  );
}
