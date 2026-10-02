"use client";

import clsx from "clsx";
import { Copy, Cpu, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Container, Figures, PageHero } from "@/components/layout";
import { Button, Card, Empty, ErrorNote, Field, Input, Note, SectionTitle, Segmented, Spinner, useAsync } from "@/components/ui";
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
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre className="overflow-x-auto border border-line bg-page p-4 pr-12 font-mono text-xs leading-relaxed text-ink-2">{text}</pre>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard?.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="absolute right-3 top-3 text-ink-3 hover:text-ink"
        aria-label="Copy"
      >
        {copied ? <span className="eyebrow text-ink">Copied</span> : <Copy className="size-4" strokeWidth={1.5} />}
      </button>
    </div>
  );
}

const STATUS_DOT: Record<string, string> = {
  done: "var(--good)",
  running: "var(--ink)",
  queued: "var(--ink-3)",
  failed: "var(--critical)",
  cancelled: "var(--ink-3)",
};

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

  const online = workers?.filter((w) => w.online).length ?? 0;
  const done = jobs.filter((j) => j.status === "done").length;

  return (
    <div>
      <PageHero
        eyebrow="Compute"
        title="Bring your own GPU"
        description="Run studies on this server, or pair your own hardware: a desktop GPU, a Kaggle or Colab notebook, or a cloud machine. Workers connect out to the platform, so no ports or firewall changes are needed."
      >
        <Figures
          items={[
            {
              label: "This server",
              value: health?.compute.gpu_available ? "GPU" : "CPU",
              sub: health?.compute.gpu_available ? "CUDA on the server" : "NumPy on the CPU",
            },
            { label: "Your workers", value: String(workers?.length ?? 0), sub: `${online} online now` },
            { label: "Jobs completed", value: String(done), sub: `${jobs.length} in the recent ledger` },
            { label: "Protocol", value: "Outbound", sub: "HTTPS polling · one-time pairing" },
          ]}
        />
      </PageHero>

      <Container className="grid gap-8 py-12 xl:grid-cols-[1fr_480px]">
        <div className="space-y-10">
          <ErrorNote error={act.error} onClose={() => act.setError(null)} />
          <section className="space-y-5">
            <SectionTitle eyebrow="Fleet" title="Your workers" />
            {!workers ? (
              <Spinner />
            ) : workers.length === 0 ? (
              <Empty title="No workers yet">Pair one on the right to run heavy studies on your own hardware.</Empty>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {workers.map((w) => (
                  <div key={w.id} className="group border border-line bg-surface p-5 transition-colors hover:border-line-strong">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="eyebrow inline-flex items-center gap-2">
                          <span
                            className="inline-block size-1.5 rounded-full"
                            style={{ background: w.online ? "var(--good)" : "var(--ink-3)", boxShadow: w.online ? "0 0 8px var(--good)" : undefined }}
                            aria-hidden
                          />
                          {!w.paired ? "Awaiting pairing" : w.online ? "Online" : "Offline"}
                        </div>
                        <div className="display mt-2 truncate text-lg">{w.name}</div>
                      </div>
                      <button type="button" onClick={() => remove(w)} className="text-ink-3 opacity-0 transition-opacity hover:text-[var(--critical)] group-hover:opacity-100 focus:opacity-100" aria-label={`Remove ${w.name}`}>
                        <Trash2 className="size-4" strokeWidth={1.5} />
                      </button>
                    </div>
                    <div className="mt-4 flex items-center gap-3 text-sm text-ink-2">
                      <Cpu className="size-4 text-ink-3" strokeWidth={1.5} aria-hidden />
                      {w.paired ? (w.device?.gpu ? "GPU" : "CPU only") : "—"}
                    </div>
                    <div className="mt-1 text-xs text-ink-3">
                      {w.paired ? `${String(w.device?.host ?? "")} · ${w.last_seen_at ? `seen ${timeAgo(w.last_seen_at)}` : "never seen"}` : "Run the pairing command on the machine"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="space-y-5">
            <SectionTitle eyebrow="Ledger" title="Recent jobs" />
            {jobs.length === 0 ? (
              <p className="text-sm text-ink-2">No jobs yet. Heavy studies you start from a project appear here.</p>
            ) : (
              <div className="overflow-x-auto border border-line bg-surface">
                <table className="w-full min-w-[640px] text-sm">
                  <thead>
                    <tr className="border-b border-line">
                      {["Job", "Status", "Ran on", "Device", "When"].map((h, i) => (
                        <th key={h} className={clsx("eyebrow px-5 py-3 font-medium", i === 4 ? "text-right" : "text-left")}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.slice(0, 15).map((j) => (
                      <tr key={j.id} className="border-b border-line last:border-0">
                        <td className="display px-5 py-3 text-[13px]">{j.kind.replace(/_/g, " ")}</td>
                        <td className="px-5 py-3">
                          <span className="inline-flex items-center gap-2 text-xs text-ink-2">
                            <span className="inline-block size-1.5 rounded-full" style={{ background: STATUS_DOT[j.status] }} aria-hidden />
                            {j.status}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-xs text-ink-2">{j.target === "server" ? "Server" : workers?.find((w) => w.id === j.target)?.name ?? "Worker"}</td>
                        <td className="px-5 py-3 text-xs text-ink-3">
                          {j.device?.backend ? (j.device.backend === "cupy" ? "GPU" : "CPU") : "—"}
                          {j.device?.seconds ? ` · ${String(j.device.seconds)} s` : ""}
                        </td>
                        <td className="px-5 py-3 text-right text-xs text-ink-3">{timeAgo(j.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <div>
          <Card title="Pair a worker" subtitle="Create a one-time code, then run one command on the machine with the GPU." className="xl:sticky xl:top-24">
            <div className="flex items-end gap-3">
              <Field label="Worker name">
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Button variant="primary" onClick={create} loading={act.busy}>
                <Plus className="size-4" /> Create code
              </Button>
            </div>
            {pairing && (
              <div className="mt-6 space-y-4">
                <div className="border border-line-strong bg-page px-5 py-6 text-center">
                  <div className="eyebrow">Pairing code · valid {pairing.expires_minutes} min</div>
                  <div className="mt-3 font-display text-4xl font-light tracking-[0.3em] text-ink">{pairing.pairing_code}</div>
                </div>
                <Segmented
                  options={[
                    { id: "local", label: "My PC / VM" },
                    { id: "notebook", label: "Kaggle / Colab" },
                  ]}
                  value={where}
                  onChange={setWhere}
                />
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
      </Container>
    </div>
  );
}
