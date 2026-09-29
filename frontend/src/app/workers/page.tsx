"use client";

import { Copy, Cpu, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Card, Empty, ErrorNote, Field, Input, Note, Segmented, Spinner, useAsync } from "@/components/ui";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Job, Worker } from "@/lib/types";

interface Pairing {
  worker: Worker;
  pairing_code: string;
  expires_minutes: number;
  instructions: { local: string; pip: string; notebook: string; note: string };
}

function CodeBlock({ text }: { text: string }) {
  return (
    <div className="relative">
      <pre className="overflow-x-auto border border-line bg-surface-2 p-3 pr-10 font-mono text-xs">{text}</pre>
      <button type="button" onClick={() => navigator.clipboard?.writeText(text)} className="absolute right-2 top-2 text-ink-3 hover:text-ink" aria-label="Copy">
        <Copy className="size-4" />
      </button>
    </div>
  );
}

export default function WorkersPage() {
  const { health } = useSession();
  const [workers, setWorkers] = useState<Worker[] | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [name, setName] = useState("My GPU");
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [where, setWhere] = useState<"local" | "notebook">("local");
  const act = useAsync();

  const load = () =>
    act.run(async () => {
      const [w, j] = await Promise.all([api<Worker[]>("/api/v1/workers"), api<Job[]>("/api/v1/jobs")]);
      setWorkers(w);
      setJobs(j);
    });
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create = () => act.run(async () => setPairing(await api<Pairing>("/api/v1/workers", { method: "POST", json: { name } })));
  const remove = (w: Worker) => {
    if (!confirm(`Remove worker "${w.name}"? It will stop receiving jobs.`)) return;
    act.run(async () => {
      await api(`/api/v1/workers/${w.id}`, { method: "DELETE" });
      await load();
    });
  };

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_460px]">
      <div className="space-y-4">
        <div>
          <h1 className="text-xl font-semibold">Compute</h1>
          <p className="text-sm text-ink-2">
            Run simulations on this server, or bring your own GPU: your PC, a Kaggle or Colab notebook, or a cloud VM. Workers
            connect out to the platform, so no ports or firewall changes are needed.
          </p>
        </div>
        <ErrorNote error={act.error} onClose={() => act.setError(null)} />
        <Card title="This server">
          <p className="text-sm">
            <Cpu className="mr-1 inline size-4 text-accent" aria-hidden />
            {health?.compute.gpu_available ? `GPU: ${health.compute.gpu_device}` : "CPU only"} · mode “{health?.compute.mode}”
          </p>
        </Card>
        <Card title="Your workers">
          {!workers ? (
            <Spinner />
          ) : workers.length === 0 ? (
            <Empty title="No workers yet">Pair one on the right to run heavy studies on your own hardware.</Empty>
          ) : (
            <ul className="divide-y divide-[var(--border)]">
              {workers.map((w) => (
                <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                  <div>
                    <div className="font-medium">{w.name}</div>
                    <div className="text-xs text-ink-3">
                      {!w.paired ? "Waiting for pairing" : `${String(w.device?.gpu ?? "CPU")} · ${String(w.device?.host ?? "")} · ${w.last_seen_at ? `seen ${timeAgo(w.last_seen_at)}` : "never seen"}`}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="inline-flex items-center gap-1.5 text-xs">
                      <span className="inline-block size-2 rounded-full" style={{ background: w.online ? "var(--good)" : "var(--ink-3)" }} aria-hidden />
                      {w.online ? "Online" : "Offline"}
                    </span>
                    <button type="button" onClick={() => remove(w)} className="text-ink-3 hover:text-[var(--critical)]" aria-label={`Remove ${w.name}`}>
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Recent jobs">
          {jobs.length === 0 ? (
            <p className="text-sm text-ink-2">No jobs yet.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {jobs.slice(0, 15).map((j) => (
                  <tr key={j.id} className="border-t border-line">
                    <td className="py-1.5">{j.kind.replace("_", " ")}</td>
                    <td className="py-1.5 text-ink-2">{j.status}</td>
                    <td className="py-1.5 text-xs text-ink-3">{j.target === "server" ? "server" : workers?.find((w) => w.id === j.target)?.name ?? "worker"}</td>
                    <td className="py-1.5 text-xs text-ink-3">{j.device?.device ? String(j.device.device) : ""}{j.device?.seconds ? ` · ${String(j.device.seconds)} s` : ""}</td>
                    <td className="py-1.5 text-right text-xs text-ink-3">{timeAgo(j.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
      <Card title="Add a worker" subtitle="Creates a one-time pairing code.">
        <div className="flex gap-2">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Button variant="primary" onClick={create} loading={act.busy} className="mt-5">
            <Plus className="size-4" /> Create code
          </Button>
        </div>
        {pairing && (
          <div className="mt-4 space-y-3">
            <div className="rounded-md border border-accent bg-surface-2 p-3 text-center">
              <div className="text-xs text-ink-2">Pairing code (valid {pairing.expires_minutes} min)</div>
              <div className="mt-1 font-mono text-2xl tracking-widest">{pairing.pairing_code}</div>
            </div>
            <Segmented options={[{ id: "local", label: "My PC / VM" }, { id: "notebook", label: "Kaggle / Colab" }]} value={where} onChange={setWhere} />
            {where === "local" ? (
              <>
                <p className="text-xs text-ink-2">From a checkout of this repository (the “gpu” extra adds NVIDIA GPU support):</p>
                <CodeBlock text={pairing.instructions.local} />
                <p className="text-xs text-ink-2">Or install from your repository with pip:</p>
                <CodeBlock text={pairing.instructions.pip} />
              </>
            ) : (
              <>
                <p className="text-xs text-ink-2">In a notebook with a GPU accelerator and internet access enabled, run:</p>
                <CodeBlock text={pairing.instructions.notebook} />
              </>
            )}
            <Note>{pairing.instructions.note}</Note>
          </div>
        )}
      </Card>
    </div>
  );
}
