"use client";

import { CheckCircle2, OctagonX, Play, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Container, Figures, PageHero } from "@/components/layout";
import { ComputePicker } from "@/components/project/ProjectBar";
import { Button, Card, Empty, ErrorNote, Note, SectionTitle, Segmented, Spinner, useAsync } from "@/components/ui";
import { api, waitForJob } from "@/lib/api";
import { fmt } from "@/lib/format";

interface Row {
  label: string;
  reference: number;
  predicted: number;
  unit: string;
  error: number;
  error_kind: "percent" | "absolute";
  check?: boolean;
}

interface CaseResult {
  id: string;
  kind: "verification" | "validation";
  model: string;
  title: string;
  question: string;
  reference: string;
  tolerance_pct: number;
  heavy: boolean;
  note: string;
  status: "done" | "error";
  error?: string;
  rows: Row[];
  verdict?: "pass" | "marginal" | "fail";
  worst_error?: number;
  seconds: number;
  findings?: string[];
}

interface Report {
  generated_at: string;
  compute: { backend: string; device: string };
  cases: CaseResult[];
}

interface Field {
  engines: number;
  median_error_before_pct?: number;
  p90_error_before_pct?: number;
  median_error_after_pct?: number;
  rows: { cylinders: number; displacement_l: number; boost_bar: number; points: number; kind: string; error_before_pct: number; error_after_pct: number }[];
}

const VERDICT = {
  pass: { icon: CheckCircle2, color: "var(--good)", label: "Pass" },
  marginal: { icon: TriangleAlert, color: "var(--warning)", label: "Marginal" },
  fail: { icon: OctagonX, color: "var(--critical)", label: "Fail" },
} as const;

function Verdict({ v }: { v?: CaseResult["verdict"] }) {
  if (!v) return <span className="eyebrow">Error</span>;
  const { icon: Icon, color, label } = VERDICT[v];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-ink">
      <Icon className="size-4" style={{ color }} aria-hidden /> {label}
    </span>
  );
}

/** Numbers at round-off level (exact checks) read as ≈ 0 rather than 2e-14. */
const show = (v: number) => (Math.abs(v) < 1e-9 ? "≈ 0" : Math.abs(v) < 1e-3 ? v.toExponential(1) : fmt(v, 4));
const errText = (r: Row) =>
  r.error_kind === "percent"
    ? Math.abs(r.error) < 1e-9
      ? "≈ 0 %"
      : `${r.error >= 0 ? "+" : "−"}${fmt(Math.abs(r.error), Math.abs(r.error) < 0.01 ? 4 : 1)} %`
    : show(r.error);

/** Paired bars: reference (outline) against predicted (filled), on a shared scale per case. */
function PairBars({ rows }: { rows: Row[] }) {
  const max = Math.max(...rows.flatMap((r) => [Math.abs(r.reference), Math.abs(r.predicted)]), 1e-9);
  return (
    <div className="space-y-3" aria-hidden>
      {rows.map((r) => (
        <div key={r.label}>
          <div className="mb-1 text-xs text-ink-2">{r.label}</div>
          <div className="relative h-2.5 border border-line-strong" style={{ width: `${(Math.abs(r.reference) / max) * 100}%` }} />
          <div className="mt-1 h-2.5 bg-[var(--s1)]" style={{ width: `${(Math.abs(r.predicted) / max) * 100}%` }} />
        </div>
      ))}
      <div className="flex gap-4 pt-1 text-[11px] text-ink-3">
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-2 w-4 border border-line-strong" /> Reference</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-2 w-4 bg-[var(--s1)]" /> Model</span>
      </div>
    </div>
  );
}

