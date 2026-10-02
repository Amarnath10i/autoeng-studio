import type { Json } from "./types";

/** Cylinder counts each layout supports (mirrors the backend's layout validation). */
export const VALID_CYLINDERS: Record<string, number[]> = {
  inline: [1, 2, 3, 4, 5, 6, 8],
  v: [2, 4, 6, 8, 10, 12, 16],
  flat: [2, 4, 6, 8, 10, 12, 16],
  w: [8, 12, 16],
};

/** Typical bank angle when switching to a layout (V: 60° for 6 and 12, 72° for 10, else 90°). */
function defaultBankAngle(layout: string, cylinders: number): number {
  if (layout === "flat") return 180;
  if (layout === "w") return cylinders === 16 ? 90 : 72;
  if (layout === "v") return cylinders === 6 || cylinders === 12 ? 60 : cylinders === 10 ? 72 : 90;
  return 90;
}

const nearest = (options: number[], n: number) => options.reduce((best, o) => (Math.abs(o - n) < Math.abs(best - n) ? o : best));

/**
 * Keep a design buildable when its layout changes: switching an inline-four to "W" would otherwise ask for a
 * W4, which does not exist. Snaps the cylinder count to the nearest valid one, picks a typical bank angle,
 * resets a V8-only crank, and keeps one injector per cylinder.
 */
export function normalizeLayout(prev: Json, next: Json): Json {
  const pa = (prev.architecture ?? {}) as Json;
  const na = (next.architecture ?? {}) as Json;
  const layout = String(na.layout ?? "inline");
  if (layout === pa.layout) return next;
  const engine = next.engine as Json;
  const prevCyl = Number((prev.engine as Json).cylinders);
  const cylinders = nearest(VALID_CYLINDERS[layout] ?? [Number(engine.cylinders)], Number(engine.cylinders));
  const bank = na.bank_angle as Json | undefined;
  const fuel = next.fuel as Json;
  return {
    ...next,
    engine: { ...engine, cylinders },
    architecture: {
      ...na,
      crank: layout === "v" && cylinders === 8 ? na.crank : "standard",
      bank_angle: bank ? { ...bank, value: defaultBankAngle(layout, cylinders) } : bank,
    },
    fuel: fuel && Number(fuel.injector_count) === prevCyl ? { ...fuel, injector_count: cylinders } : fuel,
  };
}
