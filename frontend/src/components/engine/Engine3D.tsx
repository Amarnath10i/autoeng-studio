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

type Part = "combustion_chamber" | "connecting_rods" | "crankshaft" | "compressor" | "turbine" | "intercooler" | "cooling_system" | "intake_manifold" | "exhaust_system";

const PART_NAME: Record<Part, string> = {
  combustion_chamber: "Cylinders & pistons",
  connecting_rods: "Connecting rods",
  crankshaft: "Crankshaft",
  compressor: "Turbo compressor",
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

function Controls({ targetY }: { targetY: number }) {
  const { camera, gl } = useThree();
  useEffect(() => {
    const c = new OrbitControls(camera, gl.domElement);
    c.enableDamping = true;
    c.target.set(0, targetY, 0);
    camera.lookAt(0, targetY, 0);
    c.update();
    return () => c.dispose();
  }, [camera, gl, targetY]);
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

function EngineModel({ g, status, onHover, hovered, speed }: {
  g: Geometry;
  status: Record<string, Status>;
  onHover: (p: Part | null) => void;
  hovered: Part | null;
  speed: number;
}) {
  const r = (g.stroke / 2) * S;
  const L = g.rod * S;
  const bore = g.bore * S;
  const pitch = bore * 1.25;
  const n = g.cylinders;
  const width = pitch * n;
  const deckY = r + L + bore * 0.9;
  const pistons = useRef<THREE.Mesh[]>([]);
  const rods = useRef<THREE.Mesh[]>([]);
  const pins = useRef<THREE.Mesh[]>([]);
  const crank = useRef<THREE.Group>(null);
  const comp = useRef<THREE.Mesh>(null);
  const angle = useRef(0);

  // Firing order phase offsets for an even-fire inline engine.
  const phases = useMemo(() => Array.from({ length: n }, (_, i) => ((i % 2 === 0 ? 0 : Math.PI) + Math.floor(i / 2) * (4 * Math.PI) / n) % (2 * Math.PI)), [n]);

  useFrame((_, dt) => {
    angle.current += dt * speed * 2 * Math.PI;
    if (crank.current) crank.current.rotation.x = angle.current;
    if (comp.current) comp.current.rotation.z += dt * speed * 20;
    for (let i = 0; i < n; i++) {
      const th = angle.current + phases[i];
      const pinY = r * Math.cos(th);
      const pinZ = r * Math.sin(th);
      const pistonY = pinY + Math.sqrt(Math.max(L * L - pinZ * pinZ, 0));
      const p = pistons.current[i];
      if (p) p.position.y = pistonY + bore * 0.25;
      const pin = pins.current[i];
      if (pin) pin.position.set(pin.position.x, pinY, pinZ);
      const rod = rods.current[i];
      if (rod) {
        rod.position.set(rod.position.x, (pinY + pistonY) / 2, pinZ / 2);
        rod.rotation.x = -Math.atan2(pinZ, pistonY - pinY);
      }
    }
  });

  const hoverProps = (part: Part) => ({
    onPointerOver: (e: { stopPropagation: () => void }) => {
      e.stopPropagation();
      onHover(part);
    },
    onPointerOut: () => onHover(null),
  });

  return (
    <group>
      {/* Crankshaft */}
      <group ref={crank} {...hoverProps("crankshaft")}>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[bore * 0.12, bore * 0.12, width + pitch * 0.6, 20]} />
          <Mat part="crankshaft" status={status} hovered={hovered} />
        </mesh>
      </group>
      {Array.from({ length: n }).map((_, i) => {
        const x = -width / 2 + pitch * (i + 0.5);
        return (
          <group key={i}>
            <mesh ref={(m) => { if (m) pins.current[i] = m; }} position={[x, 0, 0]} rotation={[0, 0, Math.PI / 2]} {...hoverProps("crankshaft")}>
              <cylinderGeometry args={[bore * 0.1, bore * 0.1, bore * 0.35, 16]} />
              <Mat part="crankshaft" status={status} hovered={hovered} />
            </mesh>
            <mesh ref={(m) => { if (m) rods.current[i] = m; }} position={[x, r + L / 2, 0]} {...hoverProps("connecting_rods")}>
              <boxGeometry args={[bore * 0.12, L, bore * 0.18]} />
              <Mat part="connecting_rods" status={status} hovered={hovered} />
            </mesh>
            <mesh ref={(m) => { if (m) pistons.current[i] = m; }} position={[x, r + L, 0]} {...hoverProps("combustion_chamber")}>
              <cylinderGeometry args={[bore * 0.48, bore * 0.48, bore * 0.5, 32]} />
              <Mat part="combustion_chamber" status={status} hovered={hovered} />
            </mesh>
            {/* Cylinder bore (transparent liner) */}
            <mesh position={[x, r + L + bore * 0.25, 0]}>
              <cylinderGeometry args={[bore * 0.52, bore * 0.52, 2 * r + bore * 0.6, 32, 1, true]} />
              <meshStandardMaterial color="#b8bcc2" metalness={0.2} roughness={0.1} transparent opacity={0.08} side={THREE.DoubleSide} />
            </mesh>
          </group>
        );
      })}
      {/* Head / intake plenum */}
      <mesh position={[0, deckY + bore * 0.35, -bore * 0.6]} {...hoverProps("intake_manifold")}>
        <boxGeometry args={[width, bore * 0.35, bore * 0.4]} />
        <Mat part="intake_manifold" status={status} hovered={hovered} opacity={0.85} />
      </mesh>
      {/* Exhaust manifold */}
      <mesh position={[0, deckY + bore * 0.1, bore * 0.75]} {...hoverProps("exhaust_system")}>
        <boxGeometry args={[width * 0.9, bore * 0.25, bore * 0.25]} />
        <Mat part="exhaust_system" status={status} hovered={hovered} opacity={0.85} />
      </mesh>
      {/* Turbocharger: turbine and compressor housings on a shared shaft */}
      <group position={[width / 2 + bore * 0.9, deckY, bore * 0.6]}>
        <mesh position={[0, 0, 0.0]} rotation={[0, Math.PI / 2, 0]} {...hoverProps("turbine")}>
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
      {/* Intercooler (front-mounted) */}
      <mesh position={[0, r, -width * 0.45 - bore * 1.5]} {...hoverProps("intercooler")}>
        <boxGeometry args={[width * 0.9, bore * 1.1, bore * 0.18]} />
        <Mat part="intercooler" status={status} hovered={hovered} />
      </mesh>
      {/* Radiator */}
      <mesh position={[0, r + bore * 1.2, -width * 0.45 - bore * 1.8]} {...hoverProps("cooling_system")}>
        <boxGeometry args={[width, bore * 1.2, bore * 0.14]} />
        <Mat part="cooling_system" status={status} hovered={hovered} />
      </mesh>
    </group>
  );
}

export function Engine3D({
  geometry,
  status,
  height = 380,
}: {
  geometry: Geometry;
  status: Record<string, Status>;
  height?: number;
}) {
  const [hovered, setHovered] = useState<Part | null>(null);
  const [running, setRunning] = useState(true);
  const size = Math.max(geometry.bore * 1.25 * geometry.cylinders, geometry.stroke + geometry.rod) * S;
  // Vertical centre of the model: from below the crank to the top of the head.
  const bottom = -(geometry.stroke / 2) * S;
  const top = (geometry.stroke / 2 + geometry.rod + geometry.bore * 1.4) * S;
  const centreY = (bottom + top) / 2;
  return (
    <div
      className="relative overflow-hidden border border-line"
      style={{ height, background: "radial-gradient(120% 90% at 50% 20%, #23262b 0%, #0b0c0e 55%, #050506 100%)" }}
    >
      <Canvas camera={{ position: [size * 1.55, centreY + size * 0.95, size * 2.1], fov: 34 }} dpr={[1, 2]} gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}>
        <Studio />
        <ambientLight intensity={0.15} />
        <directionalLight position={[6, 9, 4]} intensity={1.6} />
        <directionalLight position={[-7, 4, -5]} intensity={0.6} color="#9fb4ff" />
        <spotLight position={[0, 8, 0]} angle={0.5} penumbra={1} intensity={18} />
        <EngineModel g={geometry} status={status} onHover={setHovered} hovered={hovered} speed={running ? 0.6 : 0} />
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -(geometry.stroke / 2) * S - 0.32, 0]}>
          <circleGeometry args={[size * 1.6, 64]} />
          <meshStandardMaterial color="#060607" metalness={0.15} roughness={0.85} envMapIntensity={0.2} />
        </mesh>
        <Controls targetY={centreY} />
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
