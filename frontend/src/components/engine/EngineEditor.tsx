"use client";

import clsx from "clsx";
import { Segmented } from "@/components/ui";
import type { Json } from "@/lib/types";
import { GROUP_LABEL, LimitsEditor, ParamGroup, type Level } from "./ParamEditor";

const GROUPS = ["architecture", "engine", "operating", "breathing", "turbo", "intercooler", "combustion", "exhaust", "friction", "fuel", "conrod", "ambient", "targets", "limits"];

const GROUP_BLURB: Record<string, string> = {
  architecture: "Cylinder layout, bank angle, crankshaft and how air is forced in: the engine's basic configuration.",
  engine: "Bore, stroke, rods and compression: the geometry everything else scales from.",
  operating: "The rpm range the virtual dyno sweeps.",
  breathing: "How well the engine fills its cylinders across the rev range.",
  turbo: "Boost target and the turbocharger's efficiencies and turbine size.",
  intercooler: "How much of the compressor's heat is removed before the cylinders.",
  combustion: "Mixture, efficiency and the energy split between work, coolant and exhaust.",
  exhaust: "Back-pressure and the exhaust gas properties driving the turbine.",
  friction: "Mechanical losses that grow with engine speed.",
  fuel: "Fuel properties and injector capacity.",
  conrod: "Rod geometry and material for the buckling, yield and fatigue checks.",
  ambient: "Air temperature and pressure for this test.",
  targets: "What this design must achieve.",
  limits: "Documented allowables every result is checked against.",
};

/** Grouped editor for a full engine design (used in the engine lab and inside vehicle projects). */
export function EngineEditor({
  design,
  onChange,
  group,
  setGroup,
  level,
  setLevel,
  groups = GROUPS,
}: {
  design: Json;
  onChange: (d: Json) => void;
  group: string;
  setGroup: (g: string) => void;
  level: Level;
  setLevel: (l: Level) => void;
  groups?: string[];
}) {
  return (
    <div className="grid gap-6 md:grid-cols-[200px_1fr]">
      <nav className="flex gap-1 overflow-x-auto md:flex-col md:gap-0 md:border-l md:border-line" aria-label="Parameter groups">
        {groups.map((g, i) => (
          <button
            type="button"
            key={g}
            onClick={() => setGroup(g)}
            className={clsx(
              "-ml-px flex items-baseline gap-3 whitespace-nowrap border-l py-2.5 pl-4 pr-2 text-left font-display text-[13px] font-medium uppercase tracking-[0.14em] transition-colors",
              group === g ? "border-ink text-ink" : "border-transparent text-ink-3 hover:text-ink-2",
            )}
          >
            <span className="w-5 text-[10px] tabular text-ink-3">{String(i + 1).padStart(2, "0")}</span>
            {GROUP_LABEL[g] ?? g}
          </button>
        ))}
      </nav>
      <div className="min-w-0 border border-line bg-surface">
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line px-6 py-5">
          <div>
            <div className="eyebrow">Parameters</div>
            <h3 className="display mt-1.5 text-xl font-light tracking-[0.08em]">{GROUP_LABEL[group] ?? group}</h3>
            <p className="mt-1 max-w-xl text-xs text-ink-3">{GROUP_BLURB[group]}</p>
          </div>
          <Segmented
            options={[
              { id: "beginner", label: "Beginner" },
              { id: "engineer", label: "Engineer" },
              { id: "research", label: "Research" },
            ]}
            value={level}
            onChange={setLevel}
          />
        </div>
        <div className="px-6 pb-2">
          {group === "limits" ? (
            <div className="py-4">
              <LimitsEditor design={design} onChange={onChange} />
            </div>
          ) : (
            <ParamGroup group={group} design={design} onChange={onChange} level={level} />
          )}
        </div>
      </div>
    </div>
  );
}
