"use client";

import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { api } from "@/lib/api";
import type { BodyGeometry } from "./BodyDesigner";

interface Wheel {
  x: number;
  r: number;
  y: number;
  width: number;
}

interface LoftData {
  vertices: number[];
  quads: number[];
  triangles: number[];
  glass: number[];
  wheels: Wheel[];
  stats: { vertices: number; quads: number; triangles: number; stations: number; ring: number };
  bounds: { length: number; width: number; height: number };
}

export interface ImportedMesh {
  id: string;
  name: string;
  length: number;
  width: number;
  height: number;
  triangles: number;
  created_at: string;
}

export type Surface =
  | { kind: "loft"; data: LoftData; length: number }
  | { kind: "mesh"; positions: Float32Array; info: ImportedMesh; length: number };

const meshCache = new Map<string, { positions: Float32Array; info: ImportedMesh }>();

function decode(b64: string): Float32Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Float32Array(bytes.buffer);
}

/** The body's 3D surface: the server-side loft of the sketch (debounced), or the imported mesh it points to. */
export function useBodySurface(g: BodyGeometry | null) {
  const [surface, setSurface] = useState<Surface | null>(null);
  const [error, setError] = useState<string | null>(null);
  const meshId = g?.mesh_id ?? null;

  useEffect(() => {
    if (!g) return;
    let live = true;
    const t = setTimeout(
      async () => {
        try {
          if (meshId) {
            let m = meshCache.get(meshId);
            if (!m) {
              const r = await api<ImportedMesh & { triangles_b64: string }>(`/api/v1/body/meshes/${meshId}`);
              const { triangles_b64, ...info } = r;
              m = { positions: decode(triangles_b64), info };
              meshCache.set(meshId, m);
            }
            if (live) setSurface({ kind: "mesh", positions: m.positions, info: m.info, length: m.info.length });
          } else {
            const data = await api<LoftData>("/api/v1/body/mesh", { method: "POST", json: { geometry: g } });
            if (live) setSurface({ kind: "loft", data, length: data.bounds.length });
          }
          if (live) setError(null);
        } catch (e) {
          if (live) setError(e instanceof Error ? e.message : String(e));
        }
      },
      meshId ? 0 : 200,
    );
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [g, meshId]);

  return { surface, error };
}

/** Car frame (x from the nose, y right, z up; metres) to scene (x along the car centred, y up, z lateral). */
function toScene(x: number, y: number, z: number, L: number): [number, number, number] {
  return [x - L / 2, z, y];
}

function useGeometries(surface: Surface) {
  return useMemo(() => {
    const L = surface.length;
    if (surface.kind === "mesh") {
      const src = surface.positions;
      const pos = new Float32Array(src.length);
      for (let i = 0; i < src.length; i += 3) pos.set(toScene(src[i], src[i + 1], src[i + 2], L), i);
      const raw = new THREE.BufferGeometry();
      raw.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      // STL has no shared vertices: smooth the normals across panels, but keep edges sharper than 30° crisp.
      const body = toCreasedNormals(raw, Math.PI / 6);
      const wire = new THREE.EdgesGeometry(raw, 28);
      raw.dispose();
      return { body, glass: null as THREE.BufferGeometry | null, wire };
    }
    const d = surface.data;
    const n = d.vertices.length / 3;
    const pos = new Float32Array(d.vertices.length);
    for (let i = 0; i < n; i++) pos.set(toScene(d.vertices[3 * i], d.vertices[3 * i + 1], d.vertices[3 * i + 2], L), 3 * i);
    const paintIdx: number[] = [];
    const glassIdx: number[] = [];
    const edges: number[] = [];
    const R = d.stats.ring;
    for (let q = 0; q < d.quads.length / 4; q++) {
      const [a, b, c, e] = d.quads.slice(4 * q, 4 * q + 4);
      (d.glass[q] ? glassIdx : paintIdx).push(a, b, c, a, c, e);
      // A CAD-style quad layout: every third section line and every second longitudinal line.
      const station = Math.floor(q / R);
      const around = q % R;
      if (station % 3 === 0) edges.push(a, b);
      if ((around + 1) % 2 === 0) edges.push(b, c);
    }
    paintIdx.push(...d.triangles);
    const make = (idx: number[]) => {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      geo.setIndex(idx);
      geo.computeVertexNormals();
      return geo;
    };
    const body = make(paintIdx);
    const glass = glassIdx.length ? make(glassIdx) : null;
    const wire = new THREE.BufferGeometry();
    wire.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    wire.setIndex(edges);
    return { body, glass, wire };
  }, [surface]);
}

export function BodySurface({
  surface,
  ghost = false,
  wireframe = false,
  groupRef,
}: {
  surface: Surface;
  ghost?: boolean;
  wireframe?: boolean;
  groupRef?: React.RefObject<THREE.Group | null>;
}) {
  const { body, glass, wire } = useGeometries(surface);
  useEffect(
    () => () => {
      body.dispose();
      glass?.dispose();
      wire.dispose();
    },
    [body, glass, wire],
  );
  const L = surface.length;
  const wheels = surface.kind === "loft" ? surface.data.wheels : [];
  return (
    <group ref={groupRef}>
      <mesh geometry={body}>
        <meshPhysicalMaterial
          color={wireframe ? "#4a4d53" : "#2a2d33"}
          metalness={wireframe ? 0.2 : 0.7}
          roughness={wireframe ? 0.6 : 0.28}
          clearcoat={wireframe ? 0 : 1}
          clearcoatRoughness={0.08}
          side={surface.kind === "mesh" ? THREE.DoubleSide : THREE.FrontSide}
          transparent={ghost}
          opacity={ghost ? 0.3 : 1}
          depthWrite={!ghost}
        />
      </mesh>
      {glass && (
        <mesh geometry={glass}>
          <meshPhysicalMaterial color="#07090c" metalness={0.9} roughness={0.04} transparent opacity={ghost ? 0.25 : 0.92} depthWrite={!ghost} />
        </mesh>
      )}
      {wireframe && (
        <lineSegments geometry={wire}>
          <lineBasicMaterial color="#ffffff" transparent opacity={0.42} toneMapped={false} />
        </lineSegments>
      )}
      {wheels.flatMap((w) =>
        [-1, 1].map((side) => (
          <group key={`${w.x}-${side}`} position={toScene(w.x, side * w.y, w.r, L)} rotation={[Math.PI / 2, 0, 0]}>
            <mesh>
              <cylinderGeometry args={[w.r, w.r, w.width, 48]} />
              <meshStandardMaterial color="#111214" roughness={0.9} transparent={ghost} opacity={ghost ? 0.4 : 1} />
            </mesh>
            <mesh position={[0, (side * w.width) / 2 + side * 0.002, 0]}>
              <cylinderGeometry args={[w.r * 0.66, w.r * 0.66, 0.01, 48]} />
              <meshStandardMaterial color="#b9bdc3" metalness={1} roughness={0.25} />
            </mesh>
          </group>
        )),
      )}
    </group>
  );
}
