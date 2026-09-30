"use client";

import clsx from "clsx";
import { Plus, Trash2 } from "lucide-react";
import { useMemo } from "react";
import { twMerge } from "tailwind-merge";
import { Button, Input, Select, SourceBadge, inputClass } from "@/components/ui";
import { getAt, SOURCE_LABEL, setAt } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Json, Limit, Param, ParamSpec, Source } from "@/lib/types";

export type Level = "beginner" | "engineer" | "research";

export const GROUP_LABEL: Record<string, string> = {
  engine: "Engine geometry",
  operating: "Operating range",
  breathing: "Breathing",
  turbo: "Turbocharger",
  intercooler: "Intercooler",
  combustion: "Combustion",
  exhaust: "Exhaust",
  friction: "Friction",
  fuel: "Fuel system",
  ambient: "Test conditions",
  conrod: "Connecting rods",
  targets: "Targets",
  limits: "Limits",
};

function ParamRow({
  spec,
  design,
  onChange,
  level,
}: {
  spec: ParamSpec;
  design: Json;
  onChange: (d: Json) => void;
  level: Level;
}) {
  const { meta, materials } = useSession();
  const raw = getAt(design, spec.path);
  const help = level === "beginner" ? spec.beginner : spec.engineer;

  if (spec.kind === "choice") {
    const options =
      spec.choices_from === "fuels"
        ? (meta?.fuels ?? []).map((f) => ({ id: f.id, label: f.name }))
        : materials
            .filter((m) => ["density", "youngs_modulus", "yield_strength", "ultimate_strength"].every((k) => k in m.properties))
            .map((m) => ({ id: m.id, label: `${m.name} ${m.condition}${m.custom ? " (custom)" : ""}` }));
    return (
      <Row label={spec.label} help={help}>
        <Select value={String(raw ?? "")} onChange={(e) => onChange(setAt(design, spec.path, e.target.value))} className="w-[26rem] max-w-full">
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </Select>
      </Row>
    );
  }

  if (spec.kind === "int") {
    return (
      <Row label={spec.label} help={help}>
        <div className="w-44">
          <UnitInput
            unit={spec.unit}
            type="number"
            min={spec.min}
            max={spec.max}
            step={spec.step ?? 1}
            value={Number(raw ?? 0)}
            onChange={(e) => onChange(setAt(design, spec.path, Math.round(Number(e.target.value))))}
          />
        </div>
      </Row>
    );
  }

  const p = raw as Param | null | undefined;
  if (spec.optional && !p) {
    return (
      <Row label={spec.label} help={help}>
        <Button
          size="sm"
          onClick={() =>
            onChange(setAt(design, spec.path, { value: spec.min === 1 ? 100 : spec.min, source: "user", tol: 0, ref: null }))
          }
        >
          <Plus className="size-3.5" /> Set target
        </Button>
      </Row>
    );
  }
  if (!p) return null;
  const outOfRange = p.value < spec.min || p.value > spec.max;
  const update = (patch: Partial<Param>) => onChange(setAt(design, spec.path, { ...p, ...patch }));

  return (
    <Row label={spec.label} help={help} extra={<SourceBadge source={p.source} reference={p.ref} />} reference={level === "research" ? p.ref : null}>
      <div className="flex items-start gap-2">
        <div className="w-44">
          <UnitInput
            unit={spec.unit}
            type="number"
            step={spec.step ?? "any"}
            value={Number.isFinite(p.value) ? p.value : ""}
            aria-label={spec.label}
            aria-invalid={outOfRange}
            className={outOfRange ? "border-[var(--critical)]" : ""}
            onChange={(e) => update({ value: e.target.value === "" ? NaN : Number(e.target.value) })}
          />
          {outOfRange && (
            <div className="mt-1 text-[11px] text-[var(--critical)]">
              Allowed {spec.min}–{spec.max}
            </div>
          )}
        </div>
        {level !== "beginner" && (
          <div className="w-24">
            <UnitInput
              unit="±"
              unitFirst
              type="number"
              min={0}
              step={spec.step ?? "any"}
              value={p.tol}
              title="Uncertainty: ± half-width (≈95 % interval)"
              aria-label={`${spec.label} uncertainty`}
              onChange={(e) => update({ tol: Math.max(0, Number(e.target.value) || 0) })}
              className="text-ink-2"
            />
          </div>
        )}
        {level !== "beginner" && (
          <select
            className={twMerge(inputClass, "w-36 text-xs")}
            value={p.source}
            aria-label={`${spec.label} data source`}
            onChange={(e) => update({ source: e.target.value as Source })}
          >
            {(["measured", "manufacturer", "literature", "user", "estimated", "unknown", "calibrated", "community"] as Source[]).map(
              (s) => (
                <option key={s} value={s}>
                  {SOURCE_LABEL[s]}
                </option>
              ),
            )}
          </select>
        )}
      </div>
    </Row>
  );
}

