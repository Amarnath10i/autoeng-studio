"""Turn a design into sampled SI arrays for the physics models.

Each parameter gets its own random stream derived from (seed, parameter path).
Two designs that share a parameter's value and tolerance therefore draw identical
samples for it (common random numbers), so a what-if comparison shows the effect
of the change rather than sampling noise.
"""

from __future__ import annotations

import zlib
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from autoeng.core.params import Param
from autoeng.domain.engine_design import PARAM_SPECS, EngineDesign, get_path
from autoeng.domain.fuels import FUELS
from autoeng.domain.materials import Material
from autoeng.physics.engine_mvem import EngineInputs

# (scale, offset) from each parameter's display unit to SI: si = value * scale + offset
SI: dict[str, tuple[float, float]] = {
    "engine.bore": (1e-3, 0), "engine.stroke": (1e-3, 0), "engine.rod_length": (1e-3, 0),
    "turbo.boost_target": (1e5, 0), "turbo.turbine_flow_area": (1e-4, 0),
    "intercooler.pressure_drop": (1e5, 0), "exhaust.backpressure": (1e5, 0),
    "friction.a": (1e5, 0), "friction.b": (1e5, 0), "friction.c": (1e5, 0),
    "fuel.injector_flow": (1e-6 / 60.0, 0),
    "ambient.temperature": (1.0, 273.15), "ambient.pressure": (1e3, 0),
    "conrod.section_height": (1e-3, 0), "conrod.section_width": (1e-3, 0),
    "conrod.flange_thickness": (1e-3, 0), "conrod.web_thickness": (1e-3, 0),
    "conrod.volume": (1e-6, 0), "conrod.piston_group_mass": (1e-3, 0),
    "fuel.lhv": (1e6, 0), "fuel.density": (1e3, 0),
    "material.youngs_modulus": (1e9, 0), "material.yield_strength": (1e6, 0),
    "material.ultimate_strength": (1e6, 0), "material.fatigue_strength": (1e6, 0),
}

MATERIAL_KEYS = ("density", "youngs_modulus", "yield_strength", "ultimate_strength", "fatigue_strength")


@dataclass
class Sampled:
    engine: EngineInputs
    rod: dict[str, np.ndarray | None]
    inputs: dict[str, Param]  # every Param that fed the models, by path
    n: int
    draws: dict[str, np.ndarray]  # sampled values in display units, for inputs with tol > 0


def _stream(seed: int, path: str) -> np.random.Generator:
    return np.random.default_rng([seed, zlib.crc32(path.encode())])


def _draw(path: str, param: Param, n: int, seed: int, draws: dict, lo: float = -np.inf, hi: float = np.inf) -> np.ndarray:
    values = np.clip(param.sample(n, _stream(seed, path)), lo, hi)
    if param.tol > 0 and n > 1:
        draws[path] = values
    scale, offset = SI.get(path, (1.0, 0.0))
    return (values * scale + offset)[:, None]


def resolve_material(design: EngineDesign, materials: Mapping[str, Material]) -> Material:
    material = materials.get(design.conrod.material_id)
    if material is None:
        raise ValueError(f"conrod.material_id: unknown material '{design.conrod.material_id}'")
    missing = [k for k in ("density", "youngs_modulus", "yield_strength", "ultimate_strength") if k not in material.properties]
    if missing:
        raise ValueError(f"Material '{material.name}' lacks {', '.join(missing)}, which the rod checks need")
    return material


