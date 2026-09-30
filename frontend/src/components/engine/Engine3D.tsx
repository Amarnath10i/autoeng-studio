"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { StatusBadge } from "@/components/ui";
import { STATUS_LABEL } from "@/lib/format";
import type { Status } from "@/lib/types";

// 1 scene unit = 100 mm
const S = 0.01;

interface Geometry {
  cylinders: number;
  bore: number;
  stroke: number;
  rod: number;
}

/** One cylinder from the layout model: x along the crank (m), bank angle from vertical and crankpin angle (deg). */
export interface LayoutCylinder {
  index: number;
  bank: number;
  x: number;
  bank_angle: number;
  pin_angle: number;
}

/** Inline fallback while the layout loads: even-fire phasing along one bank. */
function inlineLayout(g: Geometry): LayoutCylinder[] {
  const pitch = (1.25 * g.bore) / 1000;
  return Array.from({ length: g.cylinders }, (_, i) => ({
    index: i,
    bank: 0,
    x: (i - (g.cylinders - 1) / 2) * pitch,
    bank_angle: 0,
    pin_angle: ((i % 2 === 0 ? 0 : 180) + Math.floor(i / 2) * (720 / g.cylinders)) % 360,
  }));
}

type Part = "combustion_chamber" | "connecting_rods" | "crankshaft" | "compressor" | "turbine" | "intercooler" | "cooling_system" | "intake_manifold" | "exhaust_system";

const PART_NAME: Record<Part, string> = {
  combustion_chamber: "Cylinders & pistons",
  connecting_rods: "Connecting rods",
  crankshaft: "Crankshaft",
  compressor: "Compressor (turbo / supercharger)",
  turbine: "Turbo turbine",
  intercooler: "Intercooler",
  cooling_system: "Cooling system",
  intake_manifold: "Intake manifold",
  exhaust_system: "Exhaust system",
};

