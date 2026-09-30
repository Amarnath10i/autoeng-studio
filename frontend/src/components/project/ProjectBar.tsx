"use client";

import { Cpu, GitBranch, RotateCcw, Save } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { type FigureItem, Figures, PageHero } from "@/components/layout";
import { Button, ErrorNote, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Worker } from "@/lib/types";
import type { ProjectState } from "./useProject";

export function ProjectBar({
  state,
  children,
  figures,
}: {
  state: ProjectState;
  children?: React.ReactNode;
  figures?: FigureItem[];
}) {
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
    <PageHero
      eyebrow={
        <span className="inline-flex items-center gap-3">
          <Link href="/" className="hover:text-ink">
            Garage
          </Link>
          <span aria-hidden>/</span>
          {project.kind === "vehicle" ? "Vehicle" : "Engine lab"}
          <span aria-hidden>·</span>v{head?.number}
          <span aria-hidden>·</span>
          <span className="inline-flex items-center gap-1">
            <GitBranch className="size-3" aria-hidden />
            {branch}
          </span>
        </span>
      }
      title={project.name}
      description={<span className="text-ink-3">{head?.message}</span>}
      actions={
        <>
          <Select
            value={branch}
            onChange={(e) => {
              if (dirty && !confirm("Discard unsaved changes and switch branch?")) return;
              switchBranch(e.target.value);
            }}
            className="h-10 w-40"
            aria-label="Branch"
          >
            {project.branches.map((b) => (
              <option key={b.name} value={b.name}>
                {b.name}
              </option>
            ))}
          </Select>
          {children}
        </>
      }
    >
      <div className="space-y-6">
        {figures && <Figures items={figures} />}
        {dirty && (
          <div className="flex flex-wrap items-center gap-3 border-l-2 border-ink bg-surface px-5 py-3">
            <span className="eyebrow text-ink">Unsaved changes</span>
            <Input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Describe this change"
              className="h-9 min-w-[220px] flex-1"
              onKeyDown={(e) => e.key === "Enter" && save()}
              aria-label="Commit message"
            />
            <Button variant="primary" onClick={save} loading={busy}>
              <Save className="size-3.5" aria-hidden /> Save version
            </Button>
            <Button variant="ghost" onClick={discard}>
              <RotateCcw className="size-3.5" aria-hidden /> Discard
            </Button>
          </div>
        )}
        <ErrorNote error={error} onClose={() => setError(null)} />
      </div>
    </PageHero>
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
    <label className="inline-flex items-center gap-2 text-xs text-ink-2" title="Where this computation runs">
      <Cpu className="size-4 text-ink-3" strokeWidth={1.5} aria-hidden />
      <Select value={value} onChange={(e) => onChange(e.target.value)} className="h-10 w-60" aria-label="Compute target">
        <option value="server">
          Server · {health?.compute.gpu_available ? (health.compute.gpu_device ?? "GPU").replace(/^NVIDIA (GeForce )?/, "") : "CPU"}
        </option>
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