function CaseCard({ c }: { c: CaseResult }) {
  const scored = c.rows.filter((r) => !r.check);
  return (
    <Card
      title={c.title}
      subtitle={c.question}
      actions={<Verdict v={c.status === "done" ? c.verdict : undefined} />}
    >
      {c.status === "error" ? (
        <ErrorNote error={c.error ?? "Failed"} />
      ) : (
        <div className={c.kind === "validation" ? "grid gap-6 lg:grid-cols-[1.4fr_1fr]" : ""}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm tabular">
              <thead className="text-left text-xs text-ink-2">
                <tr>
                  <th className="py-1.5 font-medium">Check</th>
                  <th className="py-1.5 text-right font-medium">Reference</th>
                  <th className="py-1.5 text-right font-medium">Model</th>
                  <th className="py-1.5 text-right font-medium">Error</th>
                </tr>
              </thead>
              <tbody>
                {c.rows.map((r) => (
                  <tr key={r.label} className="border-t border-line">
                    <td className="py-2 pr-4">{r.label}</td>
                    <td className="py-2 text-right">{show(r.reference)}</td>
                    <td className="py-2 text-right">{show(r.predicted)}</td>
                    <td className="py-2 text-right">{errText(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {c.kind === "validation" && <PairBars rows={scored} />}
        </div>
      )}
      {c.findings && c.findings.length > 0 && (
        <ul className="mt-5 space-y-1.5 border-t border-line pt-4 text-[13px] leading-relaxed text-ink-2">
          {c.findings.map((f) => (
            <li key={f} className="flex gap-2">
              <span className="text-ink-3">—</span>
              {f}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-4 text-xs text-ink-3">
        Reference: {c.reference}. Pass band ±{fmt(c.tolerance_pct, c.tolerance_pct < 1 ? 2 : 0)} %{c.note ? ` · ${c.note}` : ""} · {fmt(c.seconds, 1)} s
      </p>
    </Card>
  );
}

export default function ValidationPage() {
  const [data, setData] = useState<{ published: Report | null; field: Field } | null>(null);
  const [mine, setMine] = useState<Report | null>(null);
  const [show, setShow] = useState<"published" | "mine">("published");
  const [target, setTarget] = useState("server");
  const [status, setStatus] = useState("");
  const load = useAsync();
  const run = useAsync();

  useEffect(() => {
    load.run(async () => setData(await api("/api/v1/validation")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rerun = () =>
    run.run(async () => {
      const job = await api<{ id: string }>("/api/v1/validation/run", { method: "POST", json: { include_heavy: true, target } });
      setMine(await waitForJob<Report>(job.id, setStatus));
      setShow("mine");
    });

  const report = show === "mine" && mine ? mine : data?.published ?? null;
  const verification = report?.cases.filter((c) => c.kind === "verification") ?? [];
  const validation = report?.cases.filter((c) => c.kind === "validation") ?? [];
  const byId = (id: string) => report?.cases.find((c) => c.id === id);
  const sphere = byId("sphere_drag");
  const ahmed = byId("ahmed_drag");
  const field = data?.field;

  return (
    <div>
      <PageHero
        eyebrow="Model accuracy"
        title="Validation"
        description="Every model is checked two ways: verification (does the code solve its equations exactly?) and validation (does the answer match experiments and real engines?). Failures are published, not hidden: they tell you which numbers to trust and which to measure."
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <ComputePicker value={target} onChange={setTarget} />
            <Button variant="primary" size="lg" onClick={rerun} loading={run.busy}>
              <Play className="size-3.5" aria-hidden /> Re-run all benchmarks
            </Button>
          </div>
        }
      >
        <Figures
          items={[
            {
              label: "Verification",
              value: report ? `${verification.filter((c) => c.verdict === "pass").length}/${verification.length}` : "—",
              sub: "Exact checks passing",
            },
            {
              label: "Sphere drag",
              value: sphere?.worst_error != null ? `±${fmt(sphere.worst_error, 1)}` : "—",
              unit: "%",
              sub: "vs. measured, at the tunnel's Reynolds number",
            },
            {
              label: "Car-body drag",
              value: ahmed?.worst_error != null ? `+${fmt(ahmed.worst_error, 0)}` : "—",
              unit: "%",
              sub: "Ahmed body vs. wind-tunnel data: Cd is indicative only",
            },
            {
              label: "Real engines",
              value: field ? String(field.engines) : "—",
              sub: field?.engines ? `median torque error ${fmt(field.median_error_before_pct, 1)} % uncalibrated` : "Shared calibrations so far",
            },
          ]}
        />
      </PageHero>
      <Container className="space-y-12 py-10">
        <ErrorNote error={load.error ?? run.error} />
        {run.busy && <Spinner label={`Running benchmarks · ${status || "queued"} · the 3D flow cases take a few minutes`} />}
        {mine && (
          <div className="flex flex-wrap items-center gap-4">
            <Segmented<"published" | "mine">
              options={[
                { id: "published", label: "Published report" },
                { id: "mine", label: "Your run" },
              ]}
              value={show}
              onChange={setShow}
            />
            <span className="text-xs text-ink-3">
              {report && `Generated ${new Date(report.generated_at).toLocaleString()} on ${report.compute.device}`}
            </span>
          </div>
        )}
        {!report && !load.busy && <Empty title="No published report">Run the benchmarks to generate one.</Empty>}
        {load.busy && <Spinner />}

        {report && (
          <>
            <section className="space-y-5">
              <SectionTitle eyebrow="01 · Verification" title="Does the code solve its equations?" />
              <div className="space-y-6">
                {verification.map((c) => (
                  <CaseCard key={c.id} c={c} />
                ))}
              </div>
            </section>

            <section className="space-y-5">
              <SectionTitle eyebrow="02 · Validation" title="Does it match experiments?" />
              <div className="space-y-6">
                {validation.map((c) => (
                  <CaseCard key={c.id} c={c} />
                ))}
              </div>
            </section>
          </>
        )}

        <section className="space-y-5">
          <SectionTitle eyebrow="03 · Field evidence" title="How close is it on real engines?" />
          {field && field.engines > 0 ? (
            <Card
              title={`${field.engines} real engines`}
              subtitle="Torque error of the uncalibrated model against each engine's own dyno run, and after calibrating to it. Shared anonymously by users (opt-in)."
            >
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm tabular">
                  <thead className="text-left text-xs text-ink-2">
                    <tr>
                      <th className="py-1.5 font-medium">Engine</th>
                      <th className="py-1.5 text-right font-medium">Points</th>
                      <th className="py-1.5 text-right font-medium">Error before</th>
                      <th className="py-1.5 text-right font-medium">After calibration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {field.rows.map((r, i) => (
                      <tr key={i} className="border-t border-line">
                        <td className="py-2">
                          {r.cylinders} cyl · {fmt(r.displacement_l, 1)} L · {fmt(r.boost_bar, 1)} bar
                        </td>
                        <td className="py-2 text-right">{r.points}</td>
                        <td className="py-2 text-right">{fmt(r.error_before_pct, 1)} %</td>
                        <td className="py-2 text-right">{fmt(r.error_after_pct, 1)} %</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : (
            <Empty title="No real engines yet">
              Calibrate an engine project against your dyno run (Test & calibrate) and share it. Each shared engine adds a
              point here, showing how far the model was before calibration: the most honest accuracy figure there is.
            </Empty>
          )}
        </section>

        <Note>
          <span className="font-medium text-ink">What this means for your results.</span> The engine, balance and structure
          models solve their equations exactly, so their accuracy is set by the inputs: calibrate against a dyno and the
          uncertainty bands tighten. The wind tunnel is verified on a sphere, but at car-like Reynolds numbers its absolute
          drag is not reliable: use it to see the flow and compare big shape changes, and enter drag from a real test as a
          measured value.
        </Note>
      </Container>
    </div>
  );
}
