"use client";

import { Globe, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Container, Figures, PageHero } from "@/components/layout";
import { ResearchPanel } from "@/components/ResearchPanel";
import { Button, Card, ErrorNote, Field, Input, Select, SourceBadge, useAsync } from "@/components/ui";
import { api } from "@/lib/api";
import { num, SOURCE_LABEL } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Material, Source } from "@/lib/types";

type Draft = { name: string; category: string; condition: string; props: Record<string, { value: string; tol: string; source: Source; ref: string }> };

const emptyDraft = (): Draft => ({ name: "", category: "", condition: "", props: {} });

export default function MaterialsPage() {
  const { meta, materials, reloadMaterials } = useSession();
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [system, setSystem] = useState("all");
  const [query, setQuery] = useState("");
  const act = useAsync();
  const props = meta?.material_properties ?? {};

  const save = () =>
    act.run(async () => {
      const properties = Object.fromEntries(
        Object.entries(draft.props)
          .filter(([, v]) => v.value !== "")
          .map(([k, v]) => [k, { value: Number(v.value), tol: Number(v.tol) || 0, source: v.source, ref: v.ref || null }]),
      );
      await api("/api/v1/materials", {
        method: "POST",
        json: { name: draft.name, category: draft.category, condition: draft.condition, properties },
      });
      await reloadMaterials();
      setDraft(emptyDraft());
    });

  const remove = (m: Material) =>
    act.run(async () => {
      if (!confirm(`Delete custom material "${m.name}"?`)) return;
      await api(`/api/v1/materials/${m.id}`, { method: "DELETE" });
      await reloadMaterials();
    });

  const setProp = (k: string, patch: Partial<Draft["props"][string]>) =>
    setDraft({
      ...draft,
      props: { ...draft.props, [k]: { ...(draft.props[k] ?? { value: "", tol: "0", source: "user" as Source, ref: "" }), ...patch } },
    });

  const custom = materials.filter((m) => m.custom).length;
  const systems = meta?.material_systems ?? {};
  const shown = materials.filter(
    (m) =>
      (system === "all" || (m.uses ?? []).includes(system) || (system === "custom" && m.custom)) &&
      (!query || `${m.name} ${m.category} ${m.condition} ${m.notes}`.toLowerCase().includes(query.toLowerCase())),
  );
  return (
    <div>
      <PageHero
        eyebrow="Library"
        title="Materials"
        description="Independent of any part: every component can use any material. Each property carries its source and uncertainty, and missing values stay empty rather than guessed."
      >
        <Figures
          items={[
            { label: "Materials", value: String(materials.length), sub: `${custom} of your own` },
            { label: "Vehicle systems", value: String(Object.keys(systems).length), sub: "Engine to glazing, each material tagged" },
            { label: "Properties tracked", value: String(Object.keys(props).length), sub: "Mechanical, thermal, friction" },
            { label: "Web research", value: "Cited", sub: "Reviewed before it enters the library" },
          ]}
        />
      </PageHero>
      <Container className="space-y-12 py-12">
      <ErrorNote error={act.error} onClose={() => act.setError(null)} />

      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {[["all", "All"], ...Object.entries(systems), ["custom", "Your materials"]].map(([id, label]) => {
            const n = id === "all" ? materials.length : id === "custom" ? custom : materials.filter((m) => (m.uses ?? []).includes(id)).length;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setSystem(id)}
                aria-pressed={system === id}
                className={`border px-3 py-1.5 text-xs transition-colors ${system === id ? "border-[var(--ink)] text-ink" : "border-line text-ink-2 hover:border-line-strong hover:text-ink"}`}
              >
                {label} <span className="ml-1 text-ink-3 tabular">{n}</span>
              </button>
            );
          })}
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name, grade, use…" className="ml-auto h-9 w-64" />
        </div>
      <div className="overflow-x-auto border border-line bg-surface">
        <table className="w-full min-w-[1100px] text-sm tabular">
          <thead>
            <tr className="border-b border-line">
              <th className="eyebrow px-4 py-3 text-left font-medium">Material</th>
              {Object.entries(props).map(([k, p]) => (
                <th key={k} className="px-3 py-3 text-right align-bottom">
                  <div className="eyebrow">{p.label}</div>
                  <div className="text-[10px] text-ink-3">{p.unit}</div>
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {shown.map((m) => (
              <tr key={m.id} className="border-b border-line align-top transition-colors hover:bg-surface-2">
                <td className="min-w-[19rem] px-4 py-3">
                  <div className="display text-[13px]">{m.name}</div>
                  <div className="text-xs text-ink-3" title={m.notes || undefined}>
                    {m.category} · {m.condition}
                    {m.custom && " · custom"}
                  </div>
                  {m.notes && <div className="mt-1 max-w-[19rem] text-[11px] leading-snug text-ink-3">{m.notes}</div>}
                </td>
                {Object.keys(props).map((k) => {
                  const p = m.properties[k];
                  return (
                    <td key={k} className="px-3 py-3 text-right">
                      {p ? (
                        <>
                          {num(p.value)}
                          {p.tol ? <span className="text-ink-3"> ±{num(p.tol)}</span> : null}
                          <div className="mt-1">
                            <SourceBadge source={p.source} reference={p.ref} />
                          </div>
                        </>
                      ) : (
                        <span className="text-ink-3" title="No reliable data: checks that need it report 'no data'">
                          —
                        </span>
                      )}
                    </td>
                  );
                })}
                <td className="px-3 py-3">
                  {m.custom && (
                    <button type="button" onClick={() => remove(m)} className="text-ink-3 hover:text-[var(--critical)]" aria-label={`Delete ${m.name}`}>
                      <Trash2 className="size-4" strokeWidth={1.5} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown.length === 0 && <p className="text-sm text-ink-3">No materials match.</p>}
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card
          title={
            <span className="inline-flex items-center gap-2">
              <Globe className="size-4" strokeWidth={1.5} /> Find a material on the web
            </span>
          }
          subtitle="Searches datasheets, standards and handbooks for the material's properties and returns cited values. Tick the ones you trust and save; they can then be tested in any part."
        >
          <ResearchPanel />
        </Card>

        <Card
          title={
            <span className="inline-flex items-center gap-2">
              <Plus className="size-4" strokeWidth={1.5} /> Define a material
            </span>
          }
          subtitle="For experimental or supplier materials. Record where each value came from."
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Name">
              <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </Field>
            <Field label="Category">
              <Input value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} placeholder="Steel, composite…" />
            </Field>
            <Field label="Condition">
              <Input value={draft.condition} onChange={(e) => setDraft({ ...draft, condition: e.target.value })} placeholder="Heat treatment, layup…" />
            </Field>
          </div>
          <div className="mt-5 space-y-2">
            {Object.entries(props).map(([k, p]) => {
              const v = draft.props[k];
              return (
                <div key={k} className="grid grid-cols-[1.5fr_1fr_0.7fr_1fr] items-center gap-2">
                  <span className="text-xs text-ink-2">
                    {p.label} <span className="text-ink-3">({p.unit})</span>
                  </span>
                  <Input type="number" value={v?.value ?? ""} onChange={(e) => setProp(k, { value: e.target.value })} aria-label={p.label} />
                  <Input type="number" min={0} value={v?.tol ?? ""} placeholder="±" onChange={(e) => setProp(k, { tol: e.target.value })} aria-label={`${p.label} uncertainty`} />
                  <Select value={v?.source ?? "user"} onChange={(e) => setProp(k, { source: e.target.value as Source })} aria-label={`${p.label} source`}>
                    {(["measured", "manufacturer", "literature", "user", "estimated", "unknown"] as Source[]).map((s) => (
                      <option key={s} value={s}>
                        {SOURCE_LABEL[s]}
                      </option>
                    ))}
                  </Select>
                </div>
              );
            })}
          </div>
          <Button variant="primary" className="mt-5" onClick={save} loading={act.busy} disabled={!draft.name || !draft.category}>
            Save material
          </Button>
        </Card>
      </div>
      </Container>
    </div>
  );
}
