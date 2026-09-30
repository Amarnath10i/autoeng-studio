"""Engine layout, crank phasing, balance and firing order (fidelity level 1, exact kinematics).

Every cylinder is placed by its layout: position along the crankshaft, bank angle
(the direction of its axis in the plane perpendicular to the crank) and the
angle of its crankpin. The reciprocating inertia force of each piston along its
axis is

    F = m·r·ω² · [cos ψ + λ·cos 2ψ],   ψ = pin angle − bank angle,  λ = r/L

(primary and secondary orders; higher orders are small and omitted). Summing
these vectors, and their moments about the crank centre, over a full revolution
gives the engine's free shaking forces and rocking couples. A primary couple of
constant magnitude that rotates with the crank can be cancelled by crankshaft
counterweights; the model reports that separately. Rotating masses (crankpins,
big ends) are assumed balanced by counterweights.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MODEL_ID = "structure.engine_balance"
MODEL_VERSION = "1.0.0"

LAYOUTS = ("inline", "v", "w", "flat")
CRANKS = ("standard", "flat_plane", "cross_plane")

ASSUMPTIONS = [
    "Reciprocating forces to second order (cos ψ + λ cos 2ψ); fourth and higher orders are omitted.",
    "Rotating masses are fully counterweighted; a primary couple that rotates at constant magnitude is reported as "
    "counterweight-balanceable.",
    "Cylinder bore spacing 1.25 × bore; V-engine banks are staggered by one rod big-end width (0.35 × bore); boxer "
    "banks by half a bore spacing.",
    "W layouts are modelled as four staggered banks (two narrow 15° pairs at ± half the main bank angle).",
    "Flat engines up to six cylinders are boxers (one pin per cylinder); eight or more are 180° V engines with shared pins.",
    "Firing intervals assume each crank position fires once per 720° cycle, alternating between cylinders that share it.",
]

# Crankpin angles (degrees) along one bank, for common cylinder counts.
INLINE_THROWS: dict[int, list[float]] = {
    1: [0],
    2: [0, 180],
    3: [0, 240, 120],
    4: [0, 180, 180, 0],
    5: [0, 144, 288, 72, 216],
    6: [0, 240, 120, 120, 240, 0],
    8: [0, 180, 90, 270, 270, 90, 180, 0],
}
CROSS_PLANE_4 = [0, 90, 270, 180]


def validate_layout(layout: str, cylinders: int) -> str | None:
    if layout not in LAYOUTS:
        return f"layout must be one of {', '.join(LAYOUTS)}"
    if layout == "inline" and cylinders not in INLINE_THROWS:
        return "inline engines need 1-6 or 8 cylinders"
    if layout in ("v", "flat") and (cylinders % 2 or cylinders < 2 or cylinders // 2 not in INLINE_THROWS):
        return f"{layout.upper() if layout == 'v' else 'flat'} engines need an even count of 2-12 or 16 cylinders"
    if layout == "w" and (cylinders % 4 or cylinders // 4 not in INLINE_THROWS or cylinders < 8):
        return "W engines need 8, 12 or 16 cylinders"
    return None


@dataclass
class Cylinder:
    index: int
    bank: int
    x: float  # m along the crank from its centre
    bank_angle: float  # deg from vertical (positive to the right)
    pin_angle: float  # deg


def arrangement(layout: str, cylinders: int, bank_angle: float, crank: str, bore: float) -> list[Cylinder]:
    """Cylinder positions, bank angles and crankpin angles for a layout (bore in m)."""
    err = validate_layout(layout, cylinders)
    if err:
        raise ValueError(err)
    pitch = 1.25 * bore
    cyls: list[Cylinder] = []

    def bank(n: int, angle: float, throws: list[float], x0: float, bank_id: int):
        for j in range(n):
            cyls.append(Cylinder(len(cyls), bank_id, x0 + j * pitch, angle, throws[j] % 360))

    if layout == "inline":
        bank(cylinders, 0.0, INLINE_THROWS[cylinders], 0.0, 0)
    elif layout == "v":
        n = cylinders // 2
        throws = CROSS_PLANE_4 if (n == 4 and crank != "flat_plane") else INLINE_THROWS[n]
        # Split crankpins make a V fire evenly at any bank angle: offset = bank angle − 720°/cylinders
        # (60° for a 60° V6, 30° for a 90° V6, 18° for a 90° V10, none for a 90° V8). Twins share one pin.
        split = 0.0 if cylinders <= 2 else ((bank_angle - 720 / cylinders + 180) % 360) - 180
        bank(n, -bank_angle / 2, throws, 0.0, 0)
        bank(n, bank_angle / 2, [t + split for t in throws], 0.35 * bore, 1)
    elif layout == "flat":
        n = cylinders // 2
        throws = INLINE_THROWS[n]
        if n <= 3:  # boxer: every cylinder has its own pin, opposed pins 180° apart
            bank(n, -90.0, throws, 0.0, 0)
            bank(n, 90.0, [t + 180 for t in throws], pitch / 2, 1)
        else:  # larger flat engines are built as 180° V engines with shared pins
            bank(n, -90.0, throws, 0.0, 0)
            bank(n, 90.0, throws, 0.35 * bore, 1)
    else:  # w: two narrow-angle (15°) "VR" banks set in a V, like production W12 and W16 engines
        n = cylinders // 2
        throws = INLINE_THROWS[n]
        split = ((bank_angle - 720 / cylinders + 180) % 360) - 180
        vr_pitch = 0.65 * pitch  # VR banks nest their cylinders in a zig-zag, so they are short
        for side, offset, x0 in ((-1, 0.0, 0.0), (1, split, 0.35 * bore)):
            for j in range(n):
                tilt = 7.5 if j % 2 else -7.5
                angle = side * bank_angle / 2 + tilt
                # The pin is advanced by the tilt so each cylinder keeps its V-engine firing point.
                cyls.append(Cylinder(len(cyls), (side > 0) * 2 + j % 2, x0 + j * vr_pitch, angle,
                                     (throws[j] + offset + tilt) % 360))
    centre = np.mean([c.x for c in cyls])
    for c in cyls:
        c.x -= centre
    return cyls


def firing_intervals(cyls: list[Cylinder]) -> list[float]:
    """Crank-angle gaps between successive firings over the 720° four-stroke cycle.

    Each cylinder reaches top dead centre once per revolution and may fire on either
    of the two (the camshaft decides). The choice is made as an optimal assignment to
    an evenly spaced firing grid, which is how firing orders are designed.
    """
    from scipy.optimize import linear_sum_assignment

    n = len(cyls)
    tdc = np.array([(c.pin_angle - c.bank_angle) % 360 for c in cyls])
    options = np.stack([tdc, tdc + 360], axis=1)  # (n, 2)
    grid = tdc.min() + np.arange(n) * 720 / n

    def circ(a, b):
        d = np.abs(a - b) % 720
        return np.minimum(d, 720 - d)

    dist = circ(options[:, :, None], grid[None, None, :])  # (n, 2, n)
    rows, cols = linear_sum_assignment(dist.min(axis=1))
    events = np.sort([options[i, int(np.argmin(dist[i, :, k]))] for i, k in zip(rows, cols, strict=True)])
    gaps = np.diff(np.append(events, events[0] + 720))
    return [float(g) for g in gaps]


def shaking(cyls: list[Cylinder], lam: float, samples: int = 720) -> dict:
    """Free forces and couples per unit m·r·ω² over one revolution, split by order."""
    theta = np.linspace(0, 2 * np.pi, samples, endpoint=False)
    out = {}
    for order in (1, 2):
        f = np.zeros((samples, 2))  # lateral (y), vertical (z)
        m = np.zeros((samples, 2))  # about vertical axis (yaw, from lateral forces) and lateral axis (pitch)
        for c in cyls:
            beta = np.radians(c.bank_angle)
            psi = theta + np.radians(c.pin_angle) - beta
            mag = np.cos(psi) if order == 1 else lam * np.cos(2 * psi)
            fy, fz = mag * np.sin(beta), mag * np.cos(beta)
            f[:, 0] += fy
            f[:, 1] += fz
            m[:, 0] += c.x * fy  # yaw couple
            m[:, 1] += c.x * fz  # pitch couple
        fmag = np.hypot(f[:, 0], f[:, 1])
        mmag = np.hypot(m[:, 0], m[:, 1])
        m_max = float(mmag.max())
        f_max = float(fmag.max())
        rotating = bool(m_max > 1e-9 and mmag.min() / m_max > 0.95)
        out[order] = {
            "force": f_max,
            "force_rotating": bool(f_max > 1e-9 and fmag.min() / f_max > 0.95),
            "couple": m_max,  # m (multiply by m·r·ω² for N·m)
            "couple_rotating": rotating,
            "force_trace": f,
            "couple_trace": m,
        }
    return out


def analyse(
    layout: str,
    cylinders: int,
    bank_angle: float,
    crank: str,
    bore: float,
    stroke: float,
    rod_length: float,
    recip_mass: float,
    rpm: float,
) -> dict:
    """Balance summary at a given engine speed. SI inputs (bore/stroke/rod in m, mass in kg)."""
    cyls = arrangement(layout, cylinders, bank_angle, crank, bore)
    r = stroke / 2
    lam = r / rod_length
    omega = 2 * np.pi * rpm / 60
    scale = recip_mass * r * omega**2  # N
    s = shaking(cyls, lam)
    gaps = firing_intervals(cyls)
    even = max(gaps) - min(gaps) < 1.0
    tol_f = 0.02 * scale  # 2 % of one cylinder's primary force counts as balanced
    tol_m = 0.02 * scale * 1.25 * bore

    def verdict(order: int) -> dict:
        f = s[order]["force"] * scale
        m = s[order]["couple"] * scale
        return {
            "force_n": f,
            "couple_nm": m,
            "force_balanced": f < tol_f,
            "couple_balanced": m < tol_m,
            "force_counterweightable": order == 1 and s[order]["force_rotating"],
            "couple_counterweightable": order == 1 and s[order]["couple_rotating"],
        }

    primary, secondary = verdict(1), verdict(2)
    theta = np.linspace(0, 360, 72, endpoint=False)
    idx = np.linspace(0, len(s[1]["force_trace"]) - 1, 72).astype(int)
    summary = []
    for name, v in (("Primary", primary), ("Secondary", secondary)):
        if v["force_balanced"]:
            f = "balanced"
        elif v["force_counterweightable"]:
            f = "rotating force (cancelled by counterweights)"
        else:
            f = "free force"
        if v["couple_balanced"]:
            c = "no couple"
        elif v["couple_counterweightable"]:
            c = "rotating couple (cancelled by counterweights)"
        else:
            c = "rocking couple"
        summary.append(f"{name}: {f}, {c}")
    return {
        "layout": layout,
        "cylinders": [c.__dict__ for c in cyls],
        "firing_intervals_deg": gaps,
        "even_firing": even,
        "rod_ratio": lam,
        "unit_force_n": scale,
        "primary": primary,
        "secondary": secondary,
        "summary": summary,
        "trace": {
            "crank_deg": theta.tolist(),
            "primary_vertical_n": (s[1]["force_trace"][idx, 1] * scale).round(1).tolist(),
            "primary_lateral_n": (s[1]["force_trace"][idx, 0] * scale).round(1).tolist(),
            "secondary_vertical_n": (s[2]["force_trace"][idx, 1] * scale).round(1).tolist(),
            "secondary_lateral_n": (s[2]["force_trace"][idx, 0] * scale).round(1).tolist(),
        },
        "package_mm": package(layout, cylinders, bank_angle, bore, stroke, rod_length),
        "model": {"id": MODEL_ID, "version": MODEL_VERSION},
        "assumptions": ASSUMPTIONS,
    }


def package(layout: str, cylinders: int, bank_angle: float, bore: float, stroke: float, rod: float) -> dict:
    """Rough block envelope (mm): length along the crank, width, height above the crank centre."""
    pitch = 1.25 * bore
    deck = stroke / 2 + rod + 0.45 * bore  # crank centre to deck
    head = 1.1 * bore
    per_bank = {"inline": cylinders, "v": cylinders // 2, "flat": cylinders // 2, "w": cylinders // 4}[layout]
    length = per_bank * pitch + (pitch / 2 if layout in ("flat", "w") else 0.35 * bore) + 0.3 * bore
    if layout == "inline":
        width, height = 1.6 * bore, deck + head
    elif layout == "flat":
        width, height = 2 * (deck + head), 1.4 * bore
    else:
        a = np.radians(bank_angle / 2 + (7.5 if layout == "w" else 0))
        width = 2 * (deck + head) * np.sin(a) + 1.6 * bore
        height = (deck + head) * np.cos(np.radians(bank_angle / 2)) + 0.2 * bore
    return {"length": round(length * 1000), "width": round(width * 1000), "height_above_crank": round(height * 1000)}
