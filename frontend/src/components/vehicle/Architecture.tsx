"use client";

import clsx from "clsx";
import { Link2, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { EngineEditor } from "@/components/engine/EngineEditor";
import type { Level } from "@/components/engine/ParamEditor";
import { Button, Card, Field, Input, Note, Select, SourceBadge, StatusBadge, inputClass } from "@/components/ui";
import { SOURCE_LABEL } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { CatalogType, ComponentInstance, Json, Param, Source, Status, VehicleDesign } from "@/lib/types";

const KIND_COLOR: Record<string, string> = {
  rotation: "var(--s1)",
  air: "var(--s2)",
  coolant: "var(--s3)",
  fuel: "var(--s4)",
  ac: "var(--s5)",
  exhaust: "var(--s8)",
  dc: "var(--s7)",
  mount: "var(--ink-3)",
  road: "var(--ink-3)",
  signal: "var(--ink-3)",
};

const CATEGORY_ORDER = ["Powertrain", "Electric powertrain", "Driveline", "Chassis", "Thermal", "Fuel", "Body"];

// Labels and units for vehicle component parameters (engine parameters come from the engine registry).
const FIELD: Record<string, { label: string; unit: string; help?: string }> = {
  torque_capacity: { label: "Torque capacity", unit: "N·m" },
  launch_rpm: { label: "Launch rpm", unit: "rpm", help: "Engine speed held while the clutch slips at launch" },
  mass: { label: "Mass", unit: "kg" },
  ratios: { label: "Gear ratios (1st first)", unit: "" },
  efficiency: { label: "Efficiency", unit: "-" },
  input_torque_rating: { label: "Input torque rating", unit: "N·m" },
  shift_time: { label: "Shift time", unit: "s" },
  ratio: { label: "Final drive ratio", unit: "-" },
  axle_torque_rating: { label: "Axle torque rating", unit: "N·m" },
  rolling_radius: { label: "Rolling radius", unit: "m" },
  rolling_resistance: { label: "Rolling resistance coefficient", unit: "-" },
  peak_friction: { label: "Peak tyre friction μ (dry)", unit: "-" },
  driven_axle: { label: "Driven axle", unit: "" },
  drag_coefficient: { label: "Drag coefficient Cd", unit: "-" },
  frontal_area: { label: "Frontal area", unit: "m²" },
  wheelbase: { label: "Wheelbase", unit: "m" },
  cg_height: { label: "Centre-of-gravity height", unit: "m" },
  front_weight_fraction: { label: "Weight on front axle", unit: "-" },
  rated_heat_rejection: { label: "Rated heat rejection", unit: "kW" },
  rated_delta_t: { label: "…at coolant − air ΔT", unit: "K" },
  rated_airspeed: { label: "…at airspeed", unit: "km/h" },
  fan_airflow_fraction: { label: "Fan airflow at standstill", unit: "share" },
  airflow_exponent: { label: "Airflow exponent", unit: "-" },
  circuit_thermal_capacity: { label: "Engine + coolant thermal mass", unit: "kJ/K" },
  thermostat_open: { label: "Thermostat opens", unit: "°C" },
  thermostat_full_open: { label: "Thermostat fully open", unit: "°C" },
  max_coolant_temp: { label: "Max coolant temperature", unit: "°C" },
  disc_material_id: { label: "Disc material", unit: "" },
  disc_mass: { label: "Disc mass (each)", unit: "kg" },
  disc_cooling_area: { label: "Disc cooling area (each)", unit: "m²" },
  front_bias: { label: "Front brake bias", unit: "share" },
  h_standstill: { label: "Convection at rest", unit: "W/(m²·K)" },
  h_speed_coeff: { label: "Convection speed coefficient", unit: "W/(m²·K)/(m/s)^0.8" },
  emissivity: { label: "Disc emissivity", unit: "-" },
  max_disc_temp: { label: "Max disc temperature (fade)", unit: "°C" },
};

function isParam(v: unknown): v is Param {
  return typeof v === "object" && v !== null && "value" in v && "source" in v;
}

export function VehicleGraph({
  design,
  selected,
  onSelect,
  status,
}: {
  design: VehicleDesign;
  selected: string | null;
  onSelect: (id: string) => void;
  status: Record<string, Status>;
}) {
  const { meta } = useSession();
  const cat = (t: string) => meta?.catalog.find((c) => c.id === t);
  const layout = useMemo(() => {
    const cols = new Map<string, string[]>();
    for (const [id, c] of Object.entries(design.components)) {
      const k = cat(c.type)?.category ?? "Other";
      cols.set(k, [...(cols.get(k) ?? []), id]);
    }
    const ordered = [...cols.keys()].sort((a, b) => (CATEGORY_ORDER.indexOf(a) + 99) % 99 - (CATEGORY_ORDER.indexOf(b) + 99) % 99);
    const pos: Record<string, { x: number; y: number }> = {};
    ordered.forEach((k, ci) => cols.get(k)!.forEach((id, ri) => (pos[id] = { x: 20 + ci * 190, y: 40 + ri * 78 })));
    const h = Math.max(...[...cols.values()].map((v) => v.length)) * 78 + 50;
    return { pos, ordered, width: ordered.length * 190 + 20, height: h };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [design.components, meta]);

  const W = 160;
  const H = 52;
  const kinds = new Set<string>();
  return (
    <div className="overflow-x-auto border border-line bg-surface p-2">
      <svg width={Math.max(layout.width, 400)} height={layout.height} role="img" aria-label="Vehicle architecture graph">
        {layout.ordered.map((k, i) => (
          <text key={k} x={20 + i * 190} y={22} className="fill-[var(--ink-3)] text-[11px] font-medium uppercase tracking-wide">
            {k}
          </text>
        ))}
        {design.connections.map((c, i) => {
          const [a, pa] = c.source.split(".");
          const [b] = c.target.split(".");
          const A = layout.pos[a];
          const B = layout.pos[b];
          if (!A || !B) return null;
          const kind = cat(design.components[a]?.type)?.ports.find((p) => p.name === pa)?.kind ?? "mount";
          kinds.add(kind);
          const x1 = A.x + W / 2;
          const y1 = A.y + H / 2;
          const x2 = B.x + W / 2;
          const y2 = B.y + H / 2;
          const mx = (x1 + x2) / 2;
          return (
            <path
              key={i}
              d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
              fill="none"
              stroke={KIND_COLOR[kind] ?? "var(--ink-3)"}
              strokeWidth={kind === "mount" ? 1 : 2}
              strokeDasharray={kind === "mount" ? "3 3" : undefined}
              opacity={0.9}
            >
              <title>{`${c.source} → ${c.target} (${kind})`}</title>
            </path>
          );
        })}
        {Object.entries(design.components).map(([id, c]) => {
          const p = layout.pos[id];
          const t = cat(c.type);
          const st = status[id];
          return (
            <g key={id} transform={`translate(${p.x},${p.y})`} onClick={() => onSelect(id)} className="cursor-pointer" role="button" aria-label={`Select ${c.name || id}`}>
              <rect
                width={W}
                height={H}
                rx={2}
                fill="var(--surface)"
                stroke={selected === id ? "var(--accent)" : "var(--axis)"}
                strokeWidth={selected === id ? 2 : 1}
                strokeDasharray={t?.status === "planned" ? "4 3" : undefined}
              />
              {st && st !== "unchecked" && (
                <circle cx={W - 12} cy={12} r={5} fill={st === "ok" ? "var(--good)" : st === "warning" ? "var(--warning)" : st === "critical" ? "var(--serious)" : st === "failure" ? "var(--critical)" : "var(--ink-3)"}>
                  <title>{st}</title>
                </circle>
              )}
              <text x={10} y={21} className="fill-[var(--ink)] text-[12px] font-medium tracking-wide">
                {(c.name || id).slice(0, 22)}
              </text>
              <text x={10} y={38} className="fill-[var(--ink-3)] text-[11px]">
                {(t?.name ?? c.type).slice(0, 24)}
                {t?.status === "planned" ? " · planned" : ""}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-3 px-2 pb-1 text-[11px] text-ink-2">
        {Object.entries(KIND_COLOR)
          .filter(([k]) => design.connections.some((c) => {
            const [a, pa] = c.source.split(".");
            return cat(design.components[a]?.type)?.ports.find((p) => p.name === pa)?.kind === k;
          }))
          .map(([k, color]) => (
            <span key={k} className="inline-flex items-center gap-1">
              <span className="inline-block h-0.5 w-4" style={{ background: color }} /> {k}
            </span>
          ))}
        <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-5 rounded border border-dashed border-ink-3" /> planned (no physics model yet)</span>
      </div>
    </div>
  );
}

function ComponentParams({ id, comp, onChange }: { id: string; comp: ComponentInstance; onChange: (c: ComponentInstance) => void }) {
  const { materials } = useSession();
  const params = comp.params ?? {};
  const set = (key: string, value: unknown) => onChange({ ...comp, params: { ...params, [key]: value } });
  return (
    <div className="divide-y divide-[var(--border)]">
      {Object.entries(params).map(([key, v]) => {
        const f = FIELD[key] ?? { label: key, unit: "" };
        if (key === "driven_axle")
          return (
            <div key={key} className="flex items-center justify-between gap-3 py-2">
              <span className="text-sm">{f.label}</span>
              <Select value={String(v)} onChange={(e) => set(key, e.target.value)} className="w-40">
                <option value="front">Front</option>
                <option value="rear">Rear</option>
                <option value="all">All-wheel</option>
              </Select>
            </div>
          );
        if (key === "disc_material_id")
          return (
            <div key={key} className="flex items-center justify-between gap-3 py-2">
              <span className="text-sm">{f.label}</span>
              <Select value={String(v)} onChange={(e) => set(key, e.target.value)} className="w-56">
                {materials.filter((m) => m.properties.specific_heat).map((m) => (
                  <option key={m.id} value={m.id}>{m.name} {m.condition}</option>
                ))}
              </Select>
            </div>
          );
        if (key === "ratios")
          return (
            <div key={key} className="py-2">
              <Field label={f.label} hint="Comma-separated, strictly decreasing">
                <Input
                  defaultValue={(v as number[]).join(", ")}
                  onBlur={(e) => {
                    const r = e.target.value.split(/[,\s]+/).map(Number).filter((x) => x > 0);
                    if (r.length) set(key, r);
                  }}
                />
              </Field>
            </div>
          );
        if (v === null && ["launch_rpm", "mass", "axle_torque_rating"].includes(key))
          return (
            <div key={key} className="flex items-center justify-between gap-3 py-2">
              <span className="text-sm text-ink-2">{f.label} <span className="text-ink-3">(not set)</span></span>
              <Button size="sm" onClick={() => set(key, { value: key === "launch_rpm" ? 3000 : 1, source: "user", tol: 0, ref: null })}><Plus className="size-3.5" /> Set</Button>
            </div>
          );
        if (!isParam(v)) return null;
        return (
          <div key={key} className="grid gap-1 py-2 sm:grid-cols-[1fr_1.3fr] sm:gap-3">
            <div className="text-sm">
              <span className="flex flex-wrap items-center gap-1.5">
                {f.label} {f.unit && f.unit !== "-" && <span className="text-ink-3">({f.unit})</span>}
                <SourceBadge source={v.source} reference={v.ref} />
              </span>
              {f.help && <span className="text-xs text-ink-3">{f.help}</span>}
            </div>
            <div className="flex gap-1.5">
              <Input type="number" step="any" value={v.value} onChange={(e) => set(key, { ...v, value: Number(e.target.value) })} aria-label={f.label} />
              <Input type="number" min={0} step="any" value={v.tol} onChange={(e) => set(key, { ...v, tol: Math.max(0, Number(e.target.value) || 0) })} className="w-24 text-ink-2" title="± uncertainty" aria-label={`${f.label} uncertainty`} />
              <select className={clsx(inputClass, "w-28 text-xs")} value={v.source} onChange={(e) => set(key, { ...v, source: e.target.value as Source })} aria-label={`${f.label} source`}>
                {(["measured", "manufacturer", "literature", "user", "estimated", "unknown"] as Source[]).map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
              </select>
            </div>
          </div>
        );
      })}
      <input type="hidden" value={id} readOnly />
    </div>
  );
}

export function ArchitectureTab({
  design,
  onChange,
  status,
}: {
  design: VehicleDesign;
  onChange: (d: VehicleDesign) => void;
  status: Record<string, Status>;
}) {
  const { meta } = useSession();
  const [selected, setSelected] = useState<string | null>(Object.keys(design.components)[0] ?? null);
  const [addType, setAddType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [group, setGroup] = useState("turbo");
  const [level, setLevel] = useState<Level>("engineer");
  const catalog = meta?.catalog ?? [];
  const cat = (t: string) => catalog.find((c) => c.id === t);
  const comp = selected ? design.components[selected] : null;

  const ports = Object.entries(design.components).flatMap(([id, c]) =>
    (cat(c.type)?.ports ?? []).map((p) => ({ ref: `${id}.${p.name}`, label: `${c.name || id} · ${p.label}`, kind: p.kind })),
  );
  const fromKind = ports.find((p) => p.ref === from)?.kind;

  const add = () => {
    const t = cat(addType);
    if (!t) return;
    let id = t.id.replace(/[^a-z0-9_]/g, "_");
    let n = 2;
    while (design.components[id]) id = `${t.id}_${n++}`;
    onChange({ ...design, components: { ...design.components, [id]: { type: t.id, name: t.name, params: t.default_params ? structuredClone(t.default_params) : null } } });
    setSelected(id);
    setAddType("");
  };
  const remove = (id: string) => {
    const { [id]: _, ...rest } = design.components;
    void _;
    onChange({ ...design, components: rest, connections: design.connections.filter((c) => !c.source.startsWith(`${id}.`) && !c.target.startsWith(`${id}.`)) });
    setSelected(null);
  };
  const connect = () => {
    onChange({ ...design, connections: [...design.connections, { source: from, target: to }] });
    setFrom("");
    setTo("");
  };

  return (
    <div className="space-y-4">
      <VehicleGraph design={design} selected={selected} onSelect={setSelected} status={status} />
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <div className="min-w-0">
          {comp && selected ? (
            <Card
              title={
                <span className="flex flex-wrap items-center gap-2">
                  <input
                    value={comp.name}
                    onChange={(e) => onChange({ ...design, components: { ...design.components, [selected]: { ...comp, name: e.target.value } } })}
                    className="rounded border border-transparent bg-transparent px-1 hover:border-line focus:border-accent focus:outline-none"
                    aria-label="Component name"
                  />
                  <span className="text-xs font-normal text-ink-3">{cat(comp.type)?.name} · id “{selected}”</span>
                  {status[selected] && <StatusBadge status={status[selected]} />}
                </span>
              }
              subtitle={cat(comp.type)?.description}
              actions={<Button size="sm" variant="danger" onClick={() => remove(selected)}><Trash2 className="size-3.5" /> Remove</Button>}
            >
              {cat(comp.type)?.status === "planned" ? (
                <Note>
                  This component is part of the architecture but has no physics model yet. It is wired into the graph and
                  reported as “not evaluated” in simulations. Failure modes to be modelled: {cat(comp.type)?.failure_modes.join(", ") || "—"}.
                </Note>
              ) : comp.type === "engine_turbo_si" ? (
                <EngineEditor
                  design={comp.params as Json}
                  onChange={(p) => onChange({ ...design, components: { ...design.components, [selected]: { ...comp, params: p } } })}
                  group={group}
                  setGroup={setGroup}
                  level={level}
                  setLevel={setLevel}
                />
              ) : (
                <ComponentParams id={selected} comp={comp} onChange={(c) => onChange({ ...design, components: { ...design.components, [selected]: c } })} />
              )}
            </Card>
          ) : (
            <Card title="Select a component">Click a component in the graph to edit it.</Card>
          )}
        </div>
        <div className="space-y-4">
          <Card title="Add a component" subtitle="Build a vehicle from the catalog. Planned parts can be placed now; their physics arrives in later stages.">
            <div className="flex gap-2">
              <Select value={addType} onChange={(e) => setAddType(e.target.value)} aria-label="Component type">
                <option value="">Choose from catalog…</option>
                {CATEGORY_ORDER.map((c) => (
                  <optgroup key={c} label={c}>
                    {catalog.filter((t: CatalogType) => t.category === c).map((t) => (
                      <option key={t.id} value={t.id}>{t.name}{t.status === "planned" ? " (planned)" : ""}</option>
                    ))}
                  </optgroup>
                ))}
              </Select>
              <Button onClick={add} disabled={!addType}><Plus className="size-4" /> Add</Button>
            </div>
          </Card>
          <Card title={<span className="inline-flex items-center gap-1.5"><Link2 className="size-4" /> Connect ports</span>} subtitle="Only ports of the same kind can be joined (shaft to shaft, coolant to coolant…).">
            <div className="space-y-2">
              <Select value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From port">
                <option value="">From port…</option>
                {ports.map((p) => <option key={p.ref} value={p.ref}>{p.label} ({p.kind})</option>)}
              </Select>
              <Select value={to} onChange={(e) => setTo(e.target.value)} aria-label="To port" disabled={!from}>
                <option value="">To port…</option>
                {ports.filter((p) => p.kind === fromKind && p.ref !== from && !p.ref.startsWith(from.split(".")[0] + ".")).map((p) => (
                  <option key={p.ref} value={p.ref}>{p.label}</option>
                ))}
              </Select>
              <Button size="sm" onClick={connect} disabled={!from || !to}>Connect</Button>
            </div>
            <ul className="mt-3 max-h-56 space-y-1 overflow-auto text-xs">
              {design.connections.map((c, i) => (
                <li key={i} className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-[11px]">{c.source} → {c.target}</span>
                  <button type="button" onClick={() => onChange({ ...design, connections: design.connections.filter((_, j) => j !== i) })} className="text-ink-3 hover:text-[var(--critical)]" aria-label="Remove connection">
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
