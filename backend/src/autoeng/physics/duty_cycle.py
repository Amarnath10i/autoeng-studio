"""Time-domain vehicle operation with thermal state (fidelity level 1-2).

Drives an ensemble of vehicles (Monte Carlo samples × weather points × variants)
through a scenario schedule, step by step, and integrates:

  * speed, gear and engine operating point (following the schedule within the
    powertrain and traction limits);
  * coolant temperature: a lumped engine-plus-coolant thermal mass heated by the
    engine's heat rejection and cooled by the radiator through the thermostat;
  * front brake disc temperature: a lumped disc heated by braking power, cooled
    by convection and radiation.

Every member is independent, so the whole ensemble is one set of array
operations per step. That is what makes large studies GPU-friendly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from autoeng.compute import ns, to_numpy

MODEL_ID = "thermal.duty_cycle"
MODEL_VERSION = "1.0.0"
FIDELITY_LEVEL = 1
G = 9.80665
SIGMA = 5.670374419e-8
TAU_S = 2.0  # speed-tracking time constant
INFEASIBLE = -1e30  # force-table marker for gears that cannot run at that speed

ASSUMPTIONS = [
    "The driver follows the schedule with a first-order speed controller (τ = 2 s) within the powertrain, traction "
    "and braking limits; gear choice is the highest gear that can deliver the demanded force (lowest rpm).",
    "Shifts are instantaneous in this model (no torque interruption).",
    "Part-load fuel power follows a Willans line: (brake power + friction power) ÷ gross indicated efficiency at that "
    "rpm, taken from the engine's full-load model. Heat to coolant is the same fraction of fuel heat as at full load.",
    "Engine, coolant and oil are one lumped thermal mass; the thermostat opens linearly between its opening and "
    "fully-open temperatures (a 2 % leak when closed).",
    "Radiator conductance UA scales with airflow^n from the vehicle speed (fan provides a minimum airflow at low speed).",
    "Front brake discs are lumped masses heated by the front share of braking power and cooled by convection "
    "h = h₀ + h₁·v^0.8 and radiation; pads, calipers, fluid and rear brakes are not modelled.",
    "Weather enters through air density (drag, engine), ambient temperature (engine, cooling, brakes), headwind and "
    "a surface friction factor (dry 1.0, wet 0.7, snow 0.3: estimated).",
]


@dataclass
class DutyInputs:
    """All per-member arrays have shape (E,). `force_table` is (G, E, K)."""

    speed_grid: np.ndarray  # (K,) m/s, uniform spacing from 0
    force_table: np.ndarray  # (G, E, K) max wheel force per gear, INFEASIBLE where the gear cannot run
    rpm_per_speed: np.ndarray  # (G, E) engine rpm per m/s in each gear
    rpm_grid: np.ndarray  # (R,)
    friction_power: np.ndarray  # (E, R) W
    indicated_eff: np.ndarray  # (E, R)
    coolant_fraction: np.ndarray
    rpm_min: float
    rpm_redline: float
    overall_ratio: np.ndarray  # (G, E)
    drive_eff: np.ndarray
    wheel_radius: np.ndarray
    mass: np.ndarray
    cd_area: np.ndarray
    crr: np.ndarray
    mu: np.ndarray
    driven_share: np.ndarray  # static share of weight on driven wheels (1 for AWD)
    air_density: np.ndarray
    ambient_k: np.ndarray
    headwind: np.ndarray  # m/s
    # cooling
    ua_max: np.ndarray  # W/K
    rated_airspeed: np.ndarray  # m/s
    fan_fraction: np.ndarray
    airflow_exp: np.ndarray
    thermal_capacity: np.ndarray  # J/K
    t_open: np.ndarray  # K
    t_full: np.ndarray  # K
    t_coolant_max: np.ndarray  # K
    # brakes
    disc_heat_capacity: np.ndarray  # J/K per disc (mass × specific heat)
    disc_area: np.ndarray
    front_bias: np.ndarray
    h0: np.ndarray
    h1: np.ndarray
    emissivity: np.ndarray
    t_disc_max: np.ndarray  # K


def _interp_rows(xp, x, grid, table):
    x = xp.clip(x, grid[0], grid[-1])
    idx = xp.clip(xp.searchsorted(grid, x, side="right") - 1, 0, grid.size - 2)
    rows = xp.arange(table.shape[0])
    x0, x1 = grid[idx], grid[idx + 1]
    y0, y1 = table[rows, idx], table[rows, idx + 1]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def run(inp: DutyInputs, schedule: dict, dt: float, v0: float, cold_start: bool, n_trace: int = 600,
        blocks: int = 1, quantile_trace: bool = False) -> dict:
    """Integrate the schedule. With `quantile_trace`, traces hold the 5/50/95th percentiles of each of
    `blocks` equal consecutive groups of members (e.g. one group per weather point) instead of every member."""
    xp = ns(inp.mass)
    e = inp.mass.shape[0]
    n_gears = inp.force_table.shape[0]
    rows = xp.arange(e)
    dv = float(inp.speed_grid[1] - inp.speed_grid[0])
    k_max = inp.speed_grid.size - 1
    mode_s, target_s, rate_s, grade_s = (schedule[k] for k in ("mode", "target", "rate", "grade"))
    steps = mode_s.size
    every = max(1, steps // n_trace)

    v = xp.full(e, float(v0))
    gear = xp.zeros(e, dtype=xp.int64)
    t_cool = inp.ambient_k.copy() if cold_start else xp.maximum(inp.t_open, inp.ambient_k)
    t_disc = inp.ambient_k.copy()
    inf = xp.full(e, xp.inf)
    first_cool = inf.copy()
    first_disc = inf.copy()
    first_deficit = inf.copy()
    deficit_timer = xp.zeros(e)
    max_cool = t_cool.copy()
    max_disc = t_disc.copy()
    max_torque = xp.zeros(e)
    energy_brake = xp.zeros(e)
    fuel_energy = xp.zeros(e)
    distance = xp.zeros(e)

    trace_keys = ("t", "target", "v", "gear", "rpm", "load", "power", "coolant", "disc", "brake_power",
                  "heat_to_coolant", "heat_rejected", "torque")
    trace: dict[str, list] = {k: [] for k in trace_keys}
    g_idx = xp.arange(n_gears)[:, None]

    for i in range(steps):
        mode, target, rate, grade = int(mode_s[i]), float(target_s[i]), float(rate_s[i]), float(grade_s[i])
        cos_g, sin_g = np.cos(grade), np.sin(grade)

        # Demanded acceleration from the schedule.
        track = (target - v) / TAU_S
        if mode == 1:  # full throttle
            a_req = xp.full(e, 50.0)
        elif mode == 2:  # brake to target
            a_req = xp.where(v > target + 0.1, -rate, track)
        elif mode == 3:  # accelerate to target
            a_req = xp.where(v < target - 0.1, rate, track)
        elif mode == 4:  # idle / hold
            a_req = xp.where(v > 0.1, -2.0, 0.0)
        else:  # cruise
            a_req = xp.clip(track, -3.0, 2.0)

        v_air = v + inp.headwind
        resist = 0.5 * inp.air_density * inp.cd_area * v_air * xp.abs(v_air) + inp.crr * inp.mass * G * cos_g
        f_grade = inp.mass * G * sin_g

        # Available wheel force in every gear at this speed (table lookup).
        pos = xp.clip(v / dv, 0, k_max - 1e-9)
        k0 = pos.astype(xp.int64)
        frac = pos - k0
        f_avail = inp.force_table[:, rows, k0] * (1 - frac) + inp.force_table[:, rows, k0 + 1] * frac  # (G, E)
        f_avail = xp.where(f_avail > INFEASIBLE / 2, f_avail, -xp.inf)

        gamma = 1.04 + 0.0025 * inp.overall_ratio[gear, rows] ** 2
        f_need = gamma * inp.mass * a_req + resist + f_grade
        can = f_avail >= f_need[None, :]
        highest_ok = xp.max(xp.where(can, g_idx, -1), axis=0)
        best = xp.argmax(f_avail, axis=0)
        feasible = xp.isfinite(f_avail)
        highest_feasible = xp.max(xp.where(feasible, g_idx, 0), axis=0)
        gear = xp.where(f_need > 0, xp.where(highest_ok >= 0, highest_ok, best), highest_feasible)

        f_max_gear = f_avail[gear, rows]
        f_trac = inp.mu * inp.mass * G * cos_g * inp.driven_share
        f_drive = xp.where(f_need > 0, xp.minimum(xp.minimum(f_need, xp.maximum(f_max_gear, 0.0)), f_trac), 0.0)
        f_brake = xp.where(f_need < 0, xp.minimum(-f_need, inp.mu * inp.mass * G * cos_g), 0.0)
        gamma = 1.04 + 0.0025 * inp.overall_ratio[gear, rows] ** 2
        a = (f_drive - f_brake - resist - f_grade) / (gamma * inp.mass)
        a = xp.where((v <= 0.0) & (a < 0.0), 0.0, a)

        # Engine operating point.
        rpm = xp.clip(v * inp.rpm_per_speed[gear, rows], inp.rpm_min, inp.rpm_redline)
        torque = f_drive * inp.wheel_radius / (inp.overall_ratio[gear, rows] * inp.drive_eff)
        p_brake = torque * 2.0 * np.pi * rpm / 60.0
        p_fric = _interp_rows(xp, rpm, inp.rpm_grid, inp.friction_power)
        eta_i = _interp_rows(xp, rpm, inp.rpm_grid, inp.indicated_eff)
        fuel_power = (p_brake + p_fric) / xp.maximum(eta_i, 0.05)
        q_cool = inp.coolant_fraction * fuel_power
        load = xp.where(f_max_gear > 0, f_drive / xp.maximum(f_max_gear, 1e-9), 0.0)

        # Coolant circuit.
        opening = xp.clip((t_cool - inp.t_open) / (inp.t_full - inp.t_open), 0.02, 1.0)
        airflow = xp.maximum(inp.fan_fraction, xp.minimum(1.0, xp.abs(v_air) / inp.rated_airspeed))
        ua = inp.ua_max * airflow ** inp.airflow_exp
        q_rad = opening * ua * xp.maximum(t_cool - inp.ambient_k, 0.0)
        t_cool = t_cool + dt * (q_cool - q_rad) / inp.thermal_capacity

        # Front brake discs (per disc).
        p_disc = f_brake * v * inp.front_bias / 2.0
        h = inp.h0 + inp.h1 * xp.abs(v) ** 0.8
        loss = inp.disc_area * (h * (t_disc - inp.ambient_k) + inp.emissivity * SIGMA * (t_disc**4 - inp.ambient_k**4))
        t_disc = t_disc + dt * (p_disc - loss) / inp.disc_heat_capacity

        # Events and extremes.
        t_now = (i + 1) * dt
        first_cool = xp.where((first_cool == xp.inf) & (t_cool > inp.t_coolant_max), t_now, first_cool)
        first_disc = xp.where((first_disc == xp.inf) & (t_disc > inp.t_disc_max), t_now, first_disc)
        behind = (mode != 1) & (target - v > 5.0 / 3.6) & (a_req > 0) & (f_need > xp.minimum(f_max_gear, f_trac) + 1.0)
        deficit_timer = xp.where(behind, deficit_timer + dt, 0.0)
        first_deficit = xp.where((first_deficit == xp.inf) & (deficit_timer >= 5.0), t_now, first_deficit)
        max_cool = xp.maximum(max_cool, t_cool)
        max_disc = xp.maximum(max_disc, t_disc)
        max_torque = xp.maximum(max_torque, torque)
        energy_brake = energy_brake + f_brake * v * dt
        fuel_energy = fuel_energy + fuel_power * dt

        v_new = xp.maximum(v + a * dt, 0.0)
        distance = distance + 0.5 * (v + v_new) * dt
        v = v_new

        if i % every == 0 or i == steps - 1:
            trace["t"].append(t_now)
            trace["target"].append(target if mode != 1 else None)
            for key, arr in (("v", v * 3.6), ("gear", gear + 1.0), ("rpm", rpm), ("load", load),
                             ("power", p_brake / 1e3), ("coolant", t_cool - 273.15), ("disc", t_disc - 273.15),
                             ("brake_power", f_brake * v / 1e3), ("heat_to_coolant", q_cool / 1e3),
                             ("heat_rejected", q_rad / 1e3), ("torque", torque)):
                if quantile_trace:
                    arr = xp.percentile(arr.reshape(blocks, -1), xp.asarray([5.0, 50.0, 95.0]), axis=1)
                trace[key].append(arr)

    series = {k: np.stack([to_numpy(a) for a in trace[k]]) for k in trace_keys if k not in ("t", "target")}
    return {
        "t": trace["t"],
        "target_kmh": [None if x is None else x * 3.6 for x in trace["target"]],
        "series": series,  # each (T, E), or (T, 3, blocks) with quantile_trace
        "first_coolant_limit_s": to_numpy(first_cool),
        "first_disc_limit_s": to_numpy(first_disc),
        "first_speed_deficit_s": to_numpy(first_deficit),
        "max_coolant_c": to_numpy(max_cool) - 273.15,
        "max_disc_c": to_numpy(max_disc) - 273.15,
        "max_engine_torque_nm": to_numpy(max_torque),
        "brake_energy_mj": to_numpy(energy_brake) / 1e6,
        "fuel_energy_mj": to_numpy(fuel_energy) / 1e6,
        "distance_km": to_numpy(distance) / 1e3,
        "final_coolant_c": to_numpy(t_cool) - 273.15,
        "final_disc_c": to_numpy(t_disc) - 273.15,
    }
