"use client";

import { Canvas, useThree } from "@react-three/fiber";
import { Box, Download, Globe, Grid3x3, RotateCcw, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLExporter } from "three/examples/jsm/exporters/STLExporter.js";
import { Studio } from "@/components/engine/Engine3D";
import { ResearchPanel } from "@/components/ResearchPanel";
import { Button, Card, ErrorNote, Field, Input, Note, Select, Stat, useAsync } from "@/components/ui";
import { api, API_URL, getToken } from "@/lib/api";
import { num } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Json, Param, VehicleDesign } from "@/lib/types";
import { BodySurface, type ImportedMesh, useBodySurface } from "./BodyMesh3D";

type Pt = [number, number];

export interface BodyGeometry {
  length_mm: number;
  width_mm: number;
  height_mm: number;
  wheelbase_mm: number;
  front_overhang_mm: number;
  ground_clearance_mm: number;
  wheel_diameter_mm: number;
  panel_thickness_mm: number;
  panel_material_id: string;
  side_profile: Pt[];
  front_section: Pt[];
  applied_panel_mass_kg?: number | null;
  beltline?: number;
  tumblehome?: number;
  plan_taper_front?: number;
  plan_taper_rear?: number;
  arch_clearance_mm?: number;
  mesh_id?: string | null;
}

interface BodyAnalysis {
  frontal_area_m2: number;
  side_area_m2: number;
  panel_area_m2: number;
  panel_mass_kg: number;
  panel_mass_tol_kg: number;
  panel_cg_height_m: number;
  envelope_volume_m3: number;
  mean_width_m: number;
  rear_overhang_mm: number;
  material: { id: string; name: string; density: number };
  warnings: string[];
  assumptions: string[];
}

// ---------------------------------------------------------------- curves

/** Catmull-Rom spline through the control points, sampled for drawing and meshing. */
function spline(points: Pt[], perSegment = 12): Pt[] {
  if (points.length < 2) return points;
  const out: Pt[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(i - 1, 0)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(i + 2, points.length - 1)];
    for (let k = 0; k < perSegment; k++) {
      const t = k / perSegment;
      const t2 = t * t;
      const t3 = t2 * t;
      const f = (a: number, b: number, c: number, d: number) =>
        0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
      out.push([f(p0[0], p1[0], p2[0], p3[0]), f(p0[1], p1[1], p2[1], p3[1])]);
    }
  }
  out.push(points[points.length - 1]);
  return out;
}

// ---------------------------------------------------------------- 2D sketch editor

