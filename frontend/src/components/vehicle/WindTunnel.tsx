"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Wind } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { LineChartBands } from "@/components/charts/Charts";
import { Studio } from "@/components/engine/Engine3D";
import { Figures } from "@/components/layout";
import { ComputePicker } from "@/components/project/ProjectBar";
import { Button, Card, ErrorNote, Note, Segmented, Spinner, useAsync } from "@/components/ui";
import { api, waitForJob } from "@/lib/api";
import { fmt } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Json, Param, VehicleDesign } from "@/lib/types";
import { type BodyGeometry, Orbit } from "./BodyDesigner";
import { BodySurface, type Surface, useBodySurface } from "./BodyMesh3D";

type Resolution = "draft" | "standard" | "fine";

interface Streamline {
  points: [number, number, number][];
  speed: number[];
}

export interface TunnelResult {
  cd: number;
  cl: number;
  history: { step: number; cd: number; cl: number }[];
  frontal_area_m2: number;
  grid: { nx: number; ny: number; nz: number; cells: number; dx_m: number; steps: number; reynolds: number; resolution: string };
  slices: {
    centre_plane: { speed: (number | null)[][]; cp: (number | null)[][] };
    plan_view: { speed: (number | null)[][] };
    stride: number;
    dx_m: number;
    x0_m: number;
    plan_height_m: number;
    extent_x_m: number;
    extent_y_m: number;
    extent_z_m: number;
  };
  surface_pressure: { x: number[]; y: number[]; z: number[]; cp: number[] };
  streamlines: Streamline[];
  max_speed_ratio: number;
  seconds: number;
  compute: { backend: string; device: string; kernel?: string };
  assumptions: string[];
  body?: { source: "loft" | "mesh"; triangles: number; length_m: number; width_m: number; height_m: number };
}

interface RunRecord {
  label: string;
  resolution: string;
  cd: number;
  cl: number;
  area: number;
}

const RESOLUTION_HINT: Record<Resolution, string> = {
  draft: "≈ 0.2 M cells · seconds on a GPU",
  standard: "≈ 1.3 M cells · about a minute on a laptop GPU",
  fine: "≈ 3.5 M cells · several minutes; best on a Kaggle or Colab worker",
};

const AIR_DENSITY = 1.204; // kg/m³ at 20 °C, sea level
const V_REF = 100 / 3.6; // 100 km/h

// ---------------------------------------------------------------- colour scales

// Perceptually uniform sequential ramp (viridis stops) for speed.
const SEQ: [number, number, number][] = [
  [68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142], [38, 130, 142],
  [31, 158, 137], [53, 183, 121], [109, 205, 89], [180, 222, 44], [253, 231, 37],
];
// Diverging ramp for pressure coefficient: suction blue, stagnation red, neutral at Cp = 0.
const DIV: [number, number, number][] = [
  [33, 102, 172], [103, 169, 207], [209, 229, 240], [247, 247, 247], [253, 219, 199], [239, 138, 98], [178, 24, 43],
];

