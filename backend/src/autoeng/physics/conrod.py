"""Connecting-rod beam checks (fidelity level 1): geometry + material → stress → safety factors.

Loads per rpm point:
  * Firing TDC: gas force on the piston minus reciprocating inertia → compression.
  * Exhaust TDC: reciprocating inertia alone → tension. Also checked at an
    overspeed load case above redline.
Checks on the minimum I-beam section:
  * Buckling (Johnson parabola / Euler), pinned in the plane of rotation, ~fixed
    out of plane.
  * Tensile yield.
  * Fatigue, with the modified Goodman criterion on the cycle between those two loads.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from autoeng.compute import ns

MODEL_ID = "structure.conrod_beam"
MODEL_VERSION = "1.0.0"
FIDELITY_LEVEL = 1

ASSUMPTIONS = [
    "Stresses are evaluated on the minimum I-beam section only; the big end, small end, bolts and the pin bores are not checked.",
    "Peak gas force is applied at TDC together with the maximum inertia force. In reality peak pressure occurs ~10-20° after TDC.",
    "Reciprocating mass = piston group + small-end share of the rod mass; rod mass = material density × rod volume.",
    "Buckling length = centre-to-centre length; effective length factor 1.0 in the plane of rotation, 0.5 out of plane.",
    "Fatigue uses modified Goodman: fatigue strength × modification factor as the endurance limit; "
    "a compressive mean stress is treated conservatively (safety factor = Se/σa).",
    "Material properties at room temperature; no stress concentrations beyond the modification factor.",
]


@dataclass
class RodSection:
    area: np.ndarray  # m²
    inertia_in_plane: np.ndarray  # m⁴, bending that buckles in the plane of rotation
    inertia_out_of_plane: np.ndarray  # m⁴


def i_section(height, width, flange_t, web_t) -> RodSection:
    web_h = height - 2.0 * flange_t
    area = 2.0 * width * flange_t + web_h * web_t
    i_in = (width * height**3 - (width - web_t) * web_h**3) / 12.0
    i_out = 2.0 * flange_t * width**3 / 12.0 + web_h * web_t**3 / 12.0
    return RodSection(area, i_in, i_out)


def critical_stress(e_modulus, yield_strength, slenderness):
    """Johnson parabola for short columns, Euler beyond the transition slenderness."""
    xp = ns(slenderness)
    transition = xp.sqrt(2.0 * xp.pi**2 * e_modulus / yield_strength)
    euler = xp.pi**2 * e_modulus / xp.maximum(slenderness, 1e-9) ** 2
    johnson = yield_strength - (yield_strength * slenderness / (2.0 * xp.pi)) ** 2 / e_modulus
    return xp.where(slenderness < transition, johnson, euler)


def inertia_force(recip_mass, crank_radius, rod_length, rpm):
    """Peak reciprocating inertia at TDC: m·r·ω²·(1 + r/L)."""
    xp = ns(recip_mass, crank_radius)
    omega = 2.0 * xp.pi * rpm / 60.0
    return recip_mass * crank_radius * omega**2 * (1.0 + crank_radius / rod_length)


def analyse(
    *,
    bore,
    stroke,
    rod_length,
    rpm,
    rpm_max,
    peak_pressure,
    ambient_pressure,
    section: RodSection,
    rod_volume,
    piston_group_mass,
    small_end_fraction,
    overspeed_factor,
    density,
    e_modulus,
    yield_strength,
    ultimate_strength,
    fatigue_strength,
    fatigue_factor,
) -> dict[str, np.ndarray]:
    """All inputs SI. `fatigue_strength` may be None (unknown). Arrays broadcast to (S, R)."""
    xp = ns(bore, peak_pressure)
    radius = stroke / 2.0
    rod_mass = density * rod_volume
    recip_mass = piston_group_mass + small_end_fraction * rod_mass
    piston_area = xp.pi / 4.0 * bore**2
    f_gas = (peak_pressure - ambient_pressure) * piston_area
    f_inertia = inertia_force(recip_mass, radius, rod_length, rpm)
    compressive = xp.maximum(f_gas - f_inertia, 0.0) / section.area
    tensile = f_inertia / section.area
    tensile_overspeed = inertia_force(recip_mass, radius, rod_length, rpm_max * overspeed_factor) / section.area

    r_in = xp.sqrt(section.inertia_in_plane / section.area)
    r_out = xp.sqrt(section.inertia_out_of_plane / section.area)
    sigma_cr = xp.minimum(
        critical_stress(e_modulus, yield_strength, 1.0 * rod_length / r_in),
        critical_stress(e_modulus, yield_strength, 0.5 * rod_length / r_out),
    )

    out = {
        "rod_compressive_stress": compressive,
        "rod_tensile_stress": tensile,
        "rod_tensile_overspeed": tensile_overspeed,
        "rod_critical_stress": sigma_cr,
        "rod_mass": rod_mass,
        "recip_mass": recip_mass,
        "sf_buckling": sigma_cr / xp.maximum(compressive, 1.0),
        "sf_tensile_yield": yield_strength / xp.maximum(xp.maximum(tensile, tensile_overspeed), 1.0),
    }
    if fatigue_strength is not None:
        endurance = fatigue_strength * fatigue_factor
        amplitude = (tensile + compressive) / 2.0
        mean = (tensile - compressive) / 2.0
        goodman = 1.0 / xp.maximum(amplitude / endurance + xp.maximum(mean, 0.0) / ultimate_strength, 1e-12)
        compressive_mean = endurance / xp.maximum(amplitude, 1.0)
        out["sf_fatigue"] = xp.where(mean >= 0.0, goodman, compressive_mean)
    return out