function SketchEditor({
  title,
  points,
  onChange,
  widthMm,
  heightMm,
  mirror,
  orderedX,
  overlay,
}: {
  title: string;
  points: Pt[];
  onChange: (p: Pt[]) => void;
  widthMm: number; // drawing width represented by x = 0..1 (half-width for mirrored sections)
  heightMm: number;
  mirror?: boolean;
  orderedX?: boolean;
  overlay?: (toX: (x: number) => number, toY: (y: number) => number) => React.ReactNode;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<number | null>(null);
  const pad = 40;
  const W = 1000;
  const H = Math.max(160, Math.min(700, (heightMm / (mirror ? widthMm * 2 : widthMm)) * W));
  const x0 = mirror ? W / 2 : pad;
  const xs = mirror ? (W / 2 - pad) : W - 2 * pad;
  const toX = (x: number) => x0 + x * xs;
  const toY = (y: number) => H - pad - y * (H - 2 * pad);
  const fromEvent = (e: React.PointerEvent): Pt => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return [(p.x - x0) / xs, (H - pad - p.y) / (H - 2 * pad)];
  };
  const clamp = (v: number) => Math.min(1, Math.max(0, v));

  const move = (e: React.PointerEvent) => {
    if (drag === null) return;
    const [x, y] = fromEvent(e);
    const next = points.map((p) => [...p] as Pt);
    let nx = clamp(x);
    if (orderedX) {
      const lo = drag > 0 ? next[drag - 1][0] + 0.005 : 0;
      const hi = drag < next.length - 1 ? next[drag + 1][0] - 0.005 : 1;
      nx = Math.min(hi, Math.max(lo, nx));
    }
    next[drag] = [+nx.toFixed(4), +clamp(y).toFixed(4)];
    onChange(next);
  };

  const insert = (e: React.MouseEvent) => {
    const [x, y] = fromEvent(e as unknown as React.PointerEvent);
    let best = 0;
    let bestD = Infinity;
    for (let i = 0; i < points.length - 1; i++) {
      const [ax, ay] = points[i];
      const [bx, by] = points[i + 1];
      const d = Math.hypot((ax + bx) / 2 - x, (ay + by) / 2 - y);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    const next = [...points];
    next.splice(best + 1, 0, [+clamp(x).toFixed(4), +clamp(y).toFixed(4)]);
    onChange(next);
  };

  const curve = spline(points);
  const d = curve.map((p, i) => `${i ? "L" : "M"}${toX(p[0])},${toY(p[1])}`).join(" ");
  const dMirror = curve.map((p, i) => `${i ? "L" : "M"}${toX(-p[0])},${toY(p[1])}`).join(" ");
  const gridStep = 250; // mm
  const gridXs = Array.from({ length: Math.floor(widthMm / gridStep) + 1 }, (_, i) => (i * gridStep) / widthMm);
  const gridYs = Array.from({ length: Math.floor(heightMm / gridStep) + 1 }, (_, i) => (i * gridStep) / heightMm);

  return (
    <div className="border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <span className="display text-[13px]">{title}</span>
        <span className="eyebrow">Drag · double-click to add · right-click to remove</span>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full touch-none select-none"
        onPointerMove={move}
        onPointerUp={() => setDrag(null)}
        onPointerLeave={() => setDrag(null)}
        onDoubleClick={insert}
        role="img"
        aria-label={title}
      >
        {gridXs.map((gx) => (
          <g key={`gx${gx}`}>
            <line x1={toX(gx)} x2={toX(gx)} y1={pad / 2} y2={H - pad} stroke="var(--grid)" strokeWidth={1} />
            {mirror && gx > 0 && <line x1={toX(-gx)} x2={toX(-gx)} y1={pad / 2} y2={H - pad} stroke="var(--grid)" strokeWidth={1} />}
          </g>
        ))}
        {gridYs.map((gy) => (
          <line key={`gy${gy}`} x1={mirror ? pad : toX(0)} x2={mirror ? W - pad : toX(1)} y1={toY(gy)} y2={toY(gy)} stroke="var(--grid)" strokeWidth={1} />
        ))}
        <line x1={pad / 2} x2={W - pad / 2} y1={toY(0)} y2={toY(0)} stroke="var(--axis)" strokeWidth={1} />
        {mirror && <line x1={toX(0)} x2={toX(0)} y1={pad / 2} y2={H - pad / 2} stroke="var(--axis)" strokeDasharray="4 4" />}
        {overlay?.(toX, toY)}
        {mirror && <path d={dMirror} fill="none" stroke="var(--ink-3)" strokeWidth={1.5} />}
        <path d={d} fill="none" stroke="var(--ink)" strokeWidth={2} />
        {points.map((p, i) => (
          <g key={i}>
            <circle
              cx={toX(p[0])}
              cy={toY(p[1])}
              r={14}
              fill="transparent"
              className="cursor-grab"
              onPointerDown={(e) => {
                (e.target as Element).setPointerCapture?.(e.pointerId);
                setDrag(i);
              }}
              onContextMenu={(e) => {
                e.preventDefault();
                if (points.length > 4) onChange(points.filter((_, j) => j !== i));
              }}
            />
            <rect x={toX(p[0]) - 5} y={toY(p[1]) - 5} width={10} height={10} fill={drag === i ? "var(--ink)" : "var(--surface)"} stroke="var(--ink)" strokeWidth={1.5} pointerEvents="none" />
          </g>
        ))}
        <text x={pad / 2} y={18} className="fill-[var(--ink-3)] text-[13px]">
          {num(mirror ? widthMm * 2 : widthMm)} mm × {num(heightMm)} mm · grid {gridStep} mm
        </text>
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------- 3D preview

export function Orbit() {
  const { camera, gl } = useThree();
  useEffect(() => {
    const c = new OrbitControls(camera, gl.domElement);
    c.enableDamping = true;
    c.target.set(0, 0.6, 0);
    c.update();
    return () => c.dispose();
  }, [camera, gl]);
  return null;
}

// ---------------------------------------------------------------- designer

const DIMENSIONS: [keyof BodyGeometry, string][] = [
  ["length_mm", "Length"],
  ["width_mm", "Width"],
  ["height_mm", "Height"],
  ["wheelbase_mm", "Wheelbase"],
  ["front_overhang_mm", "Front overhang"],
  ["ground_clearance_mm", "Ground clearance"],
  ["wheel_diameter_mm", "Wheel diameter"],
  ["panel_thickness_mm", "Panel thickness"],
];

export function BodyDesigner({ design, onChange }: { design: VehicleDesign; onChange: (d: VehicleDesign) => void }) {
  const { materials, meta } = useSession();
  const bodyId = Object.entries(design.components).find(([, c]) => c.type === "body")?.[0];
  const body = bodyId ? design.components[bodyId] : null;
  const stored = (body?.params as Json | null)?.geometry as BodyGeometry | undefined;
  const [g, setG] = useState<BodyGeometry | null>(stored ?? null);
  const [analysis, setAnalysis] = useState<BodyAnalysis | null>(null);
  const [showSearch, setShowSearch] = useState(false);
  const [wireframe, setWireframe] = useState(true);
  const groupRef = useRef<THREE.Group>(null);
  const act = useAsync();
  const { surface, error: surfaceError } = useBodySurface(g);

  // Start from the stored sketch or the default one.
  useEffect(() => {
    if (!g) api<BodyGeometry>("/api/v1/body/default").then(setG).catch((e) => act.setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-analyse (debounced) whenever the sketch changes.
  useEffect(() => {
    if (!g) return;
    const t = setTimeout(() => {
      api<BodyAnalysis>("/api/v1/body/analyze", { method: "POST", json: { geometry: g } })
        .then((a) => {
          setAnalysis(a);
          act.setError(null);
        })
        .catch((e) => act.setError(e instanceof Error ? e.message : String(e)));
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g]);

  const panelMaterials = materials.filter((m) => m.properties.density);
  const set = (patch: Partial<BodyGeometry>) => setG((cur) => (cur ? { ...cur, ...patch } : cur));

  const apply = () => {
    if (!g || !analysis || !bodyId || !body?.params) return;
    const p = body.params as Record<string, Param | unknown>;
    const mass = p.mass as Param;
    const previous = g.applied_panel_mass_kg ?? analysis.panel_mass_kg;
    const newMass = mass.value + (analysis.panel_mass_kg - previous);
    const params = {
      ...p,
      frontal_area: { value: +analysis.frontal_area_m2.toFixed(3), tol: +(analysis.frontal_area_m2 * 0.03).toFixed(3), source: "calculated", ref: "Body designer: front section area" },
      wheelbase: { ...(p.wheelbase as Param), value: g.wheelbase_mm / 1000, source: "user", ref: "Body designer" },
      mass: { ...mass, value: +newMass.toFixed(1), ref: `${mass.ref ?? ""}${mass.ref ? "; " : ""}adjusted for body panel mass change` },
      geometry: { ...g, applied_panel_mass_kg: analysis.panel_mass_kg },
    };
    onChange({ ...design, components: { ...design.components, [bodyId]: { ...body, params } } });
    setG({ ...g, applied_panel_mass_kg: analysis.panel_mass_kg });
  };

  const exportStl = () => {
    if (!groupRef.current) return;
    const data = new STLExporter().parse(groupRef.current, { binary: true }) as DataView;
    const url = URL.createObjectURL(new Blob([data.buffer as ArrayBuffer], { type: "model/stl" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${design.name.replace(/\W+/g, "_")}_body.stl`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!bodyId) return <Note>Add a “Vehicle body & mass properties” component in Architecture to design the body.</Note>;
  if (!g) return <ErrorNote error={act.error} />;

  const L = g.length_mm;
  const wheelR = g.wheel_diameter_mm / 2;
  const fa = g.front_overhang_mm;
  const ra = fa + g.wheelbase_mm;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
          <SketchEditor
            title="Side profile"
            points={g.side_profile}
            onChange={(p) => set({ side_profile: p })}
            widthMm={L}
            heightMm={g.height_mm}
            orderedX
            overlay={(toX, toY) => {
              const hN = (v: number) => (v - g.ground_clearance_mm) / (g.height_mm - g.ground_clearance_mm);
              const sx = (mm: number) => toX(mm / L);
              const ry = Math.abs(toY(hN(wheelR * 2)) - toY(hN(0)));
              const rx = Math.abs(sx(wheelR) - sx(0));
              return (
                <g>
                  {[fa, ra].map((ax) => (
                    <ellipse key={ax} cx={sx(ax)} cy={(toY(hN(0)) + toY(hN(wheelR * 2))) / 2} rx={rx} ry={ry / 2} fill="none" stroke="var(--ink-3)" strokeDasharray="4 4" />
                  ))}
                  <line x1={sx(fa)} x2={sx(ra)} y1={toY(hN(0)) + 8} y2={toY(hN(0)) + 8} stroke="var(--ink-3)" />
                  <text x={(sx(fa) + sx(ra)) / 2} y={toY(hN(0)) + 27} textAnchor="middle" className="fill-[var(--ink-2)] text-[13px]">
                    wheelbase {num(g.wheelbase_mm)} mm
                  </text>
                </g>
              );
            }}
          />
          <div className="relative overflow-hidden border border-line" style={{ height: 420, background: "radial-gradient(120% 90% at 50% 25%, #2a2d33 0%, #0b0c0e 55%, #050506 100%)" }}>
            <Canvas camera={{ position: [4.6, 2.4, 4.8], fov: 32 }} dpr={[1, 2]} gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}>
              <Studio />
              <directionalLight position={[5, 8, 3]} intensity={1.4} />
              <directionalLight position={[-6, 3, -4]} intensity={0.5} color="#9fb4ff" />
              {surface && <BodySurface surface={surface} wireframe={wireframe} groupRef={groupRef} />}
              <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
                <circleGeometry args={[6, 64]} />
                <meshStandardMaterial color="#060607" roughness={0.9} envMapIntensity={0.15} />
              </mesh>
              <Orbit />
            </Canvas>
            <span className="eyebrow pointer-events-none absolute left-4 top-4 text-white/50">
              {surface?.kind === "mesh" ? `Imported mesh · ${num(surface.info.triangles)} triangles` : surface?.kind === "loft" ? `Lofted surface · ${num(surface.data.stats.quads)} quads` : "Building surface…"}
            </span>
            <button
              type="button"
              onClick={() => setWireframe((w) => !w)}
              className={`absolute right-4 top-4 inline-flex items-center gap-2 border px-3 py-1.5 font-display text-[11px] font-medium uppercase tracking-[0.16em] ${wireframe ? "border-white/70 text-white" : "border-white/20 text-white/70 hover:border-white/50"}`}
            >
              <Grid3x3 className="size-3.5" /> Wireframe
            </button>
            <button
              type="button"
              onClick={exportStl}
              className="absolute bottom-4 right-4 inline-flex items-center gap-2 border border-white/20 px-3 py-1.5 font-display text-[11px] font-medium uppercase tracking-[0.16em] text-white/80 hover:border-white/60"
            >
              <Download className="size-3.5" /> Export STL
            </button>
          </div>

      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,560px)_1fr]">
          <SketchEditor
            title="Front section (mirrored)"
            points={g.front_section}
            onChange={(p) => set({ front_section: p })}
            widthMm={g.width_mm / 2}
            heightMm={g.height_mm}
            mirror
          />
          <Card title="Dimensions & panels">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {DIMENSIONS.map(([k, label]) => (
                <Field key={k} label={`${label} (mm)`}>
                  <Input type="number" step={k === "panel_thickness_mm" ? 0.1 : 10} value={g[k] as number} onChange={(e) => set({ [k]: Number(e.target.value) } as Partial<BodyGeometry>)} />
                </Field>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <Field label="Panel material">
                <Select value={g.panel_material_id} onChange={(e) => set({ panel_material_id: e.target.value })} className="w-72">
                  {panelMaterials.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} {m.condition}
                      {m.custom ? " (custom)" : ""}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button onClick={() => setShowSearch((v) => !v)}>
                <Globe className="size-3.5" /> {showSearch ? "Close search" : "Find a material on the web"}
              </Button>
              <Field label="Start from a body style">
                <Select
                  value=""
                  onChange={(e) => {
                    const style = meta?.body_styles?.find((b) => b.id === e.target.value);
                    if (style)
                      setG({
                        ...(style.geometry as unknown as BodyGeometry),
                        panel_material_id: g.panel_material_id,
                        panel_thickness_mm: g.panel_thickness_mm,
                        applied_panel_mass_kg: g.applied_panel_mass_kg,
                      });
                  }}
                  className="w-56"
                >
                  <option value="">Choose a style…</option>
                  {(meta?.body_styles ?? []).map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button variant="ghost" onClick={() => api<BodyGeometry>("/api/v1/body/default").then((d) => setG({ ...d, applied_panel_mass_kg: g.applied_panel_mass_kg }))}>
                <RotateCcw className="size-3.5" /> Reset sketch
              </Button>
            </div>
            {showSearch && (
              <div className="mt-4 border-t border-line pt-4">
                <ResearchPanel
                  kind="material"
                  onSaved={(m) => {
                    set({ panel_material_id: m.id });
                    setShowSearch(false);
                  }}
                />
              </div>
            )}
          </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SurfaceDetail g={g} set={set} />
        <MeshImport g={g} set={set} />
      </div>

      <ErrorNote error={act.error ?? surfaceError} />
      {analysis && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Frontal area" value={num(analysis.frontal_area_m2)} unit="m²" sub="Feeds drag and top speed" />
            <Stat label="Side area" value={num(analysis.side_area_m2)} unit="m²" />
            <Stat label="Outer panel area" value={num(analysis.panel_area_m2)} unit="m²" sub="Approximation" />
            <Stat label="Panel mass" value={num(analysis.panel_mass_kg)} unit="kg" sub={`${analysis.material.name}, ${num(g.panel_thickness_mm)} mm`} />
            <Stat label="Panel CG height" value={num(analysis.panel_cg_height_m * 1000)} unit="mm" />
            <Stat label="Envelope volume" value={num(analysis.envelope_volume_m3)} unit="m³" sub={`rear overhang ${num(analysis.rear_overhang_mm)} mm`} />
          </div>
          {analysis.warnings.map((w) => (
            <Note key={w} tone="warning">
              {w}
            </Note>
          ))}
          <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
            <Card title="Same shape, other panel materials" subtitle="Outer-panel mass at the current thickness. Stiffness, dent resistance and formability differ too; thickness is usually adjusted per material.">
              <table className="w-full text-sm tabular">
                <tbody>
                  {panelMaterials
                    .map((m) => ({ m, mass: analysis.panel_area_m2 * (g.panel_thickness_mm / 1000) * m.properties.density.value }))
                    .sort((a, b) => a.mass - b.mass)
                    .map(({ m, mass }) => (
                      <tr key={m.id} className="border-t border-line">
                        <td className="py-2">
                          {m.name} <span className="text-xs text-ink-3">{m.condition}</span>
                        </td>
                        <td className="py-2 text-right">{num(mass)} kg</td>
                        <td className="py-2 text-right text-xs text-ink-3">
                          {mass - analysis.panel_mass_kg >= 0 ? "+" : "−"}
                          {num(Math.abs(mass - analysis.panel_mass_kg))} kg
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </Card>
            <Card
              title="Apply to the vehicle"
              subtitle="Writes the frontal area and wheelbase into the body component and adjusts the vehicle mass by the change in panel mass since the last application. Drag coefficient stays an input: it needs CFD or a wind tunnel."
              actions={
                <Button variant="primary" onClick={apply}>
                  Apply to vehicle
                </Button>
              }
            >
              <ul className="ml-4 list-disc space-y-1 text-xs text-ink-2">
                {analysis.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}


// ---------------------------------------------------------------- surface detail

const DETAIL: { key: keyof BodyGeometry; label: string; help: string; min: number; max: number; step: number; unit: string; scale: number; fallback: number }[] = [
  { key: "beltline", label: "Beltline", help: "Height where the glasshouse starts, as a share of body height.", min: 0.3, max: 0.85, step: 0.01, unit: "%", scale: 100, fallback: 0.6 },
  { key: "tumblehome", label: "Tumblehome", help: "How far the side glass leans in towards the roof.", min: 0, max: 0.4, step: 0.01, unit: "%", scale: 100, fallback: 0.14 },
  { key: "plan_taper_front", label: "Front corner rounding", help: "Plan-view taper of the front bumper corners.", min: 0, max: 0.4, step: 0.01, unit: "%", scale: 100, fallback: 0.14 },
  { key: "plan_taper_rear", label: "Rear corner rounding", help: "Plan-view taper of the rear bumper corners.", min: 0, max: 0.4, step: 0.01, unit: "%", scale: 100, fallback: 0.08 },
  { key: "arch_clearance_mm", label: "Wheel-well gap", help: "Clearance between tyre and wheel well.", min: 10, max: 150, step: 5, unit: "mm", scale: 1, fallback: 40 },
];

function SurfaceDetail({ g, set }: { g: BodyGeometry; set: (p: Partial<BodyGeometry>) => void }) {
  return (
    <Card title="Surface detail" subtitle="Shape the 3D skin beyond the two sketches. The same surface is exported and tested in the wind tunnel.">
      <div className="space-y-4">
        {DETAIL.map((d) => {
          const v = (g[d.key] as number | undefined) ?? d.fallback;
          return (
            <label key={d.key} className="grid grid-cols-[10rem_1fr_4.5rem] items-center gap-4" title={d.help}>
              <span className="text-sm">{d.label}</span>
              <input
                type="range"
                min={d.min}
                max={d.max}
                step={d.step}
                value={v}
                onChange={(e) => set({ [d.key]: Number(e.target.value) } as Partial<BodyGeometry>)}
                className="accent-[var(--ink)]"
              />
              <span className="text-right text-sm tabular">
                {num(v * d.scale)} {d.unit}
              </span>
            </label>
          );
        })}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- CAD import

function MeshImport({ g, set }: { g: BodyGeometry; set: (p: Partial<BodyGeometry>) => void }) {
  const [meshes, setMeshes] = useState<ImportedMesh[]>([]);
  const [units, setUnits] = useState("mm");
  const [up, setUp] = useState("z");
  const [offset, setOffset] = useState(0);
  const act = useAsync();
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<ImportedMesh[]>("/api/v1/body/meshes").then(setMeshes).catch(() => undefined);
  }, []);

  const upload = (file: File) =>
    act.run(async () => {
      const q = new URLSearchParams({ filename: file.name, units, up, ground_offset_mm: String(offset) });
      const token = getToken();
      const res = await fetch(`${API_URL}/api/v1/body/meshes?${q}`, {
        method: "POST",
        body: await file.arrayBuffer(),
        headers: { "content-type": "application/octet-stream", ...(token ? { authorization: `Bearer ${token}` } : {}) },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Upload failed");
      setMeshes((m) => [data as ImportedMesh, ...m]);
      set({ mesh_id: data.id });
    });

  const remove = (id: string) =>
    act.run(async () => {
      await api(`/api/v1/body/meshes/${id}`, { method: "DELETE" });
      setMeshes((m) => m.filter((x) => x.id !== id));
      if (g.mesh_id === id) set({ mesh_id: null });
    });

  const active = meshes.find((m) => m.id === g.mesh_id);
  return (
    <Card
      title="Import a CAD body"
      subtitle="Bring a detailed surface from Blender, Fusion, Onshape or any CAD tool as STL or OBJ. It is placed nose-first on the road and replaces the loft in the wind tunnel."
    >
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Units">
          <Select value={units} onChange={(e) => setUnits(e.target.value)} className="w-24">
            <option value="mm">mm</option>
            <option value="cm">cm</option>
            <option value="m">m</option>
            <option value="in">in</option>
          </Select>
        </Field>
        <Field label="Up axis">
          <Select value={up} onChange={(e) => setUp(e.target.value)} className="w-28">
            <option value="z">Z up</option>
            <option value="y">Y up</option>
          </Select>
        </Field>
        <Field label="Lift off road (mm)">
          <Input type="number" value={offset} onChange={(e) => setOffset(Number(e.target.value))} className="w-28" />
        </Field>
        <input
          ref={fileRef}
          type="file"
          accept=".stl,.obj"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
            e.target.value = "";
          }}
        />
        <Button variant="primary" onClick={() => fileRef.current?.click()} loading={act.busy}>
          <Upload className="size-3.5" /> Upload STL / OBJ
        </Button>
      </div>
      <ErrorNote error={act.error} onClose={() => act.setError(null)} />
      <div className="mt-4 divide-y divide-[var(--line)] border-y border-line">
        <button
          type="button"
          onClick={() => set({ mesh_id: null })}
          className={`flex w-full items-center gap-3 py-2.5 text-left text-sm ${!g.mesh_id ? "text-ink" : "text-ink-2 hover:text-ink"}`}
        >
          <Grid3x3 className="size-3.5" aria-hidden />
          <span className="flex-1">Lofted from the sketch</span>
          {!g.mesh_id && <span className="eyebrow">In use</span>}
        </button>
        {meshes.map((m) => (
          <div key={m.id} className="flex items-center gap-3 py-2.5 text-sm">
            <Box className="size-3.5 text-ink-3" aria-hidden />
            <button type="button" onClick={() => set({ mesh_id: m.id })} className={`flex-1 text-left ${g.mesh_id === m.id ? "text-ink" : "text-ink-2 hover:text-ink"}`}>
              {m.name}
              <span className="ml-2 text-xs text-ink-3 tabular">
                {num(m.length * 1000)} × {num(m.width * 1000)} × {num(m.height * 1000)} mm · {num(m.triangles)} triangles
              </span>
            </button>
            {g.mesh_id === m.id && <span className="eyebrow">In use</span>}
            <button type="button" onClick={() => remove(m.id)} aria-label={`Delete ${m.name}`} className="text-ink-3 hover:text-ink">
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
      {active && (
        <p className="mt-3 text-xs text-ink-3">
          Frontal area, panel mass and the other figures below still come from the sketch; the wind tunnel measures the imported mesh.
        </p>
      )}
    </Card>
  );
}