function ramp(stops: [number, number, number][], t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const a = stops[i];
  const b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

const CP_MIN = -1.0;
const CP_MAX = 1.0;
/** Map Cp onto the diverging ramp with 0 at the centre (asymmetric range, each side scaled separately). */
const cpT = (cp: number) => (cp < 0 ? 0.5 - 0.5 * Math.min(1, cp / CP_MIN) : 0.5 + 0.5 * Math.min(1, cp / CP_MAX));
/** Ramp colour (sRGB 0-255) as linear RGB for three.js vertex colours. */
const linear = (c: [number, number, number]) => {
  const col = new THREE.Color().setRGB(c[0] / 255, c[1] / 255, c[2] / 255, THREE.SRGBColorSpace);
  return [col.r, col.g, col.b];
};
const css = ([r, g, b]: [number, number, number]) => `rgb(${r | 0},${g | 0},${b | 0})`;

// ---------------------------------------------------------------- 3D scene

/** Tunnel coordinates (x from nose, y lateral, z up) to scene coordinates (x along the car centred, y up, z lateral). */
function toScene(p: [number, number, number], L: number): [number, number, number] {
  return [p[0] - L / 2, p[2], p[1]];
}

function Streamlines({ lines, L, maxSpeed }: { lines: Streamline[]; L: number; maxSpeed: number }) {
  const geom = useMemo(() => {
    const pos: number[] = [];
    const col: number[] = [];
    for (const line of lines) {
      for (let i = 0; i < line.points.length - 1; i++) {
        for (const k of [i, i + 1]) {
          pos.push(...toScene(line.points[k], L));
          col.push(...linear(ramp(SEQ, line.speed[k] / maxSpeed)));
        }
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    return g;
  }, [lines, L, maxSpeed]);
  useEffect(() => () => geom.dispose(), [geom]);
  return (
    <lineSegments geometry={geom}>
      <lineBasicMaterial vertexColors transparent opacity={0.6} toneMapped={false} />
    </lineSegments>
  );
}

/** Tracer particles advected along the streamlines at the local flow speed. */
function Tracers({ lines, L }: { lines: Streamline[]; L: number }) {
  const PER_LINE = 5;
  const count = lines.length * PER_LINE;
  const points = useRef<THREE.Points>(null);
  const phase = useRef<Float32Array | null>(null);
  const initial = useMemo(() => new Float32Array(count * 3), [count]);
  useFrame((_, dt) => {
    const obj = points.current;
    if (!obj) return;
    if (!phase.current || phase.current.length !== count) {
      phase.current = new Float32Array(count).map((_, i) => (i % PER_LINE) / PER_LINE);
    }
    const pos = obj.geometry.attributes.position as THREE.BufferAttribute;
    const ph = phase.current;
    lines.forEach((line, li) => {
      const n = line.points.length;
      for (let k = 0; k < PER_LINE; k++) {
        const idx = li * PER_LINE + k;
        const at = Math.min(n - 1, Math.floor(ph[idx] * (n - 1)));
        // Advance by local speed so tracers visibly slow in the wake and speed up over the roof.
        ph[idx] = (ph[idx] + (dt * 0.12 * Math.max(0.15, line.speed[at] ?? 1)) / Math.max(1, n / 60)) % 1;
        const f = ph[idx] * (n - 1);
        const i0 = Math.min(n - 2, Math.floor(f));
        const t = f - i0;
        const a = toScene(line.points[i0], L);
        const b = toScene(line.points[i0 + 1], L);
        pos.setXYZ(idx, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t);
      }
    });
    pos.needsUpdate = true;
  });
  return (
    <points ref={points} key={count}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[initial, 3]} />
      </bufferGeometry>
      <pointsMaterial color="#ffffff" size={0.045} sizeAttenuation transparent opacity={0.9} toneMapped={false} />
    </points>
  );
}

function SurfacePressure({ s, L }: { s: TunnelResult["surface_pressure"]; L: number }) {
  const geom = useMemo(() => {
    const pos = new Float32Array(s.x.length * 3);
    const col = new Float32Array(s.x.length * 3);
    for (let i = 0; i < s.x.length; i++) {
      const p = toScene([s.x[i], s.y[i], s.z[i]], L);
      pos.set(p, i * 3);
      col.set(linear(ramp(DIV, cpT(s.cp[i]))), i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    return g;
  }, [s, L]);
  useEffect(() => () => geom.dispose(), [geom]);
  return (
    <points geometry={geom}>
      <pointsMaterial vertexColors size={0.075} sizeAttenuation toneMapped={false} />
    </points>
  );
}

type Layer = "streamlines" | "pressure" | "both";

function TunnelScene({ surface, res, layer }: { surface: Surface; res: TunnelResult; layer: Layer }) {
  const L = res.body?.length_m ?? surface.length;
  return (
    <Canvas camera={{ position: [4.2, 2.2, 5.4], fov: 34 }} dpr={[1, 2]} gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}>
      <Studio />
      <directionalLight position={[5, 8, 3]} intensity={1.2} />
      <BodySurface surface={surface} ghost={layer === "both"} />
      {layer !== "pressure" && (
        <>
          <Streamlines lines={res.streamlines} L={L} maxSpeed={Math.max(1.2, res.max_speed_ratio)} />
          <Tracers lines={res.streamlines} L={L} />
        </>
      )}
      {layer !== "streamlines" && <SurfacePressure s={res.surface_pressure} L={L} />}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[res.slices.extent_x_m / 2 - res.slices.x0_m - L / 2, 0, 0]}>
        <planeGeometry args={[res.slices.extent_x_m, res.slices.extent_y_m]} />
        <meshStandardMaterial color="#060607" roughness={0.95} envMapIntensity={0.1} />
      </mesh>
      <Orbit />
    </Canvas>
  );
}

// ---------------------------------------------------------------- slices

function SliceView({
  title,
  subtitle,
  values,
  kind,
  width,
  height,
  vmax,
  originX = 0,
  originY = 0,
  yLabel,
}: {
  title: string;
  subtitle: string;
  values: (number | null)[][]; // [row from floor/side][x]
  kind: "speed" | "cp";
  width: number; // metres
  height: number;
  vmax: number;
  originX?: number; // metres subtracted from the readout (car nose / centreline at 0)
  originY?: number;
  yLabel: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number; v: number | null } | null>(null);
  const rows = values.length;
  const cols = values[0]?.length ?? 0;
  const color = (v: number) => (kind === "speed" ? ramp(SEQ, v / vmax) : ramp(DIV, cpT(v)));

  useEffect(() => {
    const c = ref.current;
    if (!c || !rows || !cols) return;
    c.width = cols;
    c.height = rows;
    const ctx = c.getContext("2d")!;
    const img = ctx.createImageData(cols, rows);
    for (let r = 0; r < rows; r++) {
      for (let x = 0; x < cols; x++) {
        const v = values[r][x];
        const o = ((rows - 1 - r) * cols + x) * 4; // row 0 is the floor: draw it at the bottom
        const [R, G, B] = v == null ? [58, 61, 68] : color(v);
        img.data.set([R, G, B, 255], o);
      }
    }
    ctx.putImageData(img, 0, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values, rows, cols, vmax, kind]);

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const b = e.currentTarget.getBoundingClientRect();
    const fx = (e.clientX - b.left) / b.width;
    const fy = 1 - (e.clientY - b.top) / b.height;
    const x = Math.min(cols - 1, Math.floor(fx * cols));
    const r = Math.min(rows - 1, Math.floor(fy * rows));
    setHover({ x: fx * width - originX, y: fy * height - originY, v: values[r]?.[x] ?? null });
  };

  const legend = kind === "speed" ? [0, vmax / 2, vmax] : [CP_MIN, 0, CP_MAX];
  return (
    <Card title={title} subtitle={subtitle}>
      <canvas
        ref={ref}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        className="block w-full border border-line"
        style={{ aspectRatio: `${width} / ${height}`, imageRendering: "auto" }}
        role="img"
        aria-label={`${title}: ${kind === "speed" ? "flow speed relative to free stream" : "pressure coefficient"}`}
      />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-ink-3 tabular">
        <div className="flex items-center gap-2">
          <span>{fmt(legend[0], 1)}</span>
          <span
            className="h-2 w-40 border border-line"
            style={{
              background: `linear-gradient(to right, ${(kind === "speed" ? SEQ : DIV).map((s) => css(s)).join(",")})`,
            }}
            aria-hidden
          />
          <span>{fmt(legend[2], 1)}</span>
          <span className="ml-1">{kind === "speed" ? "|u| / U∞" : "Cp"}</span>
        </div>
        <span>
          {hover
            ? `${fmt(hover.x, 2)} m from nose · ${yLabel} ${fmt(hover.y, 2)} m · ${hover.v == null ? "inside body" : fmt(hover.v, 2)}`
            : "Hover to read values · grey is the body"}
        </span>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- tab

export function WindTunnel({
  design,
  onChange,
  target,
  setTarget,
}: {
  design: VehicleDesign;
  onChange: (d: VehicleDesign) => void;
  target: string;
  setTarget: (t: string) => void;
}) {
  const { meta } = useSession();
  const bodyId = Object.entries(design.components).find(([, c]) => c.type === "body")?.[0];
  const body = bodyId ? design.components[bodyId] : null;
  const stored = (body?.params as Json | null)?.geometry as BodyGeometry | undefined;
  const [fallback, setFallback] = useState<BodyGeometry | null>(null);
  const g = stored ?? fallback;
  const [resolution, setResolution] = useState<Resolution>("standard");
  const [layer, setLayer] = useState<Layer>("streamlines");
  const [res, setRes] = useState<TunnelResult | null>(null);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [status, setStatus] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const act = useAsync();
  const { surface } = useBodySurface(g);

  useEffect(() => {
    if (!stored) api<BodyGeometry>("/api/v1/body/default").then(setFallback).catch(() => undefined);
  }, [stored]);

  useEffect(() => {
    if (!act.busy) return;
    const started = Date.now();
    const t = setInterval(() => setElapsed((Date.now() - started) / 1000), 500);
    return () => clearInterval(t);
  }, [act.busy]);

  const run = () =>
    act.run(async () => {
      setElapsed(0);
      const job = await api<{ id: string }>("/api/v1/aero/run", { method: "POST", json: { geometry: g, resolution, target } });
      const r = await waitForJob<TunnelResult>(job.id, setStatus);
      setRes(r);
      setRuns((prev) => [
        { label: `Run ${prev.length + 1}`, resolution: r.grid.resolution, cd: r.cd, cl: r.cl, area: r.frontal_area_m2 },
        ...prev,
      ].slice(0, 8));
    });

  const applyCd = () => {
    if (!res || !bodyId || !body?.params) return;
    const p = body.params as Record<string, Param | unknown>;
    const cd = p.drag_coefficient as Param | undefined;
    const params = {
      ...p,
      drag_coefficient: {
        ...(cd ?? {}),
        value: +res.cd.toFixed(3),
        tol: +(res.cd * 0.2).toFixed(3),
        source: "simulated",
        ref: `Wind tunnel (${res.grid.resolution}, Re ${res.grid.reynolds}); low-Reynolds estimate, ±20 %`,
      },
    };
    onChange({ ...design, components: { ...design.components, [bodyId]: { ...body, params } } });
  };

  const resolutions = meta?.wind_tunnel?.resolutions ?? [];
  const cda = res ? res.cd * res.frontal_area_m2 : 0;
  // Skip the start-up transient (impulsive start) so the chart scale shows the settling.
  const settled = res ? res.history.filter((h) => h.step >= res.grid.steps * 0.1) : [];
  const dragN = 0.5 * AIR_DENSITY * V_REF * V_REF * cda;

  return (
    <div className="space-y-6">
      <Card
        title="Virtual wind tunnel"
        subtitle="Full 3D lattice-Boltzmann flow around the body you sketched, with a moving road. The whole tunnel updates in parallel on the GPU, one CUDA thread per cell."
        actions={<ComputePicker value={target} onChange={setTarget} />}
      >
        <div className="flex flex-wrap items-center gap-4">
          <Segmented<Resolution>
            options={(resolutions.length ? resolutions.map((r) => r.id as Resolution) : (["draft", "standard", "fine"] as Resolution[])).map((id) => ({
              id,
              label: id[0].toUpperCase() + id.slice(1),
            }))}
            value={resolution}
            onChange={setResolution}
          />
          <span className="text-xs text-ink-3">{RESOLUTION_HINT[resolution]}</span>
          <Button variant="primary" onClick={run} loading={act.busy} disabled={!g} className="ml-auto">
            <Wind className="size-3.5" aria-hidden /> Run wind tunnel
          </Button>
        </div>
        <p className="mt-3 text-xs text-ink-3">
          {!stored
            ? "No sketch saved on this body yet, so the default body is tested. Shape yours in Body design and apply it."
            : g?.mesh_id
              ? "Testing the imported CAD mesh applied in Body design."
              : "Testing the detailed loft of the body sketch applied in Body design (wheel wells, glasshouse, diffuser)."}
        </p>
      </Card>
      <ErrorNote error={act.error} onClose={() => act.setError(null)} />
      {act.busy && <Spinner label={`Solving the flow · ${status || "queued"} · ${fmt(elapsed, 0)} s`} />}

      {res && g && surface && (
        <>
          <Figures
            items={[
              { label: "Drag coefficient", value: fmt(res.cd, 3), sub: `Cl ${fmt(res.cl, 3)} (${res.cl > 0 ? "lift" : "downforce"})` },
              { label: "Drag area CdA", value: fmt(cda, 3), unit: "m²", sub: `Frontal area ${fmt(res.frontal_area_m2, 2)} m²` },
              { label: "Drag at 100 km/h", value: fmt(dragN, 0), unit: "N", sub: `${fmt((dragN * V_REF) / 1000, 1)} kW to push through air` },
              {
                label: "Solve",
                value: fmt(res.seconds, 0),
                unit: "s",
                sub: `${fmt(res.grid.cells / 1e6, 2)} M cells · ${res.grid.steps} steps · ${res.compute.device}`,
              },
            ]}
          />

          <div className="relative overflow-hidden border border-line" style={{ height: 480, background: "radial-gradient(120% 90% at 50% 25%, #2a2d33 0%, #0b0c0e 55%, #050506 100%)" }}>
            <TunnelScene surface={surface} res={res} layer={layer} />
            <span className="eyebrow pointer-events-none absolute left-4 top-4 text-white/50">Flow left to right · drag to orbit</span>
            <div className="absolute right-4 top-4 flex gap-1">
              {(["streamlines", "pressure", "both"] as Layer[]).map((l) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => setLayer(l)}
                  className={`border px-3 py-1.5 font-display text-[11px] font-medium uppercase tracking-[0.16em] ${
                    layer === l ? "border-white/70 text-white" : "border-white/20 text-white/60 hover:border-white/50"
                  }`}
                >
                  {l === "pressure" ? "Surface Cp" : l}
                </button>
              ))}
            </div>
            <div className="pointer-events-none absolute bottom-4 left-4 flex items-center gap-2 text-[11px] text-white/70 tabular">
              <span>{layer === "pressure" ? `Cp ${CP_MIN}` : "slow"}</span>
              <span
                className="h-2 w-32"
                style={{ background: `linear-gradient(to right, ${(layer === "pressure" ? DIV : SEQ).map(css).join(",")})` }}
                aria-hidden
              />
              <span>{layer === "pressure" ? `+${CP_MAX}` : "fast"}</span>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <SliceView
              title="Centre plane · speed"
              subtitle="Side view through the car's centreline. Dark areas behind the body are the wake, where most of the drag comes from."
              values={res.slices.centre_plane.speed}
              kind="speed"
              width={res.slices.extent_x_m}
              height={res.slices.extent_z_m}
              originX={res.slices.x0_m}
              yLabel="height"
              vmax={Math.max(1.2, res.max_speed_ratio)}
            />
            <SliceView
              title="Centre plane · pressure"
              subtitle="Red is stagnation pressure on the nose and screen; blue is suction over the roof and in the wake."
              values={res.slices.centre_plane.cp}
              kind="cp"
              width={res.slices.extent_x_m}
              height={res.slices.extent_z_m}
              originX={res.slices.x0_m}
              yLabel="height"
              vmax={1}
            />
            <SliceView
              title="Plan view · speed"
              subtitle={`Horizontal cut ${fmt(res.slices.plan_height_m, 2)} m above the road, seen from above.`}
              values={res.slices.plan_view.speed}
              kind="speed"
              width={res.slices.extent_x_m}
              height={res.slices.extent_y_m}
              originX={res.slices.x0_m}
              originY={res.slices.extent_y_m / 2}
              yLabel="lateral"
              vmax={Math.max(1.2, res.max_speed_ratio)}
            />
            <LineChartBands
              title="Convergence"
              subtitle="Force coefficients after the start-up transient. The reported value is the mean of the last 30 %; a flat tail means the flow has settled."
              x={settled.map((h) => h.step)}
              xLabel="Time step"
              unit=""
              series={[
                { id: "cd", label: "Cd", color: "var(--s1)", values: settled.map((h) => h.cd) },
                { id: "cl", label: "Cl", color: "var(--s2)", values: settled.map((h) => h.cl) },
              ]}
            />
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
            <Card
              title="Runs this session"
              subtitle="Change the sketch in Body design and run again to compare shapes at the same resolution."
              actions={
                bodyId && body?.params ? (
                  <Button onClick={applyCd} size="sm">
                    Use Cd {fmt(res.cd, 3)} in vehicle model
                  </Button>
                ) : undefined
              }
            >
              <table className="w-full text-sm tabular">
                <thead className="text-left text-xs text-ink-2">
                  <tr>
                    <th className="py-1.5 font-medium">Run</th>
                    <th className="py-1.5 font-medium">Resolution</th>
                    <th className="py-1.5 text-right font-medium">Cd</th>
                    <th className="py-1.5 text-right font-medium">Cl</th>
                    <th className="py-1.5 text-right font-medium">CdA m²</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.label} className="border-t border-line">
                      <td className="py-1.5">{r.label}</td>
                      <td className="py-1.5 capitalize">{r.resolution}</td>
                      <td className="py-1.5 text-right">{fmt(r.cd, 3)}</td>
                      <td className="py-1.5 text-right">{fmt(r.cl, 3)}</td>
                      <td className="py-1.5 text-right">{fmt(r.cd * r.area, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Note tone="warning">
              <div className="space-y-1.5">
                <p className="font-medium text-ink">How far to trust these numbers</p>
                {res.assumptions.map((a) => (
                  <p key={a}>{a}</p>
                ))}
                <p>
                  Grid {res.grid.nx} × {res.grid.ny} × {res.grid.nz}, cell {fmt(res.grid.dx_m * 1000, 0)} mm, Reynolds {fmt(res.grid.reynolds, 0)},{" "}
                  {res.compute.kernel ?? res.compute.backend}.
                </p>
              </div>
            </Note>
          </div>
        </>
      )}
    </div>
  );
}
