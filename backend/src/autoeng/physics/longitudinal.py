"""Straight-line vehicle performance (fidelity level 1), vectorised over Monte Carlo samples.

Engine full-load torque → gearbox → final drive → tyres → road. Integrates a
full-throttle run from standstill with optimal upshifts, traction limits with
longitudinal weight transfer, aerodynamic drag and rolling resistance. Also finds
top speed and the driveline loads the run imposes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MODEL_ID = "vehicle.longitudinal"
MODEL_VERSION = "1.1.0"
FIDELITY_LEVEL = 1
G = 9.80665
QUARTER_MILE_M = 402.336

ASSUMPTIONS = [
    "Full-throttle run on a flat, dry road with the engine's full-load torque curve (no transient turbo lag).",
    "Launch: the clutch slips with the engine held at the launch rpm until the wheels catch up, with full-load "
    "(fully spooled) torque at that rpm; clutch slip energy and heat are not computed.",
    "Rotating inertia via the mass factor γ = 1 + (4·I_wheel + I_engine·ξ²·η) / (m·r²), with ξ the overall ratio. "
    "Defaults when not given: I_engine ≈ 0.10 + 0.05·V_d[L] kg·m² (engine, flywheel and clutch) and "
    "I_wheel ≈ 1.1·(r / 0.32 m)² kg·m² per wheel (tyre, rim, disc and hub).",
    "Upshift when the next gear gives more wheel force, or at redline; torque is zero during the shift time.",
    "Traction limit μ × driven-axle load, with quasi-static longitudinal weight transfer m·a·h/L; "
    "no tyre slip curve, suspension dynamics or aerodynamic downforce.",
    "Drag ½ρ·Cd·A·v² with air density from ambient conditions; constant rolling resistance coefficient.",
]


@dataclass
class VehicleInputs:
    """Arrays of shape (S,) unless noted."""

    rpm: np.ndarray  # (R,)
    torque: np.ndarray  # (S, R) engine full-load torque, N·m
    rpm_launch: np.ndarray | float  # engine rpm held while the clutch slips in first gear
    rpm_min: float  # lowest usable engine rpm (bottom of the torque curve)
    rpm_redline: float
    engine_inertia: np.ndarray  # kg·m², engine + flywheel + clutch
    wheel_inertia: np.ndarray  # kg·m² per wheel
    ratios: list[float]
    gearbox_eff: np.ndarray
    final_ratio: np.ndarray
    final_eff: np.ndarray
    shift_time: np.ndarray
    wheel_radius: np.ndarray
    crr: np.ndarray
    mu: np.ndarray
    driven: str  # front | rear | all
    mass: np.ndarray
    cd: np.ndarray
    area: np.ndarray
    wheelbase: np.ndarray
    cg_height: np.ndarray
    front_fraction: np.ndarray
    air_density: np.ndarray


def _interp_rows(x: np.ndarray, xp: np.ndarray, fp: np.ndarray) -> np.ndarray:
    """Row-wise linear interpolation: x (S,) or (S,K) into fp (S,R) sampled at xp (R,)."""
    x = np.clip(x, xp[0], xp[-1])
    idx = np.clip(np.searchsorted(xp, x, side="right") - 1, 0, xp.size - 2)
    x0, x1 = xp[idx], xp[idx + 1]
    rows = np.arange(fp.shape[0]).reshape((-1,) + (1,) * (x.ndim - 1))
    y0, y1 = fp[rows, idx], fp[rows, idx + 1]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def default_engine_inertia(displacement_l):
    """Engine + flywheel + clutch rotating inertia, kg·m² (typical of modern passenger-car engines)."""
    return 0.10 + 0.05 * displacement_l


def default_wheel_inertia(radius_m):
    """One road wheel with tyre, brake disc and hub, kg·m²."""
    return 1.1 * (radius_m / 0.32) ** 2


def mass_factor(overall_ratio, mass, wheel_radius, engine_inertia, wheel_inertia, drive_eff):
    """γ: effective mass / mass, adding the wheels and the engine reflected through the overall ratio."""
    return 1.0 + (4.0 * wheel_inertia + engine_inertia * overall_ratio**2 * drive_eff) / (mass * wheel_radius**2)


def _engine_force(v: np.ndarray, gear: int, inp: VehicleInputs, allow_slip: bool):
    """Wheel force available in `gear` at speed v (before the traction limit), and the engine rpm."""
    overall = inp.ratios[gear] * inp.final_ratio
    rpm = v / inp.wheel_radius * overall * 60.0 / (2.0 * np.pi)
    slipping = allow_slip & (rpm < inp.rpm_launch)
    engine_rpm = np.where(slipping, inp.rpm_launch, rpm)
    torque = _interp_rows(engine_rpm, inp.rpm, inp.torque)
    force = torque * overall * inp.gearbox_eff * inp.final_eff / inp.wheel_radius
    valid = (rpm <= inp.rpm_redline) & (slipping | (rpm >= inp.rpm_min))
    return np.where(valid, force, -np.inf), rpm


def _resistance(v, inp: VehicleInputs):
    return 0.5 * inp.air_density * inp.cd * inp.area * v**2 + inp.crr * inp.mass * G


def _traction_limit(resist, gamma, inp: VehicleInputs):
    k = inp.mu * inp.cg_height / (inp.wheelbase * gamma)
    if inp.driven == "all":
        return inp.mu * inp.mass * G
    if inp.driven == "rear":
        return (inp.mu * inp.mass * G * (1.0 - inp.front_fraction) - k * resist) / (1.0 - k)
    return (inp.mu * inp.mass * G * inp.front_fraction + k * resist) / (1.0 + k)


def run(inp: VehicleInputs, dt: float = 0.01, t_max: float = 60.0, trace_every: int = 5) -> dict:
    s = inp.mass.shape[0]
    n_gears = len(inp.ratios)
    v = np.zeros(s)
    x = np.zeros(s)
    gear = np.zeros(s, dtype=int)
    shift_left = np.zeros(s)
    t_100 = np.full(s, np.nan)
    t_quarter = np.full(s, np.nan)
    v_trap = np.full(s, np.nan)
    traction_until = np.zeros(s)
    max_axle_torque = np.zeros(s)
    trace = {"t": [], "v": [], "gear": [], "a": [], "rpm": []}

    steps = int(t_max / dt)
    for step in range(steps):
        forces = np.stack([_engine_force(v, g, inp, allow_slip=(g == 0))[0] for g in range(n_gears)])  # (G, S)
        best = np.argmax(forces, axis=0)
        # Upshift only, one gear at a time, when a higher gear is better or the current one is past redline.
        want_up = (best > gear) & (shift_left <= 0) & (gear < n_gears - 1)
        shift_left = np.where(want_up, inp.shift_time, shift_left)
        gear = np.where(want_up, gear + 1, gear)
        in_shift = shift_left > 0

        f_engine = forces[gear, np.arange(s)]
        f_engine = np.where(np.isfinite(f_engine), f_engine, 0.0)
        overall = np.asarray(inp.ratios)[gear] * inp.final_ratio
        gamma = mass_factor(overall, inp.mass, inp.wheel_radius, inp.engine_inertia, inp.wheel_inertia,
                            inp.gearbox_eff * inp.final_eff)
        resist = _resistance(v, inp)
        f_trac_max = _traction_limit(resist, gamma, inp)
        limited = f_engine > f_trac_max
        f_drive = np.where(in_shift, 0.0, np.minimum(f_engine, f_trac_max))
        a = (f_drive - resist) / (gamma * inp.mass)
        a = np.where((v <= 0) & (a < 0), 0.0, a)

        traction_until = np.where(limited & ~in_shift, v, traction_until)
        max_axle_torque = np.maximum(max_axle_torque, f_drive * inp.wheel_radius)

        if step % trace_every == 0:
            rpm0 = v[0] / inp.wheel_radius[0] * inp.ratios[gear[0]] * inp.final_ratio[0] * 60.0 / (2.0 * np.pi)
            trace["t"].append(round(step * dt, 3))
            trace["v"].append(float(v[0] * 3.6))
            trace["gear"].append(int(gear[0]) + 1)
            trace["a"].append(float(a[0] / G))
            trace["rpm"].append(float(max(rpm0, np.ravel(inp.rpm_launch)[0])))

        v_new = v + a * dt
        x += 0.5 * (v + v_new) * dt
        crossed_100 = np.isnan(t_100) & (v_new >= 100 / 3.6)
        frac = np.where(crossed_100, (100 / 3.6 - v) / np.maximum(v_new - v, 1e-9), 0.0)
        t_100 = np.where(crossed_100, (step + frac) * dt, t_100)
        crossed_q = np.isnan(t_quarter) & (x >= QUARTER_MILE_M)
        t_quarter = np.where(crossed_q, (step + 1) * dt, t_quarter)
        v_trap = np.where(crossed_q, v_new * 3.6, v_trap)
        v = v_new
        shift_left = np.maximum(shift_left - dt, 0.0)
        if not np.isnan(t_100).any() and not np.isnan(t_quarter).any():
            break

    top, gear_top = top_speed(inp)
    return {
        "accel_0_100_s": t_100,
        "quarter_mile_s": t_quarter,
        "trap_speed_kmh": v_trap,
        "top_speed_kmh": top * 3.6,
        "top_speed_gear": gear_top,
        "traction_limited_until_kmh": traction_until * 3.6,
        "max_axle_torque_nm": max_axle_torque,
        "trace": trace,
    }


def top_speed(inp: VehicleInputs, v_max_kmh: float = 500.0, step_kmh: float = 0.5):
    """Highest speed reachable from below: the first speed where no gear overcomes resistance."""
    speeds = np.arange(step_kmh, v_max_kmh, step_kmh) / 3.6  # (K,)
    s = inp.mass.shape[0]
    vv = np.broadcast_to(speeds, (s, speeds.size))
    forces = np.stack([
        _engine_force(vv, g, _broadcast(inp), allow_slip=False)[0] for g in range(len(inp.ratios))
    ])  # (G, S, K)
    best_force = forces.max(axis=0)
    best_gear = forces.argmax(axis=0)
    resist = 0.5 * inp.air_density[:, None] * inp.cd[:, None] * inp.area[:, None] * vv**2 + (inp.crr * inp.mass * G)[:, None]
    surplus = best_force - resist
    # First speed above 20 km/h (past launch) where the surplus is gone.
    fails = (surplus <= 0) & (vv > 20 / 3.6)
    first = np.where(fails.any(axis=1), fails.argmax(axis=1), speeds.size - 1)
    idx = np.maximum(first - 1, 0)
    return speeds[idx], best_gear[np.arange(s), idx] + 1


def _broadcast(inp: VehicleInputs) -> VehicleInputs:
    """Reshape (S,) parameters to (S, 1) for evaluation over a speed grid."""
    fields = {}
    for k, val in vars(inp).items():
        if isinstance(val, np.ndarray) and val.ndim == 1 and k != "rpm":
            fields[k] = val[:, None]
        else:
            fields[k] = val
    return VehicleInputs(**fields)


def gear_speeds_at_redline(inp: VehicleInputs) -> list[float]:
    """Nominal (sample 0) road speed at redline in each gear, km/h."""
    return [
        float(inp.rpm_redline * 2 * np.pi / 60 * inp.wheel_radius[0] / (r * inp.final_ratio[0]) * 3.6)
        for r in inp.ratios
    ]


def force_diagram(inp: VehicleInputs, v_max_kmh: float = 300.0, step_kmh: float = 2.0) -> dict:
    """Nominal tractive force per gear and road resistance versus speed (the classic traction diagram)."""
    speeds = np.arange(0.0, v_max_kmh + step_kmh, step_kmh)
    v = speeds / 3.6
    nom = _row0(inp)
    vv = np.broadcast_to(v, (1, v.size))
    gears = []
    for g in range(len(inp.ratios)):
        f, _ = _engine_force(vv, g, _broadcast(nom), allow_slip=False)
        gears.append([None if not np.isfinite(val) else round(float(val), 1) for val in f[0]])
    resist = 0.5 * nom.air_density[0] * nom.cd[0] * nom.area[0] * v**2 + nom.crr[0] * nom.mass[0] * G
    return {"speed_kmh": speeds.tolist(), "gears": gears, "resistance": [round(float(r), 1) for r in resist]}


def _row0(inp: VehicleInputs) -> VehicleInputs:
    fields = {}
    for k, val in vars(inp).items():
        if k == "torque" or isinstance(val, np.ndarray) and val.ndim == 1 and k != "rpm":
            fields[k] = val[:1]
        else:
            fields[k] = val
    return VehicleInputs(**fields)