# Design parameter path -> EngineInputs field (SI after conversion).
ENGINE_FIELDS: dict[str, str] = {
    "engine.bore": "bore", "engine.stroke": "stroke", "engine.compression_ratio": "compression_ratio",
    "breathing.ve_peak": "ve_peak", "breathing.ve_peak_rpm": "ve_peak_rpm", "breathing.ve_falloff": "ve_falloff",
    "turbo.boost_target": "boost_target", "turbo.compressor_efficiency": "eta_compressor",
    "turbo.turbine_efficiency": "eta_turbine", "turbo.mechanical_efficiency": "eta_mechanical",
    "turbo.turbine_flow_area": "turbine_area",
    "intercooler.effectiveness": "ic_effectiveness", "intercooler.pressure_drop": "ic_pressure_drop",
    "combustion.lambda_ratio": "lambda_ratio", "combustion.efficiency_ratio": "efficiency_ratio",
    "combustion.cycle_gamma": "cycle_gamma", "combustion.combustion_efficiency": "combustion_efficiency",
    "combustion.pressure_rise_ratio": "pressure_rise_ratio", "combustion.polytropic_n": "polytropic_n",
    "combustion.coolant_heat_fraction": "coolant_heat_fraction",
    "exhaust.backpressure": "exhaust_backpressure", "exhaust.gas_cp": "exhaust_cp", "exhaust.gas_gamma": "exhaust_gamma",
    "friction.a": "friction_a", "friction.b": "friction_b", "friction.c": "friction_c",
    "fuel.lhv": "fuel_lhv", "fuel.afr_stoich": "afr_stoich", "fuel.density": "fuel_density",
    "fuel.injector_flow": "injector_flow",
    "ambient.temperature": "ambient_temp", "ambient.pressure": "ambient_pressure",
}
ROD_FIELDS: dict[str, str] = {
    "engine.rod_length": "rod_length", "conrod.section_height": "height", "conrod.section_width": "width",
    "conrod.flange_thickness": "flange_t", "conrod.web_thickness": "web_t", "conrod.volume": "volume",
    "conrod.piston_group_mass": "piston_group_mass", "conrod.small_end_fraction": "small_end_fraction",
    "conrod.fatigue_factor": "fatigue_factor", "conrod.overspeed_factor": "overspeed_factor",
}
SWEEPABLE = sorted(set(ENGINE_FIELDS) | set(ROD_FIELDS)) + [f"material.{k}" for k in MATERIAL_KEYS]


def to_si(path: str, values) -> np.ndarray:
    scale, offset = SI.get(path, (1.0, 0.0))
    return np.asarray(values, dtype=float) * scale + offset


def sample_design(
    design: EngineDesign,
    materials: Mapping[str, Material],
    n: int,
    seed: int,
    overrides: Mapping[str, float] | None = None,
    points: list[Mapping[str, float]] | None = None,
) -> Sampled:
    """Sample a design's inputs.

    `n == 1` gives the nominal case. `overrides` replaces nominal values (used by
    calibration). `points` batches variants: the n samples are repeated for each
    point (point-major order, P·n rows) and each point's values (display units)
    replace that parameter for its block. The same random draws are reused across
    points, so differences between points are not sampling noise.
    """
    overrides = overrides or {}
    inputs: dict[str, Param] = {}
    draws: dict[str, np.ndarray] = {}
    x: dict[str, np.ndarray] = {}
    for path, spec in PARAM_SPECS.items():
        if spec.kind != "param" or path.startswith("targets."):
            continue
        param: Param = get_path(design, path)
        if path in overrides:
            param = param.model_copy(update={"value": overrides[path]})
        inputs[path] = param
        x[path] = _draw(path, param, n, seed, draws, spec.min, spec.max)

    fuel = FUELS[design.fuel.fuel_id]
    for key in ("lhv", "afr_stoich", "density"):
        param = getattr(fuel, key)
        inputs[f"fuel.{key}"] = param
        x[f"fuel.{key}"] = _draw(f"fuel.{key}", param, n, seed, draws, 0.0)

    material = resolve_material(design, materials)
    for key in MATERIAL_KEYS:
        param = material.prop(key)
        if param is None:
            continue
        inputs[f"material.{key}"] = param
        x[f"material.{key}"] = _draw(f"material.{key}", param, n, seed, draws, 1e-9)

    if points:
        n_points = len(points)
        x = {k: np.tile(v, (n_points, 1)) for k, v in x.items()}
        for path in {k for pt in points for k in pt}:
            if path not in x:
                raise ValueError(f"'{path}' cannot be varied in a batch")
            spec = PARAM_SPECS.get(path)
            base = x[path].reshape(n_points, n)
            for i, pt in enumerate(points):
                if path in pt:
                    v = pt[path] if spec is None else float(np.clip(pt[path], spec.min, spec.max))
                    param = inputs[path]
                    # Keep each sample's relative deviation from nominal around the new value.
                    if param.tol > 0 and n > 1:
                        base[i] = base[i] - to_si(path, param.value) + to_si(path, v)
                    else:
                        base[i] = to_si(path, v)
            x[path] = base.reshape(-1, 1)
        n = n * n_points

    engine = EngineInputs(
        cylinders=design.engine.cylinders,
        rpm_min=float(design.operating.rpm_min),
        rpm_max=float(design.operating.rpm_max),
        injector_count=design.fuel.injector_count,
        **{field: x[path] for path, field in ENGINE_FIELDS.items()},
    )
    rod: dict[str, np.ndarray | None] = {field: x[path] for path, field in ROD_FIELDS.items()}
    for key in MATERIAL_KEYS:
        rod[key] = x.get(f"material.{key}")
    return Sampled(engine=engine, rod=rod, inputs=inputs, n=n, draws=draws)
