"""Gas-dynamics building blocks shared by the engine models.

All functions are vectorised, use SI units, and run on NumPy or CuPy arrays.
"""

from __future__ import annotations

from autoeng.compute import ns

# Dry air, treated as an ideal gas at charge-air temperatures.
R_AIR = 287.05  # J/(kg·K)
CP_AIR = 1005.0  # J/(kg·K)
GAMMA_AIR = 1.4

# Exhaust gas constant; exhaust R stays within ~1 % of air for hydrocarbon/alcohol fuels.
R_EXH = 287.0  # J/(kg·K)

T_REF_CORRECTED = 298.15  # K, reference for corrected compressor flow
P_REF_CORRECTED = 101_325.0  # Pa


def compressor_outlet_temp(t_in, pressure_ratio, efficiency):
    """Actual outlet temperature from isentropic efficiency: T2 = T1·(1 + (PR^((γ−1)/γ) − 1)/η)."""
    xp = ns(t_in, pressure_ratio)
    k = (GAMMA_AIR - 1.0) / GAMMA_AIR
    return t_in * (1.0 + (xp.power(pressure_ratio, k) - 1.0) / efficiency)


def critical_pressure_ratio(gamma):
    """Downstream/upstream pressure ratio at which nozzle flow chokes."""
    xp = ns(gamma)
    return xp.power(2.0 / (gamma + 1.0), gamma / (gamma - 1.0))


def flow_function(x, gamma):
    """Isentropic nozzle flow function Ψ(x), x = p_down/p_up.

    Mass flow through an effective area A is ṁ = A·p_up/√(R·T_up)·Ψ(x); below the
    critical ratio the flow is choked and Ψ stays at its maximum.
    """
    xp = ns(x, gamma)
    x = xp.maximum(x, critical_pressure_ratio(gamma))
    inner = 2.0 * gamma / (gamma - 1.0) * (xp.power(x, 2.0 / gamma) - xp.power(x, (gamma + 1.0) / gamma))
    return xp.sqrt(xp.maximum(inner, 0.0))


def nozzle_mass_flow(area, p_up, t_up, p_down, gamma):
    xp = ns(p_up, t_up)
    return area * p_up / xp.sqrt(R_EXH * t_up) * flow_function(p_down / p_up, gamma)


def upstream_pressure_for_flow(mass_flow, area, t_up, p_down, gamma, iterations: int = 32):
    """Invert the nozzle equation: turbine inlet pressure needed to pass `mass_flow`.

    With x = p_down/p_up the condition is Ψ(x)/x = ṁ·√(R·T)/(A·p_down); the left side
    falls monotonically as x rises, so choked cases have a closed form and the rest
    are bisected on [x_crit, 1].
    """
    xp = ns(mass_flow, t_up)
    target = mass_flow * xp.sqrt(R_EXH * t_up) / (area * p_down)
    xc = critical_pressure_ratio(gamma)
    psi_max = flow_function(xc, gamma)
    choked = target >= psi_max / xc
    x_choked = psi_max / xp.maximum(target, 1e-12)

    lo = xp.broadcast_to(xc, target.shape).astype(float).copy()
    hi = xp.ones_like(target)
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        too_little_flow = flow_function(mid, gamma) / mid < target
        hi = xp.where(too_little_flow, mid, hi)
        lo = xp.where(too_little_flow, lo, mid)
    x = xp.where(choked, x_choked, 0.5 * (lo + hi))
    return p_down / x


def turbine_power(mass_flow, cp, t_in, efficiency, expansion_ratio, gamma):
    """Shaft power from expanding `mass_flow` by p_in/p_out = expansion_ratio."""
    xp = ns(mass_flow, expansion_ratio)
    k = (gamma - 1.0) / gamma
    return mass_flow * cp * t_in * efficiency * (1.0 - xp.power(1.0 / expansion_ratio, k))
