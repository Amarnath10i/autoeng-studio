"""Whole-vehicle simulation: runs each available physics model over the component graph.

Today: the engine models on the engine component, then straight-line performance
along the driveline chain. Each model's outputs feed the next (engine torque
samples → driveline), so uncertainty propagates across components. Planned
components are reported as "not evaluated", never silently skipped.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from autoeng.analysis import limits as lim
from autoeng.analysis.sampling import _stream
from autoeng.analysis.simulate import DISCLAIMER, simulate
from autoeng.core.params import Param
from autoeng.domain.materials import Material
from autoeng.physics import longitudinal
from autoeng.physics.gas import R_AIR
from autoeng.platform.catalog import CATALOG, EngineParams
from autoeng.platform.vehicle import VehicleDesign


def _draw(seed: int, key: str, p: Param | dict, n: int) -> np.ndarray:
    p = p if isinstance(p, Param) else Param.model_validate(p)
    return p.sample(n, _stream(seed, key))


def _dist(nominal: float, samples: np.ndarray) -> dict:
    samples = samples[np.isfinite(samples)]
    if samples.size == 0:
        return {"nominal": nominal, "p05": None, "p50": None, "p95": None}
    p05, p50, p95 = np.percentile(samples, [5, 50, 95])
    return {"nominal": float(nominal), "p05": float(p05), "p50": float(p50), "p95": float(p95)}


def _inputs(v: VehicleDesign, chain_ids: dict, rpm, torque, engine, n: int, seed: int) -> longitudinal.VehicleInputs:
    gb, fd, wt, body, cl = (v.components[chain_ids[k]].params
                            for k in ("gearbox", "final_drive", "wheel_tire", "body", "clutch"))

    def d(cid_key: str, params: dict, name: str) -> np.ndarray:
        return _draw(seed, f"vehicle.{chain_ids[cid_key]}.{name}", params[name], n)

    t_amb = engine.ambient.temperature.value + 273.15
    rho = engine.ambient.pressure.value * 1e3 / (R_AIR * t_amb)
    return longitudinal.VehicleInputs(
        rpm=rpm, torque=torque,
        rpm_launch=(np.clip(d("clutch", cl, "launch_rpm"), engine.operating.rpm_min, engine.operating.rpm_max)
                    if cl.get("launch_rpm") else float(engine.operating.rpm_min)),
        rpm_min=float(engine.operating.rpm_min),
        rpm_redline=float(engine.operating.rpm_max),
        ratios=list(gb["ratios"]),
        gearbox_eff=d("gearbox", gb, "efficiency"),
        final_ratio=d("final_drive", fd, "ratio"),
        final_eff=d("final_drive", fd, "efficiency"),
        shift_time=d("gearbox", gb, "shift_time"),
        wheel_radius=d("wheel_tire", wt, "rolling_radius"),
        crr=d("wheel_tire", wt, "rolling_resistance"),
        mu=d("wheel_tire", wt, "peak_friction"),
        driven=wt["driven_axle"],
        mass=d("body", body, "mass"),
        cd=d("body", body, "drag_coefficient"),
        area=d("body", body, "frontal_area"),
        wheelbase=d("body", body, "wheelbase"),
        cg_height=d("body", body, "cg_height"),
        front_fraction=d("body", body, "front_weight_fraction"),
        air_density=np.full(n, rho),
    )


def _rating_check(id_, component, label, actual_nom, actual_samples, rating: dict | None, seed) -> lim.LimitResult:
    if rating is None:
        return lim.no_data(id_, component, label, "N·m", "No documented rating entered for this component.")
    p = Param.model_validate(rating)
    allow = p.sample(actual_samples.size, _stream(seed, f"rating.{id_}"))
    sf_nom = p.value / actual_nom
    sf = allow / actual_samples
    sf_p05 = float(np.percentile(sf, 5))
    return lim.LimitResult(
        id=id_, kind="limit", component=component, label=label, unit="N·m", channel=None,
        actual_nominal=float(actual_nom), actual_p95=float(np.percentile(actual_samples, 95)),
        allowable_nominal=p.value, allowable_source=p.source, allowable_ref=p.ref,
        sf_nominal=float(sf_nom), sf_p05=sf_p05, p_exceed=float(np.mean(sf < 1)), at_rpm=None,
        status=lim.status_from_sf(sf_nom, sf_p05),
    )


def simulate_vehicle(v: VehicleDesign, materials: Mapping[str, Material], samples: int = 200, seed: int = 42) -> dict:
    arch = v.architecture_report()
    evaluated, not_evaluated = [], []
    for cid, comp in v.components.items():
        if CATALOG[comp.type].status == "planned":
            not_evaluated.append({"component": cid, "type": comp.type, "reason": "No physics model yet (planned)."})

    engines = v.of_type("engine_turbo_si")
    if not engines or engines[0][1].params is None:
        return {"architecture": arch, "evaluated": [], "not_evaluated": not_evaluated,
                "error": "Add an engine component with parameters to simulate the vehicle."}
    engine_id, engine_comp = engines[0]
    engine = EngineParams.model_validate(engine_comp.params)
    engine_result, nom, ens = simulate(engine, materials, samples, seed, return_raw=True)
    evaluated.append({"component": engine_id, "models": ["engine.turbo_si_mvem", "structure.conrod_beam"]})

    result = {
        "architecture": arch,
        "engine_component": engine_id,
        "engine": engine_result,
        "evaluated": evaluated,
        "not_evaluated": not_evaluated,
        "performance": None,
        "limits": [],
        "targets": [],
        "trust": {
            "models": engine_result["trust"]["models"],
            "assumptions": {"engine": engine_result["trust"]["assumptions"], "vehicle": []},
            "disclaimer": DISCLAIMER,
        },
    }
    if not arch["models"]["vehicle.longitudinal"]:
        result["performance_note"] = ("Connect engine → clutch → gearbox → final drive → wheels & tyres along their "
                                      "rotation ports and add a body with parameters to compute vehicle performance.")
        return result

    chain = arch["driveline_chain"]
    chain_ids = {v.components[c].type: c for c in chain}
    chain_ids["body"] = v.of_type("body")[0][0]
    for key in ("clutch", "gearbox", "final_drive", "wheel_tire", "body"):
        evaluated.append({"component": chain_ids[key], "models": ["vehicle.longitudinal"]})

    rpm = nom.rpm
    n_ens = ens.channels["torque"].shape[0]
    nom_in = _inputs(v, chain_ids, rpm, nom.channels["torque"], engine, 1, seed)
    ens_in = _inputs(v, chain_ids, rpm, ens.channels["torque"], engine, n_ens, seed)
    r_nom = longitudinal.run(nom_in)
    r_ens = longitudinal.run(ens_in, trace_every=10**9) if n_ens > 1 else r_nom

    def dist(key: str) -> dict:
        return _dist(float(r_nom[key][0]), np.asarray(r_ens[key], dtype=float))

    perf = {
        "accel_0_100_s": dist("accel_0_100_s"),
        "quarter_mile_s": dist("quarter_mile_s"),
        "trap_speed_kmh": dist("trap_speed_kmh"),
        "top_speed_kmh": dist("top_speed_kmh"),
        "top_speed_gear": int(r_nom["top_speed_gear"][0]),
        "traction_limited_until_kmh": dist("traction_limited_until_kmh"),
        "max_axle_torque_nm": dist("max_axle_torque_nm"),
        "gear_speeds_at_redline_kmh": longitudinal.gear_speeds_at_redline(nom_in),
        "trace": r_nom["trace"],
        "force_diagram": longitudinal.force_diagram(nom_in, v_max_kmh=float(min(400, r_nom["top_speed_kmh"][0] * 1.25))),
    }
    result["performance"] = perf

    peak_nom = float(np.nanmax(nom.channels["torque"][0]))
    peak_ens = np.nanmax(ens.channels["torque"], axis=1)
    clutch = v.components[chain_ids["clutch"]].params
    gbox = v.components[chain_ids["gearbox"]].params
    fdr = v.components[chain_ids["final_drive"]].params
    result["limits"] = [r.as_dict() for r in [
        _rating_check("clutch_capacity", chain_ids["clutch"], "Clutch torque capacity", peak_nom, peak_ens,
                      clutch.get("torque_capacity"), seed),
        _rating_check("gearbox_input", chain_ids["gearbox"], "Gearbox input torque rating", peak_nom, peak_ens,
                      gbox.get("input_torque_rating"), seed),
        _rating_check("axle_torque", chain_ids["final_drive"], "Axle torque (acceleration run)",
                      float(r_nom["max_axle_torque_nm"][0]), np.asarray(r_ens["max_axle_torque_nm"]),
                      fdr.get("axle_torque_rating"), seed),
    ]]

    for key, better in (("accel_0_100_s", "lower"), ("top_speed_kmh", "higher"), ("quarter_mile_s", "lower")):
        if key not in v.targets:
            continue
        target = v.targets[key]
        vals = np.asarray(r_ens[key], dtype=float)
        met = vals <= target if better == "lower" else vals >= target
        result["targets"].append({"id": key, "target": target, "better": better, "nominal": perf[key]["nominal"],
                                  "probability_met": float(np.mean(met & np.isfinite(vals)))})

    result["trust"]["models"] = result["trust"]["models"] + [{
        "id": longitudinal.MODEL_ID, "version": longitudinal.MODEL_VERSION,
        "fidelity_level": longitudinal.FIDELITY_LEVEL, "name": "Straight-line vehicle performance"}]
    result["trust"]["assumptions"]["vehicle"] = longitudinal.ASSUMPTIONS
    return result
