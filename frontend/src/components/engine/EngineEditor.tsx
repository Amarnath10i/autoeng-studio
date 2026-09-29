"use client";

import clsx from "clsx";
import { Segmented } from "@/components/ui";
import type { Json } from "@/lib/types";
import { GROUP_LABEL, LimitsEditor, ParamGroup, type Level } from "./ParamEditor";

const GROUPS = ["engine", "operating", "breathing", "turbo", "intercooler", "combustion", "exhaust", "friction", "fuel", "conrod", "ambient", "targets", "limits"];

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
    <div className="grid gap-4 md:grid-cols-[180px_1fr]">
      <nav className="flex gap-1 overflow-x-auto md:flex-col" aria-label="Parameter groups">
        {groups.map((g) => (
          <button type="button"
            key={g}
            onClick={() => setGroup(g)}
            className={clsx(
              "whitespace-nowrap rounded-md px-2.5 py-1.5 text-left text-sm",
              group === g ? "bg-surface-2 font-medium text-ink" : "text-ink-2 hover:text-ink",
            )}
          >
            {GROUP_LABEL[g] ?? g}
          </button>
        ))}
      </nav>
      <div className="min-w-0 border border-line bg-surface p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{GROUP_LABEL[group] ?? group}</h3>
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
        {group === "limits" ? (
          <LimitsEditor design={design} onChange={onChange} />
        ) : (
          <ParamGroup group={group} design={design} onChange={onChange} level={level} />
        )}
      </div>
    </div>
  );
}
