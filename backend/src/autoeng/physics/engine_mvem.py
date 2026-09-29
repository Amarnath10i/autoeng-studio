"""Mean-value model of a turbocharged four-stroke spark-ignition engine (fidelity level 1-2).

For each rpm point the model finds the boost the turbocharger can actually sustain
by balancing turbine and compressor shaft power, then computes air and fuel flow,
indicated work, pumping and friction losses, brake output, peak cylinder pressure
and the heat split between work, coolant and exhaust.

Every array is shaped (samples, rpm points) so one call evaluates a whole Monte
Carlo ensemble across the whole sweep. All inputs and internal quantities are SI.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from autoeng.compute import ns
from autoeng.physics import gas

MODEL_ID = "engine.turbo_si_mvem"
MODEL_VERSION = "1.0.0"
FIDELITY_LEVEL = 1

ASSUMPTIONS = [
    "Quasi-steady, full-load (wide-open throttle) operation at each rpm point; no transients or turbo lag.",
    "Four-stroke cycle: air flow ṁ = VE·ρ_manifold·V_d·N/120.",
    "Compressor and turbine efficiencies are constant (no maps); surge and shaft speed are not predicted.",
    "Turbine treated as a single isentropic nozzle of fixed effective area with steady flow. Exhaust pulse energy is ignored, "
    "which tends to under-predict boost at low rpm.",
    "The wastegate opens as needed to hold the boost target; where the turbine cannot supply enough power, boost is reduced "
    "until turbine power × shaft efficiency equals compressor power.",
    "Gross indicated efficiency = efficiency ratio × ideal Otto efficiency 1 − CR^(1−γ).",
    "For rich mixtures (λ < 1) only the air-limited share of fuel releases heat.",
    "Gas-exchange work = (p_intake − p_exhaust)·V_d per cycle.",
    "Friction follows the Barnes-Moss correlation form FMEP = a + b·N + c·N². Coefficients from older engines tend to "
    "over-predict friction in modern engines; the correlation also partly includes pumping, so pumping is partly double-counted.",
    "Peak cylinder pressure = p_manifold · CR^n · pressure-rise ratio. This is an order-of-magnitude estimate, not a combustion model.",
    "Turbine inlet temperature comes from an energy balance: fuel heat − gross indicated work − coolant heat = exhaust sensible heat. "
    "Exhaust manifold heat loss is ignored.",
    "Ambient air enters the compressor with no filter pressure loss; the intercooler sinks to ambient temperature.",
]

NOT_MODELLED = [
    "Knock and spark timing. The knock limit is often what really limits a turbo engine's boost and compression ratio.",
    "Compressor surge and choke lines and turbo shaft speed (these need a compressor map).",
    "Transient response (turbo lag), exhaust pulse tuning, twin-scroll effects.",
    "Charge-air pressure losses that vary with flow; variable valve timing; exhaust gas recirculation.",
    "Temperature-dependent material properties.",
]


@dataclass
class EngineInputs:
    """Sampled engine inputs in SI units. Arrays have shape (S, 1)."""

    cylinders: int
    bore: np.ndarray
    stroke: np.ndarray
    compression_ratio: np.ndarray
    rpm_min: float
    rpm_max: float
    ve_peak: np.ndarray
    ve_peak_rpm: np.ndarray
    ve_falloff: np.ndarray
    boost_target: np.ndarray  # Pa gauge
    eta_compressor: np.ndarray
    eta_turbine: np.ndarray
    eta_mechanical: np.ndarray
    turbine_area: np.ndarray  # m²
    ic_effectiveness: np.ndarray
    ic_pressure_drop: np.ndarray  # Pa
    lambda_ratio: np.ndarray
    efficiency_ratio: np.ndarray
    cycle_gamma: np.ndarray
    combustion_efficiency: np.ndarray
    pressure_rise_ratio: np.ndarray
    polytropic_n: np.ndarray
    coolant_heat_fraction: np.ndarray
    exhaust_backpressure: np.ndarray  # Pa gauge
    exhaust_cp: np.ndarray
    exhaust_gamma: np.ndarray
    friction_a: np.ndarray  # Pa
    friction_b: np.ndarray  # Pa per 1000 rpm
    friction_c: np.ndarray  # Pa per (1000 rpm)²
    fuel_lhv: np.ndarray  # J/kg
    afr_stoich: np.ndarray
    fuel_density: np.ndarray  # kg/m³
    injector_flow: np.ndarray  # m³/s per injector
    injector_count: int
    ambient_temp: np.ndarray  # K
    ambient_pressure: np.ndarray  # Pa

    @property
    def displacement(self) -> np.ndarray:
        return self.cylinders * np.pi / 4.0 * self.bore**2 * self.stroke


def volumetric_efficiency(inp: EngineInputs, rpm: np.ndarray) -> np.ndarray:
    xp = ns(inp.ve_peak)
    span = max(inp.rpm_max - inp.rpm_min, 1.0)
    ve = inp.ve_peak - inp.ve_falloff * ((rpm - inp.ve_peak_rpm) / span) ** 2
    return xp.clip(ve, 0.2, 1.4)


class _Charge:
    """Intake-side state and combustion energy split for a given boost level."""

    def __init__(self, inp: EngineInputs, rpm: np.ndarray, ve: np.ndarray, boost: np.ndarray):
        xp = ns(boost)
        self.boost = boost
        self.p_manifold = inp.ambient_pressure + boost
        self.p_compressor_out = self.p_manifold + inp.ic_pressure_drop
        self.pressure_ratio = self.p_compressor_out / inp.ambient_pressure
        self.t_compressor_out = gas.compressor_outlet_temp(inp.ambient_temp, self.pressure_ratio, inp.eta_compressor)
        self.t_manifold = self.t_compressor_out - inp.ic_effectiveness * (self.t_compressor_out - inp.ambient_temp)
        rho = self.p_manifold / (gas.R_AIR * self.t_manifold)
        self.air_flow = ve * rho * inp.displacement * rpm / 120.0
        self.fuel_flow = self.air_flow / (inp.lambda_ratio * inp.afr_stoich)
        burned_fuel = self.air_flow / (inp.afr_stoich * xp.maximum(inp.lambda_ratio, 1.0))
        self.heat_released = inp.combustion_efficiency * inp.fuel_lhv * burned_fuel
        otto = 1.0 - xp.power(inp.compression_ratio, 1.0 - inp.cycle_gamma)
        self.indicated_power = inp.efficiency_ratio * otto * self.heat_released
        self.heat_to_coolant = inp.coolant_heat_fraction * self.heat_released
        self.exhaust_heat = xp.maximum(self.heat_released - self.indicated_power - self.heat_to_coolant, 0.0)
        self.exhaust_flow = self.air_flow + self.fuel_flow
        self.t_exhaust = self.t_manifold + self.exhaust_heat / (self.exhaust_flow * inp.exhaust_cp)
        self.compressor_power = self.air_flow * gas.CP_AIR * (self.t_compressor_out - inp.ambient_temp)


def _turbine_closed(inp: EngineInputs, c: _Charge, p_out: np.ndarray):
    """Turbine inlet pressure and power with the wastegate shut (all exhaust through the turbine)."""
    p_in = gas.upstream_pressure_for_flow(c.exhaust_flow, inp.turbine_area, c.t_exhaust, p_out, inp.exhaust_gamma)
    power = gas.turbine_power(c.exhaust_flow, inp.exhaust_cp, c.t_exhaust, inp.eta_turbine, p_in / p_out, inp.exhaust_gamma)
    return p_in, power


def run(inp: EngineInputs, rpm: np.ndarray, iterations: int = 30) -> dict[str, np.ndarray]:
    """Evaluate the full-load curve. Returns SI arrays shaped (S, R)."""
    xp = ns(inp.bore)
    rpm = xp.asarray(rpm, dtype=float)[None, :]
    shape = np.broadcast_shapes(inp.bore.shape, rpm.shape)
    ve = xp.broadcast_to(volumetric_efficiency(inp, rpm), shape)
    p_out = inp.ambient_pressure + inp.exhaust_backpressure
    target = xp.broadcast_to(inp.boost_target, shape)

    def surplus(boost):
        c = _Charge(inp, rpm, ve, boost)
        _, w_turbine = _turbine_closed(inp, c, p_out)
        return w_turbine * inp.eta_mechanical - c.compressor_power

    reachable = surplus(target) >= 0.0
    lo = xp.zeros(shape)
    hi = target.copy()
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        ok = surplus(mid) >= 0.0
        lo = xp.where(ok, mid, lo)
        hi = xp.where(ok, hi, mid)
    boost = xp.where(reachable, target, lo)

    c = _Charge(inp, rpm, ve, boost)
    p3_closed, _ = _turbine_closed(inp, c, p_out)
    required = c.compressor_power / inp.eta_mechanical

    # Wastegate open: find the turbine inlet pressure at which the turbine (passing only
    # part of the exhaust) makes exactly the power the compressor needs.
    lo_p = xp.broadcast_to(p_out, shape).astype(float).copy()
    hi_p = p3_closed.copy()
    for _ in range(iterations):
        mid = 0.5 * (lo_p + hi_p)
        flow = xp.minimum(c.exhaust_flow, gas.nozzle_mass_flow(inp.turbine_area, mid, c.t_exhaust, p_out, inp.exhaust_gamma))
        w = gas.turbine_power(flow, inp.exhaust_cp, c.t_exhaust, inp.eta_turbine, mid / p_out, inp.exhaust_gamma)
        short = w < required
        lo_p = xp.where(short, mid, lo_p)
        hi_p = xp.where(short, hi_p, mid)
    p3 = xp.where(reachable, 0.5 * (lo_p + hi_p), p3_closed)
    turbine_flow = xp.minimum(c.exhaust_flow, gas.nozzle_mass_flow(inp.turbine_area, p3, c.t_exhaust, p_out, inp.exhaust_gamma))
    turbine_power = gas.turbine_power(turbine_flow, inp.exhaust_cp, c.t_exhaust, inp.eta_turbine, p3 / p_out, inp.exhaust_gamma)

    cycles_per_s = rpm / 120.0
    vd = inp.displacement
    imep = c.indicated_power / (vd * cycles_per_s)
    pmep = c.p_manifold - p3
    krpm = rpm / 1000.0
    fmep = inp.friction_a + inp.friction_b * krpm + inp.friction_c * krpm**2
    bmep = imep + pmep - fmep
    torque = bmep * vd / (4.0 * xp.pi)
    omega = 2.0 * xp.pi * rpm / 60.0
    power = torque * omega
    fuel_power = c.fuel_flow * inp.fuel_lhv
    bsfc = xp.where(power > 0, c.fuel_flow / xp.where(power > 0, power, 1.0) * 3.6e9, xp.nan)  # g/kWh
    injector_capacity = inp.injector_count * inp.injector_flow * inp.fuel_density  # kg/s
    peak_pressure = c.p_manifold * xp.power(inp.compression_ratio, inp.polytropic_n) * inp.pressure_rise_ratio
    corrected_flow = c.air_flow * xp.sqrt(inp.ambient_temp / gas.T_REF_CORRECTED) / (inp.ambient_pressure / gas.P_REF_CORRECTED)

    return {
        "rpm": xp.broadcast_to(rpm, shape),
        "ve": ve,
        "boost": boost,
        "boost_limited": (~reachable).astype(float),
        "manifold_pressure": c.p_manifold,
        "pressure_ratio": c.pressure_ratio,
        "compressor_outlet_temp": c.t_compressor_out,
        "charge_temp": c.t_manifold,
        "air_flow": c.air_flow,
        "corrected_air_flow": corrected_flow,
        "compressor_power": c.compressor_power,
        "turbine_power": turbine_power,
        "exhaust_manifold_pressure": p3,
        "egt": c.t_exhaust,
        "wastegate_fraction": 1.0 - turbine_flow / c.exhaust_flow,
        "fuel_flow": c.fuel_flow,
        "injector_duty": c.fuel_flow / injector_capacity,
        "imep": imep,
        "pmep": pmep,
        "fmep": xp.broadcast_to(fmep, shape),
        "bmep": bmep,
        "torque": torque,
        "power": power,
        "bsfc": bsfc,
        "brake_efficiency": power / fuel_power,
        "peak_pressure": peak_pressure,
        "heat_released": c.heat_released,
        "heat_to_coolant": c.heat_to_coolant,
        "exhaust_heat": c.exhaust_heat,
        "piston_speed": xp.broadcast_to(2.0 * inp.stroke * rpm / 60.0, shape),
    }


# Conversions from the SI arrays above to each channel's display unit.
DISPLAY = {
    "boost": lambda v: v / 1e5,
    "manifold_pressure": lambda v: v / 1e3,
    "exhaust_manifold_pressure": lambda v: v / 1e3,
    "compressor_outlet_temp": lambda v: v - 273.15,
    "charge_temp": lambda v: v - 273.15,
    "egt": lambda v: v - 273.15,
    "air_flow": lambda v: v * 1e3,
    "fuel_flow": lambda v: v * 1e3,
    "compressor_power": lambda v: v / 1e3,
    "turbine_power": lambda v: v / 1e3,
    "power": lambda v: v / 1e3,
    "heat_released": lambda v: v / 1e3,
    "heat_to_coolant": lambda v: v / 1e3,
    "exhaust_heat": lambda v: v / 1e3,
    "imep": lambda v: v / 1e5,
    "pmep": lambda v: v / 1e5,
    "fmep": lambda v: v / 1e5,
    "bmep": lambda v: v / 1e5,
    "peak_pressure": lambda v: v / 1e5,
}


def to_display(channel: str, values: np.ndarray) -> np.ndarray:
    fn = DISPLAY.get(channel)
    return fn(values) if fn else values
