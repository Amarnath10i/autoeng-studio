"use client";

import { ArrowRight, ArrowUpRight, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Backdrop, CoupeLineArt, EngineLineArt } from "@/components/brand";
import { Button, Empty, ErrorNote, Field, Input, SectionTitle, Segmented, Select, Spinner, useAsync } from "@/components/ui";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Project } from "@/lib/types";

function Figure({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="border-t border-line-strong pt-4">
      <div className="eyebrow">{label}</div>
      <div className="mt-2 text-3xl font-extralight tracking-tight text-ink">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-3">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { meta, user, health, materials } = useSession();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [kind, setKind] = useState<"vehicle" | "engine">("vehicle");
  const [template, setTemplate] = useState("");
  const [name, setName] = useState("");
  const list = useAsync();
  const create = useAsync();

  useEffect(() => {
    list.run(async () => setProjects(await api<Project[]>("/api/v1/projects")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const templates = kind === "vehicle" ? meta?.vehicle_templates ?? [] : meta?.engine_presets ?? [];
  const chosen = template || templates[0]?.id || "";

  const createProject = (k: "vehicle" | "engine", t: string, projectName?: string) =>
    create.run(async () => {
      const design = await api<Record<string, unknown>>(`/api/v1/presets/${k}/${t}`);
      const n = projectName?.trim() || String(design.name);
      design.name = n;
      const p = await api<Project>("/api/v1/projects", {
        method: "POST",
        json: { name: n, kind: k, design, description: String(design.description ?? "") },
      });
      router.push(`/projects/${p.id}`);
    });

  const remove = (p: Project) => {
    if (!confirm(`Delete "${p.name}" and its whole history? This cannot be undone.`)) return;
    list.run(async () => {
      await api(`/api/v1/projects/${p.id}`, { method: "DELETE" });
      setProjects((ps) => ps?.filter((x) => x.id !== p.id) ?? null);
    });
  };

  const firstVehicle = meta?.vehicle_templates.find((t) => t.id !== "blank")?.id ?? "generic_hatch";
  const firstEngine = meta?.engine_presets[0]?.id ?? "generic_2l_turbo";

  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-line">
        <Backdrop />
        <div className="relative mx-auto grid max-w-[1680px] gap-10 px-6 pb-14 pt-16 lg:grid-cols-[1fr_1.15fr] lg:px-10 lg:pt-24">
          <div className="flex flex-col justify-center">
            <div className="eyebrow rise">Welcome{user?.name ? `, ${user.name}` : ""}</div>
            <h1 className="rise mt-5 font-display text-5xl font-light uppercase leading-[0.95] tracking-[0.04em] sm:text-6xl xl:text-7xl" style={{ animationDelay: "0.08s" }}>
              Build it.
              <br />
              <span className="text-ink-2">Prove it.</span>
            </h1>
            <p className="rise mt-6 max-w-xl text-[15px] leading-relaxed text-ink-2" style={{ animationDelay: "0.16s" }}>
              Design a complete vehicle or a single engine, drive it through heat, altitude and track days, and see what
              fails first, with the uncertainty stated and every number traced to its source.
            </p>
            <div className="rise mt-9 flex flex-wrap gap-3" style={{ animationDelay: "0.24s" }}>
              <Button variant="primary" size="lg" onClick={() => createProject("vehicle", firstVehicle)} loading={create.busy}>
                New vehicle <ArrowRight className="size-4" aria-hidden />
              </Button>
              <Button size="lg" onClick={() => createProject("engine", firstEngine)} disabled={create.busy}>
                Open engine lab
              </Button>
            </div>
            <ErrorNote error={create.error} />
          </div>
          <div className="flex items-center">
            <CoupeLineArt className="w-full text-ink" />
          </div>
        </div>
        <div className="relative mx-auto grid max-w-[1680px] grid-cols-2 gap-8 px-6 pb-12 md:grid-cols-4 lg:px-10">
          <Figure label="Projects" value={projects ? String(projects.length) : "–"} sub="Every one version-controlled" />
          <Figure
            label="Compute"
            value={health?.compute.gpu_available ? "GPU" : "CPU"}
            sub={health?.compute.gpu_available ? "Server GPU ready" : "Pair your own GPU under Compute"}
          />
          <Figure label="Physics models" value="4" sub="Engine · structure · vehicle · thermal" />
          <Figure label="Materials" value={String(materials.length)} sub="Each value with its source" />
        </div>
      </section>

      <div className="mx-auto max-w-[1680px] space-y-16 px-6 py-14 lg:px-10">
        {/* Projects */}
        <section className="space-y-8">
          <SectionTitle eyebrow="Garage" title="Your projects" />
          <ErrorNote error={list.error} />
          {!projects && <Spinner />}
          {projects && projects.length === 0 && (
            <Empty title="Your garage is empty">Start a vehicle or an engine above, or configure one below.</Empty>
          )}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {projects?.map((p) => (
              <div key={p.id} className="group relative border border-line bg-surface transition-colors hover:border-line-strong hover:bg-surface-2">
                <Link href={`/projects/${p.id}`} className="block p-7">
                  <div className="flex h-36 items-center justify-center text-ink-3 transition-colors group-hover:text-ink">
                    {p.kind === "vehicle" ? <CoupeLineArt animate={false} className="h-full" /> : <EngineLineArt className="h-full" />}
                  </div>
                  <div className="mt-6 flex items-end justify-between gap-3">
                    <div className="min-w-0">
                      <div className="eyebrow">{p.kind === "vehicle" ? "Vehicle" : "Engine"}</div>
                      <div className="display mt-2 truncate text-lg">{p.name}</div>
                      <div className="mt-1 text-xs text-ink-3">
                        {p.branches.length} branch{p.branches.length === 1 ? "" : "es"} · updated {timeAgo(p.updated_at)}
                      </div>
                    </div>
                    <ArrowUpRight className="size-5 shrink-0 text-ink-3 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-ink" strokeWidth={1.25} aria-hidden />
                  </div>
                </Link>
                <button
                  type="button"
                  onClick={() => remove(p)}
                  className="absolute right-4 top-4 text-ink-3 opacity-0 transition-opacity hover:text-[var(--critical)] focus:opacity-100 group-hover:opacity-100"
                  aria-label={`Delete ${p.name}`}
                >
                  <Trash2 className="size-4" strokeWidth={1.5} />
                </button>
              </div>
            ))}
          </div>
        </section>

        {/* Configure a new project */}
        <section className="space-y-8">
          <SectionTitle eyebrow="Configure" title="Start a new project" />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createProject(kind, chosen, name);
            }}
            className="grid items-end gap-6 border border-line bg-surface p-6 md:grid-cols-[auto_1fr_1fr_auto]"
          >
            <Field label="Design">
              <Segmented
                options={[
                  { id: "vehicle", label: "Vehicle" },
                  { id: "engine", label: "Engine" },
                ]}
                value={kind}
                onChange={(v) => {
                  setKind(v);
                  setTemplate("");
                }}
              />
            </Field>
            <Field label="Start from">
              <Select value={chosen} onChange={(e) => setTemplate(e.target.value)}>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Project name">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Track build 2027" />
            </Field>
            <Button type="submit" variant="primary" loading={create.busy}>
              Create <ArrowRight className="size-4" aria-hidden />
            </Button>
          </form>
          <p className="text-xs text-ink-3">
            Templates are illustrative, generic designs. Every value is labelled as an estimate until you replace it with
            measured or manufacturer data.
          </p>
        </section>
      </div>
    </div>
  );
}
