"""Large batched studies: design-space sweeps, weather studies and material comparisons.

These are the platform's GPU workloads. A sweep evaluates every grid point ×
every Monte Carlo sample in one batched array computation (chunked to fit GPU
memory), so a 30 × 30 grid with 200 samples each (180 000 engine curves) is one
job rather than 900 separate simulations.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Mapping

import numpy as np

from autoeng import compute
from autoeng.analysis.sampling import SWEEPABLE
from autoeng.analysis.simulate import run_raw, simulate
from autoeng.domain.components import CHANNELS
from autoeng.domain.engine_design import PARAM_SPECS, EngineDesign
from autoeng.domain.materials import Material
from autoeng.platform.scenarios import Scenario, Weather
from autoeng.platform.simulate_scenario import run_scenario
from autoeng.platform.vehicle import VehicleDesign

MAX_GRID_POINTS = 2500
CHUNK_ROWS = 60_000  # engine curves per batch (rows × rpm points must fit GPU memory)


def _label(path: str) -> str:
    spec = PARAM_SPECS.get(path)
    return f"{spec.label} ({spec.unit})" if spec else path


def engine_sweep(
    design: EngineDesign,
    materials: Mapping[str, Material],
    x_path: str,
    x_values: list[float],
    y_path: str | None = None,
    y_values: list[float] | None = None,
    samples: int = 100,
    seed: int = 42,
) -> dict:
    """Evaluate a 1-D or 2-D grid of design variants with Monte Carlo at every point."""
    for p in [x_path] + ([y_path] if y_path else []):
        if p not in SWEEPABLE:
            raise ValueError(f"'{p}' cannot be swept")
    ys = y_values if y_path else [None]
    grid = [(xv, yv) for yv in ys for xv in x_values]  # row-major: y outer, x inner
    if len(grid) > MAX_GRID_POINTS:
        raise ValueError(f"Grid has {len(grid)} points (max {MAX_GRID_POINTS})")
    points = [{x_path: xv} | ({y_path: yv} if y_path else {}) for xv, yv in grid]

    per_chunk = max(1, CHUNK_ROWS // max(samples, 1))
    metrics = {k: [] for k in ("peak_power", "peak_torque", "max_peak_pressure", "max_egt", "max_boost")}
    p_fail, worst_limit, p_target = [], [], []
    started = time.perf_counter()
    device = None
    for c0 in range(0, len(points), per_chunk):
        chunk = points[c0:c0 + per_chunk]
        raw = run_raw(design, materials, samples, seed, points=chunk)
        device = raw.device
        ch = {k: v.reshape(len(chunk), samples, -1) for k, v in raw.channels.items()}
        for key, channel in (("peak_power", "power"), ("peak_torque", "torque"), ("max_peak_pressure", "peak_pressure"),
                             ("max_egt", "egt"), ("max_boost", "boost")):
            per_sample = np.nanmax(ch[channel], axis=2)  # (P, S)
            metrics[key].append(np.percentile(per_sample, [5, 50, 95], axis=1).T)  # (P, 3)
        exceed = np.zeros((len(chunk), samples), dtype=bool)
        counts = np.zeros((len(chunk), len(design.limits)))
        for j, limit in enumerate(design.limits):
            if limit.channel not in ch:
                continue
            ref = design.ambient.temperature.value if CHANNELS[limit.channel].unit == "°C" else 0.0
            worst = np.nanmax(ch[limit.channel], axis=2)
            over = (worst - ref) > (limit.allowable.value - ref)
            exceed |= over
            counts[:, j] = over.mean(axis=1)
        rod = {k: np.broadcast_to(v, raw.channels["torque"].shape).reshape(len(chunk), samples, -1)
               for k, v in raw.rod.items() if k.startswith("sf_")}
        for sf in rod.values():
            exceed |= np.nanmin(sf, axis=2) < 1.0
        p_fail.append(exceed.mean(axis=1))
        worst_limit.extend(
            design.limits[int(np.argmax(row))].id if len(design.limits) and row.max() > 0 else None for row in counts)
        if design.targets.peak_power is not None:
            p_target.append((np.nanmax(ch["power"], axis=2) >= design.targets.peak_power.value).mean(axis=1))

    def stack(key):
        return np.concatenate(metrics[key], axis=0)

    shape = (len(ys), len(x_values))
    out = {
        "x": {"path": x_path, "label": _label(x_path), "values": list(map(float, x_values))},
        "y": {"path": y_path, "label": _label(y_path), "values": list(map(float, y_values))} if y_path else None,
        "samples": samples,
        "grid_points": len(points),
        "evaluations": len(points) * samples,
        "metrics": {k: {q: stack(k)[:, i].reshape(shape).round(3).tolist() for i, q in enumerate(("p05", "p50", "p95"))}
                    for k in metrics},
        "probability_any_failure": np.concatenate(p_fail).reshape(shape).round(4).tolist(),
        "most_likely_limit": np.array(worst_limit, dtype=object).reshape(shape).tolist(),
        "probability_target": (np.concatenate(p_target).reshape(shape).round(4).tolist() if p_target else None),
        "seconds": round(time.perf_counter() - started, 2),
        "compute": device or compute.describe(np),
        "notes": [
            "'probability_any_failure' is the share of samples in which any design limit or rod check is exceeded "
            "(nominal allowables).",
            "Each grid point reuses the same random draws, so neighbouring points differ by the swept change only.",
        ],
    }
    return out


def weather_study(
    vehicle: VehicleDesign,
    scenario: Scenario,
    materials: Mapping[str, Material],
    temperatures_c: list[float],
    altitudes_m: list[float] | None = None,
    samples: int = 100,
    seed: int = 42,
    surface: str | None = None,
) -> dict:
    """Run one scenario across a grid of ambient temperatures × altitudes in a single batched ensemble."""
    altitudes_m = altitudes_m or [scenario.weather.altitude_m]
    base = scenario.weather.model_dump()
    weathers = [Weather(**(base | {"ambient_temp_c": t, "altitude_m": a} | ({"surface": surface} if surface else {})))
                for a, t in itertools.product(altitudes_m, temperatures_c)]
    if len(weathers) > 60:
        raise ValueError("At most 60 weather points per study")
    started = time.perf_counter()
    res = run_scenario(vehicle, scenario, materials, samples, seed, weather_points=weathers)
    res["study"] = {"temperatures_c": temperatures_c, "altitudes_m": altitudes_m,
                    "seconds": round(time.perf_counter() - started, 2)}
    return res


def material_study(
    target: str,
    materials: Mapping[str, Material],
    material_ids: list[str],
    engine: EngineDesign | None = None,
    vehicle: VehicleDesign | None = None,
    scenario: Scenario | None = None,
    samples: int = 100,
    seed: int = 42,
) -> dict:
    """Compare materials for one component: connecting rods (engine) or brake discs (vehicle scenario)."""
    rows = []
    for mid in material_ids:
        mat = materials.get(mid)
        if mat is None:
            raise ValueError(f"Unknown material '{mid}'")
        row = {"material_id": mid, "name": f"{mat.name} {mat.condition}".strip(), "custom": mat.custom,
               "sources": sorted({p.source.value for p in mat.properties.values()})}
        try:
            if target == "conrod":
                if engine is None:
                    raise ValueError("An engine design is required")
                d = engine.model_dump()
                d["conrod"]["material_id"] = mid
                res = simulate(EngineDesign.model_validate(d), materials, samples, seed)
                row["rod_mass_g"] = res["summary"]["rod_mass_g"]
                row["checks"] = [r for r in res["limits"] if r["component"] == "connecting_rods"]
            elif target == "brake_disc":
                if vehicle is None or scenario is None:
                    raise ValueError("A vehicle and a scenario are required")
                d = vehicle.model_dump()
                brakes = next(cid for cid, c in d["components"].items() if c["type"] == "brakes_front")
                params = d["components"][brakes]["params"]
                base = materials.get(params["disc_material_id"])
                scale = mat.prop("density").value / base.prop("density").value
                params["disc_material_id"] = mid
                params["disc_mass"]["value"] *= scale  # same geometry, different density
                res = run_scenario(VehicleDesign.model_validate(d), scenario, materials, samples, seed)
                p = res["points"][0]
                row["disc_mass_kg"] = params["disc_mass"]["value"]
                row["max_disc_c"] = p["max_disc_c"]
                solidus = mat.prop("solidus_temp")
                if solidus is not None and p["max_disc_c"]["p95"] is not None:
                    homologous = (p["max_disc_c"]["p95"] + 273.15) / (solidus.value + 273.15)
                    row["homologous_temp_p95"] = homologous
                    if homologous >= 1.0:
                        row["warning"] = "The disc would reach its melting range: this material cannot work here."
                    elif homologous >= 0.4:
                        row["warning"] = ("Above ~0.4 of the absolute melting temperature: expect significant "
                                          "softening and creep (rule of thumb for metals).")
                row["disc_limit"] = p["disc_limit"]
                row["checks"] = [c for c in p["checks"] if c["id"] == "brake_disc"]
            else:
                raise ValueError("target must be 'conrod' or 'brake_disc'")
        except ValueError as exc:
            row["error"] = str(exc)
        rows.append(row)
    notes = ["Materials are compared on the same geometry; a real redesign would resize the part for each material."]
    if target == "brake_disc":
        notes.append("Disc mass is scaled by density from the current disc (same volume), so both heat capacity "
                     "and mass change with the material. Strength at temperature and wear are not assessed.")
    return {"target": target, "rows": rows, "notes": notes}

