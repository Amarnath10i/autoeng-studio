"use client";

import { Cpu, GitBranch, RotateCcw, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, ErrorNote, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Worker } from "@/lib/types";
import type { ProjectState } from "./useProject";

export function ProjectBar({ state, children }: { state: ProjectState; children?: React.ReactNode }) {
  const { project, branch, head, dirty, commit, discard, switchBranch } = state;
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!project) return null;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await commit(message.trim() || "Update design");
      setMessage("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-0">
          <div className="eyebrow">
            {project.kind === "vehicle" ? "Vehicle project" : "Engine lab"} · v{head?.number} · {branch}
          </div>
          <h1 className="display mt-2 truncate text-3xl font-light tracking-[0.06em] sm:text-4xl">{project.name}</h1>
          <p className="mt-1 truncate text-xs text-ink-3">{head?.message}</p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-1.5 text-xs text-ink-2">
            <GitBranch className="size-3.5" aria-hidden />
            <Select
              value={branch}
              onChange={(e) => {
                if (dirty && !confirm("Discard unsaved changes and switch branch?")) return;
                switchBranch(e.target.value);
              }}
              className="h-8 w-40 text-xs"
              aria-label="Branch"
            >
              {project.branches.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name}
                </option>
              ))}
            </Select>
          </label>
          {children}
          {dirty && (
            <>
              <Input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Describe this change"
                className="h-8 w-56 text-xs"
                onKeyDown={(e) => e.key === "Enter" && save()}
                aria-label="Commit message"
              />
              <Button size="sm" variant="primary" onClick={save} loading={busy}>
                <Save className="size-3.5" aria-hidden /> Save version
              </Button>
              <Button size="sm" variant="ghost" onClick={discard}>
                <RotateCcw className="size-3.5" aria-hidden /> Discard
              </Button>
            </>
          )}
        </div>
      </div>
      <ErrorNote error={error} onClose={() => setError(null)} />
    </div>
  );
}

/** Where heavy computations run: this server, or one of the user's paired workers (their PC, Kaggle, Colab…). */
export function ComputePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { health } = useSession();
  const [workers, setWorkers] = useState<Worker[]>([]);
  useEffect(() => {
    api<Worker[]>("/api/v1/workers").then(setWorkers).catch(() => setWorkers([]));
  }, []);
  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-ink-2" title="Where this computation runs">
      <Cpu className="size-3.5" aria-hidden />
      <Select value={value} onChange={(e) => onChange(e.target.value)} className="h-8 w-56 text-xs" aria-label="Compute target">
        <option value="server">Server ({health?.compute.gpu_available ? health.compute.gpu_device : "CPU"})</option>
        {workers
          .filter((w) => w.paired)
          .map((w) => (
            <option key={w.id} value={w.id} disabled={!w.online}>
              {w.name} · {String(w.device?.gpu ?? "CPU")}
              {w.online ? "" : " (offline)"}
            </option>
          ))}
      </Select>
    </label>
  );
}