/** One parameter row: name and explanation on the left, controls aligned on the right. */
function Row({
  label,
  help,
  extra,
  reference,
  children,
}: {
  label: string;
  help: string;
  extra?: React.ReactNode;
  reference?: string | null;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-3 py-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start lg:gap-8">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-[14px] text-ink">
          {label}
          {extra}
        </div>
        <p className="mt-1 max-w-xl text-xs leading-relaxed text-ink-3">{help}</p>
        {reference && <p className="mt-1 text-[11px] italic text-ink-3">Ref: {reference}</p>}
      </div>
      {children}
    </div>
  );
}

/** Numeric input with its unit set inside the field. */
function UnitInput({
  unit,
  unitFirst,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { unit: string; unitFirst?: boolean }) {
  const show = unit && unit !== "-";
  return (
    <div className="relative">
      <Input {...props} className={twMerge(show ? (unitFirst ? "pl-7" : "pr-16") : "", className)} />
      {show && (
        <span
          className={clsx(
            "pointer-events-none absolute top-1/2 -translate-y-1/2 truncate font-display text-[11px] uppercase tracking-[0.08em] text-ink-3",
            unitFirst ? "left-2.5" : "right-2.5 max-w-14",
          )}
        >
          {unit}
        </span>
      )}
    </div>
  );
}

export function ParamGroup({
  group,
  design,
  onChange,
  level,
}: {
  group: string;
  design: Json;
  onChange: (d: Json) => void;
  level: Level;
}) {
  const { meta } = useSession();
  const specs = useMemo(() => (meta?.params ?? []).filter((s) => s.group === group), [meta, group]);
  return (
    <div className="divide-y divide-[var(--border)]">
      {specs.map((s) => (
        <ParamRow key={s.path} spec={s} design={design} onChange={onChange} level={level} />
      ))}
    </div>
  );
}

export function LimitsEditor({ design, onChange }: { design: Json; onChange: (d: Json) => void }) {
  const { meta } = useSession();
  const limits = (design.limits as Limit[]) ?? [];
  const components = meta?.components ?? [];
  const channels = meta?.channels ?? [];
  const set = (next: Limit[]) => onChange({ ...design, limits: next });
  const update = (i: number, patch: Partial<Limit>) => set(limits.map((l, j) => (i === j ? { ...l, ...patch } : l)));

  const add = () => {
    const comp = components[0];
    const channel = comp?.channels[0] ?? "torque";
    let id = channel;
    let n = 2;
    while (limits.some((l) => l.id === id)) id = `${channel}_${n++}`;
    set([...limits, { id, component: comp.id, channel, label: null, allowable: { value: 1, source: "manufacturer", tol: 0, ref: "" } }]);
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-2">
        Allowables should come from documented data (datasheets, tests). The platform computes the safety factor
        allowable ÷ load for each, with uncertainty.
      </p>
      {limits.map((l, i) => {
        const comp = components.find((c) => c.id === l.component);
        const chan = channels.find((c) => c.id === l.channel);
        return (
          <div key={i} className="grid gap-2 border border-line p-3 sm:grid-cols-2 lg:grid-cols-[1.2fr_1fr_1fr_0.8fr_0.7fr_1fr_auto]">
            <Input value={l.label ?? ""} placeholder={chan?.label ?? "Label"} onChange={(e) => update(i, { label: e.target.value || null })} aria-label="Limit label" />
            <Select value={l.component} onChange={(e) => {
              const c = components.find((x) => x.id === e.target.value);
              update(i, { component: e.target.value, channel: c?.channels.includes(l.channel) ? l.channel : c?.channels[0] ?? l.channel });
            }} aria-label="Component">
              {components.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select value={l.channel} onChange={(e) => update(i, { channel: e.target.value })} aria-label="Quantity">
              {(comp?.channels ?? []).map((ch) => <option key={ch} value={ch}>{channels.find((c) => c.id === ch)?.label ?? ch}</option>)}
            </Select>
            <div className="flex items-center gap-1">
              <Input type="number" value={l.allowable.value} onChange={(e) => update(i, { allowable: { ...l.allowable, value: Number(e.target.value) } })} aria-label="Allowable" />
              <span className="text-xs text-ink-3">{chan?.unit}</span>
            </div>
            <Input type="number" min={0} value={l.allowable.tol} title="± uncertainty" onChange={(e) => update(i, { allowable: { ...l.allowable, tol: Math.max(0, Number(e.target.value) || 0) } })} aria-label="Allowable uncertainty" />
            <Select value={l.allowable.source} onChange={(e) => update(i, { allowable: { ...l.allowable, source: e.target.value as Source } })} aria-label="Source">
              {(["manufacturer", "measured", "literature", "user", "estimated", "unknown"] as Source[]).map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
            </Select>
            <button type="button" onClick={() => set(limits.filter((_, j) => j !== i))} className="justify-self-end text-ink-3 hover:text-[var(--critical)]" aria-label="Remove limit">
              <Trash2 className="size-4" />
            </button>
            <input
              className={clsx(inputClass, "sm:col-span-2 lg:col-span-7 text-xs")}
              placeholder="Reference: datasheet, test report or URL"
              value={l.allowable.ref ?? ""}
              onChange={(e) => update(i, { allowable: { ...l.allowable, ref: e.target.value } })}
            />
          </div>
        );
      })}
      <Button size="sm" onClick={add}>
        <Plus className="size-3.5" /> Add limit
      </Button>
    </div>
  );
}