function cssColor(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function statusColor(status: Status | undefined) {
  switch (status) {
    case "ok":
      return cssColor("--good", "#0ca30c");
    case "warning":
      return cssColor("--warning", "#fab219");
    case "critical":
      return cssColor("--serious", "#ec835a");
    case "failure":
      return cssColor("--critical", "#d03b3b");
    default:
      return "#8a8a86";
  }
}

/** Orbit controls, with the camera refitted to the engine's bounding sphere whenever the layout changes. */
function Controls({ targetY, radius }: { targetY: number; radius: number }) {
  const { camera, gl } = useThree();
  useEffect(() => {
    const fov = ((camera as THREE.PerspectiveCamera).fov * Math.PI) / 180;
    const dist = (radius / Math.sin(fov / 2)) * 0.95;
    const dir = new THREE.Vector3(0.95, 0.6, 1.3).normalize();
    camera.position.set(dir.x * dist, targetY + dir.y * dist, dir.z * dist);
    const c = new OrbitControls(camera, gl.domElement);
    c.enableDamping = true;
    c.target.set(0, targetY, 0);
    camera.lookAt(0, targetY, 0);
    c.update();
    return () => c.dispose();
  }, [camera, gl, targetY, radius]);
  return null;
}

// Finishes per part: forged steel, machined aluminium, cast iron, heat-blued exhaust…
const FINISH: Record<Part, { color: string; metalness: number; roughness: number }> = {
  crankshaft: { color: "#9ea3aa", metalness: 1, roughness: 0.28 },
  connecting_rods: { color: "#8b9097", metalness: 1, roughness: 0.32 },
  combustion_chamber: { color: "#d7d9dc", metalness: 1, roughness: 0.22 },
  compressor: { color: "#c9ccd0", metalness: 1, roughness: 0.3 },
  turbine: { color: "#6d6660", metalness: 0.9, roughness: 0.45 },
  intercooler: { color: "#3a3d42", metalness: 0.8, roughness: 0.5 },
  cooling_system: { color: "#2e3136", metalness: 0.7, roughness: 0.55 },
  intake_manifold: { color: "#1f2226", metalness: 0.6, roughness: 0.4 },
  exhaust_system: { color: "#7a6a5c", metalness: 0.9, roughness: 0.5 },
};

/** Metal finish; a part glows in its status colour only when a limit is at risk. */
function Mat({ part, status, hovered, opacity = 1 }: { part: Part; status: Record<string, Status>; hovered: Part | null; opacity?: number }) {
  const f = FINISH[part];
  const st = status[part];
  const atRisk = st === "warning" || st === "critical" || st === "failure";
  const glow = atRisk ? statusColor(st) : hovered === part ? "#ffffff" : "#000000";
  return (
    <meshStandardMaterial
      color={f.color}
      metalness={f.metalness}
      roughness={f.roughness}
      transparent={opacity < 1}
      opacity={opacity}
      emissive={glow}
      emissiveIntensity={atRisk ? (hovered === part ? 0.9 : 0.55) : hovered === part ? 0.12 : 0}
    />
  );
}

/** Studio reflections from a procedural room environment. */
export function Studio() {
  const gl = useThree((st) => st.gl);
  const env = useMemo(() => {
    const pm = new THREE.PMREMGenerator(gl);
    const texture = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    pm.dispose();
    return texture;
  }, [gl]);
  useEffect(() => () => env.dispose(), [env]);
  return <primitive object={env} attach="environment" />;
}

function EngineModel({ g, cyls, induction, status, onHover, hovered, speed }: {
  g: Geometry;
  cyls: LayoutCylinder[];
  induction: string;
  status: Record<string, Status>;
  onHover: (p: Part | null) => void;
  hovered: Part | null;
  speed: number;
}) {
  const r = (g.stroke / 2) * S;
  const L = g.rod * S;
  const bore = g.bore * S;
  const M = 1000 * S; // metres to scene units
  const xs = cyls.map((c) => c.x * M);
  const xMin = Math.min(...xs) - bore * 0.7;
  const xMax = Math.max(...xs) + bore * 0.7;
  const length = xMax - xMin;
  const deck = r + L + bore * 0.45;
  const pistons = useRef<THREE.Mesh[]>([]);
  const rods = useRef<THREE.Mesh[]>([]);
  const pins = useRef<THREE.Mesh[]>([]);
  const crank = useRef<THREE.Group>(null);
  const comp = useRef<THREE.Mesh>(null);
  const angle = useRef(0);

  // Banks: cylinders sharing a bank id get one head along their mean axis.
  const banks = useMemo(() => {
    const by = new Map<number, LayoutCylinder[]>();
    for (const c of cyls) by.set(c.bank, [...(by.get(c.bank) ?? []), c]);
    return [...by.values()].map((cs) => {
      const x = cs.map((c) => c.x * M);
      return {
        beta: (cs.reduce((a, c) => a + c.bank_angle, 0) / cs.length) * (Math.PI / 180),
        x0: Math.min(...x) - bore * 0.62,
        x1: Math.max(...x) + bore * 0.62,
      };
    });
  }, [cyls, bore, M]);

  useFrame((_, dt) => {
    angle.current += dt * speed * 2 * Math.PI;
    if (crank.current) crank.current.rotation.x = angle.current;
    if (comp.current) comp.current.rotation.z += dt * speed * 20;
    cyls.forEach((c, i) => {
      const beta = (c.bank_angle * Math.PI) / 180;
      const phi = angle.current + (c.pin_angle * Math.PI) / 180; // pin angle from vertical, towards +z
      const pinY = r * Math.cos(phi);
      const pinZ = r * Math.sin(phi);
      const psi = phi - beta;
      // Gudgeon pin distance from the crank centre along the bore axis.
      const s = r * Math.cos(psi) + Math.sqrt(Math.max(L * L - (r * Math.sin(psi)) ** 2, 0));
      const pistonY = s * Math.cos(beta);
      const pistonZ = s * Math.sin(beta);
      const p = pistons.current[i];
      if (p) p.position.set(0, s + bore * 0.25, 0); // piston lives in the cylinder's bore-axis frame
      const pin = pins.current[i];
      if (pin) pin.position.set(pin.position.x, pinY, pinZ);
      const rod = rods.current[i];
      if (rod) {
        rod.position.set(rod.position.x, (pinY + pistonY) / 2, (pinZ + pistonZ) / 2);
        rod.rotation.x = Math.atan2(pistonZ - pinZ, pistonY - pinY);
      }
    });
  });

  const hoverProps = (part: Part) => ({
    onPointerOver: (e: { stopPropagation: () => void }) => {
      e.stopPropagation();
      onHover(part);
    },
    onPointerOut: () => onHover(null),
  });

  const turbo = induction === "turbo";
  const supercharged = induction.startsWith("supercharger");
  const vee = banks.length > 1 && banks.every((b) => Math.abs(b.beta) < Math.PI / 2 - 0.05);
  const topY = Math.max(...banks.map((b) => Math.cos(b.beta) * (deck + bore * 0.5)));
  const sideZ = Math.max(...banks.map((b) => Math.abs(Math.sin(b.beta)) * (deck + bore * 0.5)), bore * 0.8);

  return (
    <group>
      {/* Crankshaft main journal */}
      <group ref={crank} {...hoverProps("crankshaft")}>
        <mesh rotation={[0, 0, Math.PI / 2]} position={[(xMin + xMax) / 2, 0, 0]}>
          <cylinderGeometry args={[bore * 0.12, bore * 0.12, length + bore * 0.4, 20]} />
          <Mat part="crankshaft" status={status} hovered={hovered} />
        </mesh>
      </group>
      {cyls.map((c, i) => {
        const x = c.x * M;
        const beta = (c.bank_angle * Math.PI) / 180;
        return (
          <group key={c.index}>
            <mesh ref={(m) => { if (m) pins.current[i] = m; }} position={[x, 0, 0]} rotation={[0, 0, Math.PI / 2]} {...hoverProps("crankshaft")}>
              <cylinderGeometry args={[bore * 0.1, bore * 0.1, bore * 0.3, 16]} />
              <Mat part="crankshaft" status={status} hovered={hovered} />
            </mesh>
            <mesh ref={(m) => { if (m) rods.current[i] = m; }} position={[x, r + L / 2, 0]} {...hoverProps("connecting_rods")}>
              <boxGeometry args={[bore * 0.12, L, bore * 0.18]} />
              <Mat part="connecting_rods" status={status} hovered={hovered} />
            </mesh>
            {/* Bore-axis frame: the vertical cylinder rotated by its bank angle about the crank */}
            <group position={[x, 0, 0]} rotation={[beta, 0, 0]}>
              <mesh ref={(m) => { if (m) pistons.current[i] = m; }} position={[0, r + L, 0]} {...hoverProps("combustion_chamber")}>
                <cylinderGeometry args={[bore * 0.48, bore * 0.48, bore * 0.5, 32]} />
                <Mat part="combustion_chamber" status={status} hovered={hovered} />
              </mesh>
              <mesh position={[0, r + L + bore * 0.25, 0]}>
                <cylinderGeometry args={[bore * 0.52, bore * 0.52, 2 * r + bore * 0.6, 32, 1, true]} />
                <meshStandardMaterial color="#b8bcc2" metalness={0.2} roughness={0.1} transparent opacity={0.08} side={THREE.DoubleSide} />
              </mesh>
            </group>
          </group>
        );
      })}
      {/* One cylinder head per bank, exhaust on its outer side */}
      {banks.map((b, i) => (
        <group key={i} rotation={[b.beta, 0, 0]} position={[(b.x0 + b.x1) / 2, 0, 0]}>
          <mesh position={[0, deck + bore * 0.35, 0]} {...hoverProps("intake_manifold")}>
            <boxGeometry args={[b.x1 - b.x0, bore * 0.3, bore * 1.1]} />
            <Mat part="intake_manifold" status={status} hovered={hovered} opacity={0.85} />
          </mesh>
          <mesh position={[0, deck + bore * 0.05, (b.beta < -0.01 ? -1 : 1) * bore * 0.75]} {...hoverProps("exhaust_system")}>
            <boxGeometry args={[(b.x1 - b.x0) * 0.9, bore * 0.22, bore * 0.22]} />
            <Mat part="exhaust_system" status={status} hovered={hovered} opacity={0.85} />
          </mesh>
        </group>
      ))}
      {/* Supercharger: a blower in the valley of a V, or on top of other layouts */}
      {supercharged && (
        <mesh position={[(xMin + xMax) / 2, vee ? topY * 0.92 : topY + bore * 0.45, 0]} rotation={[0, 0, Math.PI / 2]} {...hoverProps("compressor")}>
          <capsuleGeometry args={[bore * 0.42, length * 0.55, 8, 24]} />
          <Mat part="compressor" status={status} hovered={hovered} />
        </mesh>
      )}
      {/* Turbocharger: turbine and compressor housings on a shared shaft */}
      {turbo && (
        <group position={[xMax + bore * 0.6, topY * 0.8, sideZ * 0.5]}>
          <mesh rotation={[0, Math.PI / 2, 0]} {...hoverProps("turbine")}>
            <torusGeometry args={[bore * 0.35, bore * 0.16, 16, 40]} />
            <Mat part="turbine" status={status} hovered={hovered} />
          </mesh>
          <mesh position={[bore * 0.7, 0, 0]} rotation={[0, Math.PI / 2, 0]} {...hoverProps("compressor")}>
            <torusGeometry args={[bore * 0.38, bore * 0.17, 16, 40]} />
            <Mat part="compressor" status={status} hovered={hovered} />
          </mesh>
          <mesh ref={comp} position={[bore * 0.7, 0, 0]} rotation={[0, Math.PI / 2, 0]} {...hoverProps("compressor")}>
            <cylinderGeometry args={[bore * 0.22, bore * 0.22, bore * 0.08, 8]} />
            <Mat part="compressor" status={status} hovered={hovered} />
          </mesh>
        </group>
      )}
      {/* Charge cooler (none on a naturally aspirated engine) and radiator, ahead of the engine */}
      {induction !== "naturally_aspirated" && (
        <mesh position={[(xMin + xMax) / 2, r, -sideZ - bore * 1.3]} {...hoverProps("intercooler")}>
          <boxGeometry args={[length * 0.9, bore * 1.1, bore * 0.18]} />
          <Mat part="intercooler" status={status} hovered={hovered} />
        </mesh>
      )}
      <mesh position={[(xMin + xMax) / 2, r + bore * 1.2, -sideZ - bore * 1.65]} {...hoverProps("cooling_system")}>
        <boxGeometry args={[length, bore * 1.2, bore * 0.14]} />
        <Mat part="cooling_system" status={status} hovered={hovered} />
      </mesh>
    </group>
  );
}

export function Engine3D({
  geometry,
  layout,
  induction = "turbo",
  status,
  height = 380,
}: {
  geometry: Geometry;
  layout?: LayoutCylinder[] | null;
  induction?: string;
  status: Record<string, Status>;
  height?: number;
}) {
  const [hovered, setHovered] = useState<Part | null>(null);
  const [running, setRunning] = useState(true);
  const cyls = layout?.length === geometry.cylinders ? layout : inlineLayout(geometry);
  const xs = cyls.map((c) => c.x * 1000 * S);
  const span = Math.max(...xs) - Math.min(...xs) + geometry.bore * 1.4 * S;
  const reach = (geometry.stroke / 2 + geometry.rod + geometry.bore * 1.2) * S;
  const spread = Math.max(...cyls.map((c) => Math.abs(Math.sin((c.bank_angle * Math.PI) / 180))));
  const size = Math.max(span, reach * (1 + spread));
  // Bounding sphere: crank length × width across the banks (plus radiator ahead) × height.
  const width = 2 * reach * spread + geometry.bore * 3 * S;
  // Vertical centre of the model: from below the crank to the top of the highest head.
  const bottom = -(geometry.stroke / 2) * S;
  const top = reach * Math.max(...cyls.map((c) => Math.cos((c.bank_angle * Math.PI) / 180)), 0.3);
  const centreY = (bottom + top) / 2;
  return (
    <div
      className="relative overflow-hidden border border-line"
      style={{ height, background: "radial-gradient(120% 90% at 50% 20%, #23262b 0%, #0b0c0e 55%, #050506 100%)" }}
    >
      <Canvas camera={{ position: [size * 0.95, centreY + size * 0.6, size * 1.3], fov: 34 }} dpr={[1, 2]} gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}>
        <Studio />
        <ambientLight intensity={0.15} />
        <directionalLight position={[6, 9, 4]} intensity={1.6} />
        <directionalLight position={[-7, 4, -5]} intensity={0.6} color="#9fb4ff" />
        <spotLight position={[0, 8, 0]} angle={0.5} penumbra={1} intensity={18} />
        <EngineModel key={cyls.map((c) => `${c.x}:${c.bank_angle}`).join("|")} g={geometry} cyls={cyls} induction={induction} status={status} onHover={setHovered} hovered={hovered} speed={running ? 0.6 : 0} />
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -(geometry.stroke / 2) * S - 0.32, 0]}>
          <circleGeometry args={[size * 1.1, 64]} />
          <meshStandardMaterial color="#060607" metalness={0.15} roughness={0.85} envMapIntensity={0.2} />
        </mesh>
        <Controls targetY={centreY} radius={0.5 * Math.hypot(span, width, top - bottom)} />
      </Canvas>
      <div className="pointer-events-none absolute left-4 top-4">
        {hovered ? (
          <div className="flex items-center gap-3 border border-white/15 bg-black/60 px-3 py-2 backdrop-blur">
            <span className="display text-[13px] text-white">{PART_NAME[hovered]}</span>
            <StatusBadge status={status[hovered] ?? "unchecked"} />
          </div>
        ) : (
          <span className="eyebrow text-white/50">Drag to orbit · scroll to zoom · hover a part</span>
        )}
      </div>
      <div className="absolute bottom-4 left-4 right-28 flex flex-wrap items-center gap-4 text-[11px] text-white/70">
        <span className="eyebrow text-white/50">Glow = limit at risk</span>
        {(["warning", "critical", "failure"] as Status[]).map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2 rounded-full" style={{ background: statusColor(s), boxShadow: `0 0 8px ${statusColor(s)}` }} aria-hidden />
            {STATUS_LABEL[s]}
          </span>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setRunning((v) => !v)}
        className="absolute bottom-4 right-4 border border-white/20 px-3 py-1.5 font-display text-[11px] font-medium uppercase tracking-[0.16em] text-white/70 hover:border-white/50 hover:text-white"
      >
        {running ? "Pause" : "Animate"}
      </button>
    </div>
  );
}
