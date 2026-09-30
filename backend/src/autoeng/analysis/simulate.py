"""Run a design through the physics models and package the result with its provenance."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from autoeng import compute
from autoeng.analysis import limits as lim
from autoeng.analysis.sampling import Sampled, _stream, resolve_material, sample_design
from autoeng.core.params import Source
from autoeng.domain.components import CHANNELS, COMPONENTS
from autoeng.domain.engine_design import PARAM_SPECS, EngineDesign
from autoeng.domain.materials import Material
from autoeng.physics import balance, conrod, engine_mvem

MAX_SAMPLES = 2000
DEFAULT_SAMPLES = 200
DEFAULT_SEED = 42

ROD_DISPLAY = {"rod_compressive_stress": 1e-6, "rod_tensile_stress": 1e-6}

DISCLAIMER = (
    "Engineering estimate from simplified physics models. It is not a measurement, a guarantee of real-world "
    "performance, or a safety certification. Validate against measured data before acting on it."
)


@dataclass
class RawRun:
    rpm: np.ndarray  # (R,)
    channels: dict[str, np.ndarray]  # display units, (S, R)
    rod: dict[str, np.ndarray]  # SI, broadcast to (S, R) where rpm-dependent
    sampled: Sampled
    device: dict


def rpm_grid(design: EngineDesign) -> np.ndarray:
    op = design.operating
    return np.arange(op.rpm_min, op.rpm_max + op.rpm_step / 2, op.rpm_step, dtype=float)


def run_raw(
    design: EngineDesign,
    materials: Mapping[str, Material],
    n: int,
    seed: int,
    rpm: np.ndarray | None = None,
    overrides: Mapping[str, float] | None = None,
    points: list[Mapping[str, float]] | None = None,
) -> RawRun:
    """Evaluate the engine and rod models. With `points`, rows are point-major blocks of n samples."""
    rpm = rpm_grid(design) if rpm is None else np.asarray(rpm, dtype=float)
    s = sample_design(design, materials, n, seed, overrides, points)
    xp = compute.for_size(s.n * rpm.size)
    eng = _to_device(s.engine, xp)
    r = {k: (None if v is None else xp.asarray(v)) for k, v in s.rod.items()}
    si = engine_mvem.run(eng, rpm)
    rod = conrod.analyse(
        bore=eng.bore,
        stroke=eng.stroke,
        rod_length=r["rod_length"],
        rpm=xp.asarray(rpm)[None, :],
        rpm_max=eng.rpm_max,
        peak_pressure=si["peak_pressure"],
        ambient_pressure=eng.ambient_pressure,
        section=conrod.i_section(r["height"], r["width"], r["flange_t"], r["web_t"]),
        rod_volume=r["volume"],
        piston_group_mass=r["piston_group_mass"],
        small_end_fraction=r["small_end_fraction"],
        overspeed_factor=r["overspeed_factor"],
        density=r["density"],
        e_modulus=r["youngs_modulus"],
        yield_strength=r["yield_strength"],
        ultimate_strength=r["ultimate_strength"],
        fatigue_strength=r["fatigue_strength"],
        fatigue_factor=r["fatigue_factor"],
    )
    channels = {name: engine_mvem.to_display(name, compute.to_numpy(v).astype(float)) for name, v in si.items()}
    rod = {k: compute.to_numpy(v) for k, v in rod.items()}
    shape = channels["torque"].shape
    for name, scale in ROD_DISPLAY.items():
        channels[name] = np.broadcast_to(rod[name] * scale, shape)
    return RawRun(rpm=rpm, channels=channels, rod=rod, sampled=s, device=compute.describe(xp))


def _to_device(inp: engine_mvem.EngineInputs, xp) -> engine_mvem.EngineInputs:
    if xp is np:
        return inp
    fields = {k: (xp.asarray(v) if isinstance(v, np.ndarray) else v) for k, v in vars(inp).items()}
    return engine_mvem.EngineInputs(**fields)


def _clean(arr: np.ndarray, digits: int = 5) -> list[float | None]:
    return [None if not np.isfinite(v) else round(float(v), digits) for v in np.ravel(arr)]


def _dist(nominal: float, samples: np.ndarray) -> dict:
    samples = samples[np.isfinite(samples)]
    if samples.size == 0:
        return {"nominal": nominal, "p05": None, "p50": None, "p95": None}
    p05, p50, p95 = np.percentile(samples, [5, 50, 95])
    return {"nominal": float(nominal), "p05": float(p05), "p50": float(p50), "p95": float(p95)}


def _ranges(rpm: np.ndarray, mask: np.ndarray) -> list[tuple[float, float]]:
    out, start = [], None
    for i, flag in enumerate(mask):
        if flag and start is None:
            start = i
        if not flag and start is not None:
            out.append((rpm[start], rpm[i - 1]))
            start = None
    if start is not None:
        out.append((rpm[start], rpm[-1]))
    return out


def _fmt_ranges(ranges: list[tuple[float, float]]) -> str:
    return ", ".join(f"{a:.0f}" if a == b else f"{a:.0f}-{b:.0f}" for a, b in ranges) + " rpm"


def simulate(
    design: EngineDesign,
    materials: Mapping[str, Material],
    samples: int = DEFAULT_SAMPLES,
    seed: int = DEFAULT_SEED,
    return_raw: bool = False,
):
    """Simulate an engine design. With `return_raw`, also return the nominal and ensemble runs."""
    samples = int(np.clip(samples, 1, MAX_SAMPLES))
    material = resolve_material(design, materials)
    nom = run_raw(design, materials, 1, seed)
    ens = run_raw(design, materials, samples, seed) if samples > 1 else nom
    rpm = nom.rpm

    channels = {}
    for name in CHANNELS:
        if name == "rpm":
            continue
        n_curve = nom.channels[name][0]
        e = ens.channels[name]
        with np.errstate(all="ignore"):
            p05, p50, p95 = (np.nanpercentile(e, q, axis=0) for q in (5, 50, 95))
        channels[name] = {"nominal": _clean(n_curve), "p05": _clean(p05), "p50": _clean(p50), "p95": _clean(p95)}

    def peak(name: str, fn=np.nanmax) -> dict:
        n_curve = nom.channels[name][0]
        idx = int(np.nanargmax(n_curve) if fn is np.nanmax else np.nanargmin(n_curve))
        with np.errstate(all="ignore"):
            per_sample = fn(ens.channels[name], axis=1)
        return {**_dist(float(n_curve[idx]), per_sample), "rpm": float(rpm[idx])}

    displacement_l = float(nom.sampled.engine.displacement.ravel()[0] * 1e3)
    summary = {
        "peak_power": peak("power"),
        "peak_torque": peak("torque"),
        "max_boost": peak("boost"),
        "max_egt": peak("egt"),
        "max_peak_pressure": peak("peak_pressure"),
        "max_heat_to_coolant": peak("heat_to_coolant"),
        "max_charge_temp": peak("charge_temp"),
        "max_injector_duty": peak("injector_duty"),
        "min_bsfc": peak("bsfc", np.nanmin),
        "displacement_l": displacement_l,
        "rod_mass_g": _dist(float(nom.rod["rod_mass"].ravel()[0] * 1e3), ens.rod["rod_mass"].ravel() * 1e3),
        "recip_mass_g": _dist(float(nom.rod["recip_mass"].ravel()[0] * 1e3), ens.rod["recip_mass"].ravel() * 1e3),
    }
    summary["specific_power_kw_per_l"] = summary["peak_power"]["nominal"] / displacement_l

    targets = []
    for key, channel in (("peak_power", "power"), ("peak_torque", "torque")):
        target = getattr(design.targets, key)
        if target is None:
            continue
        per_sample = np.nanmax(ens.channels[channel], axis=1)
        targets.append({
            "id": key,
            "channel": channel,
            "target": target.value,
            "nominal": summary[key]["nominal"],
            "probability_met": float(np.mean(per_sample >= target.value)),
            "met_nominal": summary[key]["nominal"] >= target.value,
        })

    results = _evaluate_limits(design, nom, ens, seed) + _rod_checks(nom, ens, material)
    component_status = {}
    for cid in COMPONENTS:
        statuses = [r.status for r in results if r.component == cid]
        component_status[cid] = lim.worst(statuses) if statuses else "unchecked"

    result = {
        "design_name": design.name,
        "architecture": design.architecture.model_dump(mode="json"),
        "balance": balance_for(design, material),
        "rpm": _clean(rpm, 1),
        "channels": channels,
        "summary": summary,
        "targets": targets,
        "limits": [r.as_dict() for r in results],
        "component_status": component_status,
        "status_rules": lim.STATUS_RULES,
        "material": {"id": material.id, "name": material.name, "condition": material.condition, "custom": material.custom},
        "warnings": _warnings(nom, rpm),
        "sensitivity": sensitivity(ens),
        "trust": trust_block(nom.sampled, samples, seed),
        "compute": ens.device,
    }
    return (result, nom, ens) if return_raw else result


def balance_for(design: EngineDesign, material: Material) -> dict:
    """Layout balance and firing analysis at redline, using the nominal reciprocating mass."""
    rod = design.conrod
    density = material.prop("density").value
    recip = rod.piston_group_mass.value / 1000 + rod.small_end_fraction.value * density * rod.volume.value * 1e-6
    arch = design.architecture
    return balance.analyse(
        arch.layout, design.engine.cylinders, arch.bank_angle.value, arch.crank,
        design.engine.bore.value / 1000, design.engine.stroke.value / 1000, design.engine.rod_length.value / 1000,
        recip, float(design.operating.rpm_max),
    )


def _evaluate_limits(design: EngineDesign, nom: RawRun, ens: RawRun, seed: int) -> list[lim.LimitResult]:
    out = []
    for limit in design.limits:
        channel = CHANNELS.get(limit.channel)
        if channel is None or limit.channel not in nom.channels:
            out.append(lim.no_data(limit.id, limit.component, limit.label or limit.channel, "",
                                   f"Unknown channel '{limit.channel}'"))
            continue
        allowable_samples = limit.allowable.sample(ens.sampled.n, _stream(seed, f"limit.{limit.id}"))
        thermal = channel.unit == "°C"
        reference = design.ambient.temperature.value if thermal else 0.0
        out.append(lim.evaluate_max_limit(
            id=limit.id,
            component=limit.component,
            label=limit.label or channel.label,
            unit=channel.unit,
            channel=limit.channel,
            nominal_curve=nom.channels[limit.channel][0],
            sample_curves=ens.channels[limit.channel],
            rpm=nom.rpm,
            allowable=limit.allowable,
            allowable_samples=allowable_samples,
            reference=reference,
            thermal=thermal,
        ))
    return out


def _rod_checks(nom: RawRun, ens: RawRun, material: Material) -> list[lim.LimitResult]:
    rpm = nom.rpm
    shape_n, shape_e = nom.channels["torque"].shape, ens.channels["torque"].shape

    def b(run: RawRun, key: str, shape) -> np.ndarray:
        return np.broadcast_to(run.rod[key], shape)

    yld = material.prop("yield_strength")
    checks = [
        lim.evaluate_sf_check(
            id="conrod.buckling", component="connecting_rods", label="Rod buckling (firing load)", unit="MPa",
            actual_nominal=nom.channels["rod_compressive_stress"][0],
            actual_samples=ens.channels["rod_compressive_stress"],
            sf_nominal_curve=b(nom, "sf_buckling", shape_n)[0], sf_sample_curves=b(ens, "sf_buckling", shape_e),
            rpm=rpm, allowable_nominal=float(b(nom, "rod_critical_stress", shape_n)[0, 0] * 1e-6),
            allowable_source=Source.CALCULATED,
            note="Allowable is the Johnson/Euler critical stress for the governing plane.",
        ),
        lim.evaluate_sf_check(
            id="conrod.tensile_yield", component="connecting_rods", label="Rod tensile yield (incl. overspeed)", unit="MPa",
            actual_nominal=np.maximum(nom.channels["rod_tensile_stress"][0], b(nom, "rod_tensile_overspeed", shape_n)[0] * 1e-6),
            actual_samples=np.maximum(ens.channels["rod_tensile_stress"], b(ens, "rod_tensile_overspeed", shape_e) * 1e-6),
            sf_nominal_curve=b(nom, "sf_tensile_yield", shape_n)[0], sf_sample_curves=b(ens, "sf_tensile_yield", shape_e),
            rpm=rpm, allowable_nominal=yld.value, allowable_source=yld.source,
            note="Governed by the overspeed load case when it exceeds the sweep.",
        ),
    ]
    fatigue = material.prop("fatigue_strength")
    if fatigue is None or "sf_fatigue" not in nom.rod:
        checks.append(lim.no_data("conrod.fatigue", "connecting_rods", "Rod fatigue (Goodman)", "MPa",
                                  f"No fatigue strength for {material.name}; fatigue not assessed."))
    else:
        amplitude = (nom.channels["rod_tensile_stress"][0] + nom.channels["rod_compressive_stress"][0]) / 2
        amplitude_e = (ens.channels["rod_tensile_stress"] + ens.channels["rod_compressive_stress"]) / 2
        checks.append(lim.evaluate_sf_check(
            id="conrod.fatigue", component="connecting_rods", label="Rod fatigue (Goodman)", unit="MPa",
            actual_nominal=amplitude, actual_samples=amplitude_e,
            sf_nominal_curve=b(nom, "sf_fatigue", shape_n)[0], sf_sample_curves=b(ens, "sf_fatigue", shape_e),
            rpm=rpm, allowable_nominal=fatigue.value, allowable_source=fatigue.source,
            note="Load shown is stress amplitude; allowable is the unmodified material fatigue strength.",
        ))
    return checks


SENSITIVITY_OUTPUTS = {
    "peak_power": "power",
    "peak_torque": "torque",
    "max_peak_pressure": "peak_pressure",
    "max_egt": "egt",
    "max_heat_to_coolant": "heat_to_coolant",
}


def input_label(path: str) -> str:
    spec = PARAM_SPECS.get(path)
    if spec:
        return spec.label
    group, _, key = path.partition(".")
    return f"{'Fuel' if group == 'fuel' else 'Rod material'} {key.replace('_', ' ')}"


def _rank(a: np.ndarray) -> np.ndarray:
    return np.argsort(np.argsort(a, kind="stable"), kind="stable").astype(float)


def sensitivity(ens: RawRun, top: int = 8) -> dict:
    """Spearman rank correlation of each uncertain input with each key output.

    `share` is ρ² normalised over inputs: a rough guide to which uncertainty to reduce
    first (e.g. by measuring that input), not an exact variance decomposition.
    """
    if ens.sampled.n < 30 or not ens.sampled.draws:
        return {}
    out = {}
    for key, channel in SENSITIVITY_OUTPUTS.items():
        y = np.nanmax(ens.channels[channel], axis=1)
        if np.ptp(y) == 0:
            continue
        ry = _rank(y)
        rows = []
        for path, xs in ens.sampled.draws.items():
            if np.ptp(xs) == 0:
                continue
            rho = float(np.corrcoef(_rank(xs), ry)[0, 1])
            rows.append({"path": path, "label": input_label(path), "rho": rho})
        total = sum(r["rho"] ** 2 for r in rows) or 1.0
        for r in rows:
            r["share"] = r["rho"] ** 2 / total
        rows.sort(key=lambda r: abs(r["rho"]), reverse=True)
        out[key] = rows[:top]
    return out


def _warnings(nom: RawRun, rpm: np.ndarray) -> list[str]:
    c = {k: v[0] for k, v in nom.channels.items()}
    out = []
    limited = c["boost_limited"] > 0.5
    if limited.any():
        out.append(
            f"Target boost not reached at {_fmt_ranges(_ranges(rpm, limited))}: the turbine cannot supply enough power there. "
            "This steady-flow turbine model ignores exhaust pulse energy, so real engines usually spool somewhat earlier."
        )
    over = c["injector_duty"] > 1.0
    if over.any():
        out.append(f"Injectors are too small at {_fmt_ranges(_ranges(rpm, over))} (duty > 100 %). Results assume the fuel is delivered anyway.")
    if (c["torque"] <= 0).any():
        out.append("Brake torque is zero or negative at some rpm; check friction and efficiency inputs.")
    return out


def trust_block(sampled: Sampled, samples: int, seed: int) -> dict:
    by_source: dict[str, list[str]] = {}
    for path, param in sampled.inputs.items():
        by_source.setdefault(param.source.value, []).append(path)
    uncertain = [p for p, param in sampled.inputs.items() if param.tol > 0]
    return {
        "models": [
            {"id": engine_mvem.MODEL_ID, "version": engine_mvem.MODEL_VERSION, "fidelity_level": engine_mvem.FIDELITY_LEVEL,
             "name": "Turbocharged SI engine, mean-value model"},
            {"id": conrod.MODEL_ID, "version": conrod.MODEL_VERSION, "fidelity_level": conrod.FIDELITY_LEVEL,
             "name": "Connecting-rod beam checks"},
            {"id": balance.MODEL_ID, "version": balance.MODEL_VERSION, "fidelity_level": 1,
             "name": "Layout balance and firing analysis"},
        ],
        "assumptions": engine_mvem.ASSUMPTIONS + conrod.ASSUMPTIONS + balance.ASSUMPTIONS,
        "not_modelled": engine_mvem.NOT_MODELLED,
        "inputs_by_source": by_source,
        "unknown_inputs": by_source.get(Source.UNKNOWN.value, []),
        "uncertainty": {
            "method": "Monte Carlo" if samples > 1 else "none (nominal only)",
            "samples": samples,
            "seed": seed,
            "uncertain_inputs": uncertain,
            "note": "Bands reflect input uncertainty only. Model-form error is not quantified until the model is "
                    "validated against measurements.",
        },
        "validation": {"status": "unvalidated", "note": "No measured data compared with this run."},
        "disclaimer": DISCLAIMER,
    }
