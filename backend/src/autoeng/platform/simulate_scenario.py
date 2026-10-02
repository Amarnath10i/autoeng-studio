"""Run a vehicle through a scenario in time, across weather points and Monte Carlo samples.

Pipeline: engine full-load model at each weather point (batched) → wheel-force
tables per gear → time-domain drive with coolant and brake-disc thermal states →
events (time to overheat, brake fade, can't hold speed) and time series with
uncertainty bands. Ensembles run on the GPU when one is available and the
ensemble is large.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from autoeng import compute
from autoeng.analysis import limits as lim
from autoeng.analysis.sampling import _stream
from autoeng.analysis.simulate import DISCLAIMER, run_raw
from autoeng.core.params import Param
from autoeng.domain.materials import Material
from autoeng.physics import duty_cycle, longitudinal
from autoeng.physics.gas import R_AIR
from autoeng.physics.longitudinal import _interp_rows
from autoeng.platform.catalog import EngineParams
from autoeng.platform.scenarios import Scenario, Weather, compile_schedule
from autoeng.platform.vehicle import VehicleDesign

MAX_ENSEMBLE = 40_000
MAX_TRACE_POINTS = 8
SPEED_STEP = 0.25  # m/s, force-table resolution


def _param(p) -> Param:
    return p if isinstance(p, Param) else Param.model_validate(p)


def _dist(samples: np.ndarray) -> dict:
    samples = np.asarray(samples, dtype=float)
    finite = samples[np.isfinite(samples)]
    if finite.size == 0:
        return {"p05": None, "p50": None, "p95": None}
    p05, p50, p95 = np.percentile(finite, [5, 50, 95])
    return {"p05": float(p05), "p50": float(p50), "p95": float(p95)}


def _event(times: np.ndarray, duration: float) -> dict:
    hit = np.isfinite(times)
    return {
        "probability": float(hit.mean()),
        "median_time_s": float(np.median(times[hit])) if hit.any() else None,
        "earliest_time_s": float(times[hit].min()) if hit.any() else None,
        "duration_s": duration,
    }


def requirements(v: VehicleDesign) -> list[str]:
    arch = v.architecture_report()
    missing = []
    if not arch["models"]["vehicle.longitudinal"]:
        missing.append("a complete driveline (engine → clutch → gearbox → final drive → wheels) and a body")
    for type_id, label in (("radiator", "a cooling circuit"), ("brakes_front", "front brakes")):
        comps = v.of_type(type_id)
        if not comps or comps[0][1].params is None:
            missing.append(f"{label} with parameters")
    return missing


def run_scenario(
    v: VehicleDesign,
    scenario: Scenario,
    materials: Mapping[str, Material],
    samples: int = 100,
    seed: int = 42,
    weather_points: list[Weather] | None = None,
) -> dict:
    missing = requirements(v)
    if missing:
        raise ValueError("To run scenarios the vehicle needs " + "; ".join(missing))
    weathers = weather_points or [scenario.weather]
    n_points = len(weathers)
    samples = max(1, min(samples, MAX_ENSEMBLE // n_points))
    schedule = compile_schedule(scenario)

    arch = v.architecture_report()
    ids = {v.components[c].type: c for c in arch["driveline_chain"]}
    ids["body"] = v.of_type("body")[0][0]
    ids["radiator"] = v.of_type("radiator")[0][0]
    ids["brakes"] = v.of_type("brakes_front")[0][0]
    engine = EngineParams.model_validate(v.components[ids["engine_turbo_si"]].params)
    points = [{"ambient.temperature": w.ambient_temp_c, "ambient.pressure": w.pressure_kpa} for w in weathers]

    nominal = _run(v, engine, ids, weathers, points, schedule, scenario, materials, 1, seed, full_trace=True)
    ensemble = (_run(v, engine, ids, weathers, points, schedule, scenario, materials, samples, seed, full_trace=False)
                if samples > 1 else nominal)

    duration = float(schedule["mode"].size * scenario.dt_s)
    gb = v.components[ids["gearbox"]].params
    cl = v.components[ids["clutch"]].params
    cool = v.components[ids["radiator"]].params
    brk = v.components[ids["brakes"]].params
    out_points = []
    for p, w in enumerate(weathers):
        sl = slice(p * ensemble["n"], (p + 1) * ensemble["n"])
        r = ensemble["result"]
        amb = w.ambient_temp_c
        max_cool, max_disc = r["max_coolant_c"][sl], r["max_disc_c"][sl]
        max_tq = r["max_engine_torque_nm"][sl]
        n_max_cool = float(nominal["result"]["max_coolant_c"][p])
        n_max_disc = float(nominal["result"]["max_disc_c"][p])
        n_max_tq = float(nominal["result"]["max_engine_torque_nm"][p])
        checks = [
            _check("coolant", ids["radiator"], "Coolant temperature", "°C", n_max_cool, max_cool,
                   _param(cool["max_coolant_temp"]), amb, thermal=True),
            _check("brake_disc", ids["brakes"], "Front disc temperature", "°C", n_max_disc, max_disc,
                   _param(brk["max_disc_temp"]), amb, thermal=True),
            _check("gearbox_torque", ids["gearbox"], "Gearbox input torque", "N·m", n_max_tq, max_tq,
                   _param(gb["input_torque_rating"]), 0.0),
            _check("clutch_torque", ids["clutch"], "Clutch torque", "N·m", n_max_tq, max_tq,
                   _param(cl["torque_capacity"]), 0.0),
        ]
        out_points.append({
            "weather": w.model_dump() | {"pressure_kpa": w.pressure_kpa},
            "engine_peak_power_kw": _dist(ensemble["peak_power"][sl]) | {"nominal": float(nominal["peak_power"][p])},
            "max_coolant_c": _dist(max_cool) | {"nominal": n_max_cool},
            "max_disc_c": _dist(max_disc) | {"nominal": n_max_disc},
            "max_engine_torque_nm": _dist(max_tq) | {"nominal": n_max_tq},
            "final_coolant_c": _dist(r["final_coolant_c"][sl]),
            "coolant_limit": _event(r["first_coolant_limit_s"][sl], duration),
            "disc_limit": _event(r["first_disc_limit_s"][sl], duration),
            "speed_deficit": _event(r["first_speed_deficit_s"][sl], duration),
            "fuel_energy_mj": _dist(r["fuel_energy_mj"][sl]),
            "brake_energy_mj": _dist(r["brake_energy_mj"][sl]),
            "distance_km": _dist(r["distance_km"][sl]),
            "checks": [c.as_dict() for c in checks],
        })

    trace = None
    if n_points <= MAX_TRACE_POINTS:
        nr, er = nominal["result"], ensemble["result"]
        trace = {
            "t": nr["t"],
            "target_kmh": nr["target_kmh"],
            "nominal": {k: np.round(a.T, 3).tolist() for k, a in nr["series"].items()},  # [point][time]
            "bands": ({k: {q: np.round(a[:, i, :].T, 3).tolist() for i, q in enumerate(("p05", "p50", "p95"))}
                       for k, a in er["series"].items()} if samples > 1 else None),
        }

    return {
        "scenario": scenario.model_dump() | {"duration_s": duration},
        "samples": samples,
        "points": out_points,
        "trace": trace,
        "limits": {
            "max_coolant_temp_c": _param(cool["max_coolant_temp"]).value,
            "max_disc_temp_c": _param(brk["max_disc_temp"]).value,
            "gearbox_torque_nm": _param(gb["input_torque_rating"]).value,
            "clutch_torque_nm": _param(cl["torque_capacity"]).value,
        },
        "compute": ensemble["device"],
        "trust": {
            "models": [{"id": duty_cycle.MODEL_ID, "version": duty_cycle.MODEL_VERSION,
                        "fidelity_level": duty_cycle.FIDELITY_LEVEL, "name": "Time-domain drive with thermal states"}],
            "assumptions": duty_cycle.ASSUMPTIONS,
            "uncertainty": {"method": "Monte Carlo" if samples > 1 else "nominal only", "samples": samples,
                            "seed": seed, "note": "Bands reflect input uncertainty only."},
            "validation": {"status": "unvalidated"},
            "disclaimer": DISCLAIMER,
        },
    }


def _check(id_, component, label, unit, nominal, samples, allow: Param, reference, thermal=False) -> lim.LimitResult:
    warning, critical = (lim.THERMAL_WARNING_SF, lim.THERMAL_CRITICAL_SF) if thermal else (lim.WARNING_SF, lim.CRITICAL_SF)
    if nominal - reference < 1.0:
        return lim.LimitResult(
            id=id_, kind="limit", component=component, label=label, unit=unit, channel=None,
            actual_nominal=float(nominal), actual_p95=float(np.percentile(samples, 95)), allowable_nominal=allow.value,
            allowable_source=allow.source, allowable_ref=allow.ref, sf_nominal=None, sf_p05=None, p_exceed=0.0,
            at_rpm=None, status="ok", note="Not loaded in this scenario.", reference=reference, warning_sf=warning)
    denom_nom = max(nominal - reference, 1e-9)
    sf_nom = (allow.value - reference) / denom_nom
    sf = (allow.value - reference) / np.maximum(samples - reference, 1e-9)
    sf_p05 = float(np.percentile(sf, 5))
    return lim.LimitResult(
        id=id_, kind="limit", component=component, label=label, unit=unit, channel=None,
        actual_nominal=float(nominal), actual_p95=float(np.percentile(samples, 95)),
        allowable_nominal=allow.value, allowable_source=allow.source, allowable_ref=allow.ref,
        sf_nominal=float(sf_nom), sf_p05=sf_p05, p_exceed=float(np.mean(sf < 1)), at_rpm=None,
        status=lim.status_from_sf(sf_nom, sf_p05, warning, critical),
        note="SF on temperature rise above ambient." if thermal else "", reference=reference, warning_sf=warning,
    )


def _run(v, engine, ids, weathers, points, schedule, scenario, materials, n, seed, full_trace: bool) -> dict:
    n_points = len(weathers)
    raw = run_raw(engine, materials, n, seed, points=points)
    e = raw.sampled.n  # n_points * n, point-major
    rpm = raw.rpm
    ch = raw.channels
    vd = raw.sampled.engine.displacement.reshape(-1, 1)
    cycles = rpm[None, :] / 120.0
    friction_power = ch["fmep"] * 1e5 * vd * cycles
    indicated_eff = ch["imep"] * 1e5 * vd * cycles / np.maximum(ch["heat_released"] * 1e3, 1.0)
    torque = ch["torque"]

    def draw(comp_key: str, name: str) -> np.ndarray:
        comp = v.components[ids[comp_key]].params
        vals = _param(comp[name]).sample(n, _stream(seed, f"vehicle.{ids[comp_key]}.{name}"))
        return np.tile(vals, n_points)

    def per_point(values: list[float]) -> np.ndarray:
        return np.repeat(np.asarray(values, dtype=float), n)

    gb, fd, wt, cl = (v.components[ids[k]].params for k in ("gearbox", "final_drive", "wheel_tire", "clutch"))
    ratios = np.asarray(gb["ratios"], dtype=float)
    final = draw("final_drive", "ratio")
    radius = draw("wheel_tire", "rolling_radius")
    drive_eff = draw("gearbox", "efficiency") * draw("final_drive", "efficiency")
    overall = ratios[:, None] * final[None, :]  # (G, E)
    rpm_per_speed = overall / radius[None, :] * 60.0 / (2.0 * np.pi)
    rpm_min, redline = float(engine.operating.rpm_min), float(engine.operating.rpm_max)
    launch = (np.clip(draw("clutch", "launch_rpm"), rpm_min, redline) if cl.get("launch_rpm")
              else np.full(e, rpm_min))

    v_top = redline / rpm_per_speed[-1].min()
    speed_grid = np.arange(0.0, v_top + 2 * SPEED_STEP, SPEED_STEP)
    table = np.empty((ratios.size, e, speed_grid.size))
    for g in range(ratios.size):
        eng_rpm = speed_grid[None, :] * rpm_per_speed[g][:, None]
        slipping = (g == 0) & (eng_rpm < launch[:, None])
        eff_rpm = np.where(slipping, launch[:, None], eng_rpm)
        tq = _interp_rows(eff_rpm, rpm, torque)
        force = tq * overall[g][:, None] * drive_eff[:, None] / radius[:, None]
        ok = (eng_rpm <= redline) & (slipping | (eng_rpm >= rpm_min))
        table[g] = np.where(ok, force, duty_cycle.INFEASIBLE)

    front = draw("body", "front_weight_fraction")
    driven = {"front": front, "rear": 1.0 - front, "all": np.ones(e)}[wt["driven_axle"]]
    temps_k = per_point([w.ambient_temp_c + 273.15 for w in weathers])
    pressures = per_point([w.pressure_kpa * 1e3 for w in weathers])
    brk = v.components[ids["brakes"]].params
    disc_mat = materials.get(brk["disc_material_id"])
    if disc_mat is None or disc_mat.prop("specific_heat") is None:
        raise ValueError(f"Brake disc material '{brk['disc_material_id']}' needs a specific heat value")
    cp_disc = np.tile(disc_mat.prop("specific_heat").sample(n, _stream(seed, "brake.disc.cp")), n_points)

    fields = dict(
        speed_grid=speed_grid, force_table=table, rpm_per_speed=rpm_per_speed, rpm_grid=rpm,
        friction_power=friction_power, indicated_eff=indicated_eff,
        coolant_fraction=raw.sampled.engine.coolant_heat_fraction.ravel(),
        rpm_min=rpm_min, rpm_redline=redline, overall_ratio=overall, drive_eff=drive_eff, wheel_radius=radius,
        engine_inertia=(draw("clutch", "rotating_inertia") if cl.get("rotating_inertia")
                        else longitudinal.default_engine_inertia(vd.ravel() * 1000)),
        wheel_inertia=(draw("wheel_tire", "wheel_inertia") if wt.get("wheel_inertia")
                       else longitudinal.default_wheel_inertia(radius)),
        mass=draw("body", "mass"), cd_area=draw("body", "drag_coefficient") * draw("body", "frontal_area"),
        crr=draw("wheel_tire", "rolling_resistance"),
        mu=draw("wheel_tire", "peak_friction") * per_point([w.friction_factor for w in weathers]),
        driven_share=driven, air_density=pressures / (R_AIR * temps_k), ambient_k=temps_k,
        headwind=per_point([w.headwind_kmh / 3.6 for w in weathers]),
        ua_max=draw("radiator", "rated_heat_rejection") * 1e3 / draw("radiator", "rated_delta_t"),
        rated_airspeed=draw("radiator", "rated_airspeed") / 3.6,
        fan_fraction=draw("radiator", "fan_airflow_fraction"),
        airflow_exp=draw("radiator", "airflow_exponent"),
        thermal_capacity=draw("radiator", "circuit_thermal_capacity") * 1e3,
        t_open=draw("radiator", "thermostat_open") + 273.15,
        t_full=draw("radiator", "thermostat_full_open") + 273.15,
        t_coolant_max=draw("radiator", "max_coolant_temp") + 273.15,
        disc_heat_capacity=draw("brakes", "disc_mass") * cp_disc,
        disc_area=draw("brakes", "disc_cooling_area"), front_bias=draw("brakes", "front_bias"),
        h0=draw("brakes", "h_standstill"), h1=draw("brakes", "h_speed_coeff"),
        emissivity=draw("brakes", "emissivity"), t_disc_max=draw("brakes", "max_disc_temp") + 273.15,
    )
    # The time loop launches ~100 small kernels per step, so the GPU only pays off for large ensembles.
    xp = compute.for_size(int(e * 2.5))
    if xp is not np:
        fields = {k: (xp.asarray(val) if isinstance(val, np.ndarray) else val) for k, val in fields.items()}
    inputs = duty_cycle.DutyInputs(**fields)
    result = duty_cycle.run(inputs, schedule, scenario.dt_s, scenario.initial_speed_kmh / 3.6, scenario.cold_start,
                            blocks=n_points, quantile_trace=not full_trace)
    return {"result": result, "n": n, "device": compute.describe(xp),
            "peak_power": np.nanmax(ch["power"], axis=1)}
