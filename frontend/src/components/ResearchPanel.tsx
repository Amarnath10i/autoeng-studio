"use client";

import { ExternalLink, Globe } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, ErrorNote, Input, Note, Select, Spinner, useAsync } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Material, Source } from "@/lib/types";

interface Candidate {
  key: string;
  label: string;
  value: number;
  unit: string;
  value_min: number | null;
  value_max: number | null;
  condition: string;
  source_kind: "manufacturer" | "literature" | "unknown";
  source_title: string;
  source_url: string;
  quote: string;
  confidence: "high" | "medium" | "low";
  url_verified: boolean;
}

export interface ResearchRow {
  id: string;
  kind: string;
  query: string;
  status: "running" | "done" | "failed";
  error: string | null;
  result: {
    summary: string;
    items: { name: string; category: string; condition: string; properties: Candidate[] }[];
    caveats: string[];
    notice: string;
  } | null;
}

/**
 * Search the web for a material (or part) and turn reviewed, cited values into a library material.
 * Nothing is saved until the user ticks values and presses Save.
 */
export function ResearchPanel({
  initialQuery = "",
  kind: fixedKind,
  onSaved,
}: {
  initialQuery?: string;
  kind?: "material" | "part";
  onSaved?: (m: Material) => void;
}) {
  const { meta, health, reloadMaterials } = useSession();
  const [query, setQuery] = useState(initialQuery);
  const [kind, setKind] = useState<"material" | "part">(fixedKind ?? "material");
  const [research, setResearch] = useState<ResearchRow | null>(null);
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  const act = useAsync();
  const props = meta?.material_properties ?? {};

  useEffect(() => {
    if (!research || research.status !== "running") return;
    const t = setTimeout(async () => setResearch(await api<ResearchRow>(`/api/v1/research/${research.id}`)), 2500);
    return () => clearTimeout(t);
  }, [research]);

  if (!health?.research_available) {
    return (
      <Note>
        Web search for materials and parts is switched off on this server. Add a research API key as
        <code className="mx-1">AUTOENG_RESEARCH_API_KEY</code>
        in the backend environment and restart it. Until then, add the values yourself as a custom material with their
        source.
      </Note>
    );
  }

  const start = () =>
    act.run(async () => {
      const r = await api<ResearchRow>("/api/v1/research", { method: "POST", json: { kind, query } });
      // Tick high/medium-confidence values with verified URLs by default; the user reviews them all.
      setAccepted({});
      setResearch(r);
    });

  const save = (item: NonNullable<ResearchRow["result"]>["items"][number]) =>
    act.run(async () => {
      const properties: Record<string, { value: number; tol: number; source: Source; ref: string }> = {};
      item.properties.forEach((p, i) => {
        if (!accepted[`${item.name}-${i}`] || !(p.key in props) || properties[p.key]) return;
        const tol = p.value_min != null && p.value_max != null ? (p.value_max - p.value_min) / 2 : Math.abs(p.value) * 0.05;
        properties[p.key] = {
          value: p.value,
          tol: +tol.toPrecision(3),
          source: p.source_kind === "unknown" ? "unknown" : p.source_kind,
          ref: `${p.source_title} — ${p.source_url}${p.url_verified ? "" : " (URL not among retrieved pages)"}; reviewed by user`,
        };
      });
      if (!Object.keys(properties).length) throw new Error("Tick at least one value to save");
      const m = await api<Material>("/api/v1/materials", {
        method: "POST",
        json: {
          name: item.name,
          category: item.category || "Custom",
          condition: item.condition,
          properties,
          notes: "Values found by web research and reviewed before saving.",
        },
      });
      await reloadMaterials();
      onSaved?.(m);
    });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {!fixedKind && (
          <Select value={kind} onChange={(e) => setKind(e.target.value as "material" | "part")} className="w-32">
            <option value="material">Material</option>
            <option value="part">Part</option>
          </Select>
        )}
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && query.trim().length > 2 && start()}
          placeholder={kind === "material" ? "e.g. Inconel 718 aged, CFRP T700 quasi-isotropic" : "e.g. turbocharger model, clutch kit"}
          className="min-w-[240px] flex-1"
        />
        <Button variant="primary" onClick={start} disabled={query.trim().length < 3} loading={act.busy || research?.status === "running"}>
          <Globe className="size-3.5" aria-hidden /> Search the web
        </Button>
      </div>
      <ErrorNote error={act.error} onClose={() => act.setError(null)} />
      {research?.status === "running" && <Spinner label="Searching sources and extracting values" />}
      {research?.status === "failed" && <ErrorNote error={research.error} />}
      {research?.result && (
        <div className="space-y-4">
          <p className="text-sm text-ink-2">{research.result.summary}</p>
          <Note tone="warning">{research.result.notice}</Note>
          {research.result.items.map((item) => (
            <div key={item.name} className="border border-line p-4">
              <div className="display text-sm">
                {item.name} <span className="ml-1 normal-case tracking-normal text-ink-3">{item.condition}</span>
              </div>
              <ul className="mt-3 space-y-3">
                {item.properties.map((p, i) => (
                  <li key={i} className="text-sm">
                    <label className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={!!accepted[`${item.name}-${i}`]}
                        disabled={!(p.key in props)}
                        onChange={(e) => setAccepted({ ...accepted, [`${item.name}-${i}`]: e.target.checked })}
                      />
                      <span className="flex-1">
                        <span className="text-ink">{p.label}</span>: <span className="tabular">{p.value} {p.unit}</span>
                        {p.value_min != null && p.value_max != null && (
                          <span className="text-ink-3"> (range {p.value_min}–{p.value_max})</span>
                        )}
                        <span className="ml-2 text-xs text-ink-3">{p.condition} · confidence {p.confidence}</span>
                        <span className="mt-0.5 block text-xs italic text-ink-2">“{p.quote}”</span>
                        <a href={p.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-ink underline-offset-4 hover:underline">
                          {p.source_title || p.source_url} <ExternalLink className="size-3" />
                        </a>
                        {!p.url_verified && <span className="ml-2 text-xs text-[var(--critical)]">Source not among retrieved pages: verify</span>}
                        {!(p.key in props) && <span className="ml-2 text-xs text-ink-3">(not a library property yet)</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
              {kind === "material" && (
                <Button className="mt-4" size="sm" variant="primary" onClick={() => save(item)} loading={act.busy}>
                  Save ticked values as a material
                </Button>
              )}
            </div>
          ))}
          {research.result.caveats.map((c) => (
            <p key={c} className="text-xs text-ink-3">{c}</p>
          ))}
        </div>
      )}
    </div>
  );
}
