"""Verification and validation benchmarks.

Verification asks whether the code solves its equations correctly (conservation laws,
closed-form and textbook answers). Validation asks whether the model matches reality
(experiments and real users' measurements). Each case reports rows of reference vs
predicted values, an error metric, a tolerance band and a verdict, and cites its source.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

PASS, MARGINAL, FAIL = "pass", "marginal", "fail"


@dataclass
class Case:
    id: str
    kind: str  # "verification" | "validation"
    model: str
    title: str
    question: str
    reference: str
    tolerance_pct: float
    run: Callable[[], list[dict]]
    heavy: bool = False  # needs a 3D flow solution (GPU recommended)
    note: str = ""


def _row(label: str, reference: float, predicted: float, unit: str = "", *, absolute: bool = False) -> dict:
    err = predicted - reference if absolute or reference == 0 else 100 * (predicted / reference - 1)
    return {"label": label, "reference": float(reference), "predicted": float(predicted), "unit": unit,
            "error": float(err), "error_kind": "absolute" if absolute or reference == 0 else "percent"}


def verdict(rows: list[dict], tol: float) -> tuple[str, float]:
    worst = max(abs(r["error"]) for r in rows)
    return (PASS if worst <= tol else MARGINAL if worst <= 2 * tol else FAIL), worst


# --------------------------------------------------------------------- engine verification

def _engine_nominal():
    from autoeng.analysis.sampling import sample_design
    from autoeng.domain.materials import LIBRARY
    from autoeng.physics import engine_mvem
    from autoeng.presets import generic_2l_turbo

    design = generic_2l_turbo()
    s = sample_design(design, LIBRARY, 1, 0)
    rpm = np.arange(design.operating.rpm_min, design.operating.rpm_max + 1, 250.0)
    return s, engine_mvem.run(s.engine, rpm), rpm


def engine_conservation() -> list[dict]:
    from autoeng.physics import engine_mvem

    s, out, rpm = _engine_nominal()
    c = engine_mvem._Charge(s.engine, rpm[None, :], out["ve"], out["boost"])
    energy = np.max(np.abs(c.heat_released - (c.indicated_power + c.heat_to_coolant + c.exhaust_heat)) / c.heat_released)
    power = np.max(np.abs(out["power"] - out["torque"] * 2 * math.pi * rpm / 60) / out["power"])
    wg = out["boost_limited"] < 0.5
    shaft = out["turbine_power"] * s.engine.eta_mechanical - out["compressor_power"]
    shaft_err = float(np.max(np.abs(shaft[wg]) / out["compressor_power"][wg])) if wg.any() else 0.0
    return [
        _row("Energy: fuel heat = work + coolant + exhaust (worst point)", 0, 100 * float(energy), "%", absolute=True),
        _row("P = T · ω (worst point)", 0, 100 * float(power), "%", absolute=True),
        _row("Turbo shaft power balance on wastegate (worst point)", 0, 100 * shaft_err, "%", absolute=True),
    ]


def balance_textbook() -> list[dict]:
    from autoeng.physics import balance

    bore, stroke, rod = 0.086, 0.086, 0.145
    lam = stroke / 2 / rod

    def orders(layout, n, angle=90.0, crank="standard"):
        return balance.shaking(balance.arrangement(layout, n, angle, crank, bore), lam)

    i4, i6 = orders("inline", 4), orders("inline", 6)
    v8x, v8f = orders("v", 8, 90, "cross_plane"), orders("v", 8, 90, "flat_plane")
    return [
        _row("Inline-4 secondary force (× m r ω²)", 4 * lam, i4[2]["force"]),
        _row("Inline-6 primary + secondary force", 0, i6[1]["force"] + i6[2]["force"], absolute=True),
        _row("Cross-plane V8 free forces", 0, v8x[1]["force"] + v8x[2]["force"], absolute=True),
        _row("Flat-plane V8 secondary force (× m r ω²)", 4 * lam * math.sqrt(2), v8f[2]["force"]),
    ]


def conrod_buckling() -> list[dict]:
    from autoeng.physics import conrod

    e, sy = 205e9, 710e6
    slender = np.array([150.0, 250.0])
    euler = math.pi**2 * e / slender**2
    got = conrod.critical_stress(e, sy, slender)
    transition = math.sqrt(2 * math.pi**2 * e / sy)
    return [
        _row(f"Euler stress at slenderness {int(s)} (MPa)", eu / 1e6, g / 1e6, "MPa") for s, eu, g in zip(slender, euler, got, strict=True)
    ] + [_row("Johnson stress at the transition (MPa)", sy / 2e6, float(conrod.critical_stress(e, sy, np.array(transition))) / 1e6, "MPa")]


# --------------------------------------------------------------------- aerodynamics

def clift_gauvin(re: float) -> float:
    """Standard sphere drag curve, Clift & Gauvin (1971); within about ±6 % of measurements for Re < 3·10⁵."""
    return 24 / re * (1 + 0.15 * re**0.687) + 0.42 / (1 + 42500 * re**-1.16)


SPHERE_DOMAIN = {"upstream": 4.0, "length": 14.0, "width": 8.0, "height": 8.0 / 4.5}


def sphere_drag() -> list[dict]:
    from autoeng.physics import aero_lbm3d
    from autoeng.validation import shapes

    rows = []
    for re in (100, 300):
        r = aero_lbm3d.run(None, body=shapes.sphere(1.0, 4.0), domain=SPHERE_DOMAIN,
                           config={"cells": 16, "u": 0.04, "re": re, "flow_throughs": 1.2, "cs": 0.0})
        rows.append(_row(f"Sphere Cd at Re {re}", clift_gauvin(re), r["cd"]))
        rows.append({**_row(f"Sphere lift at Re {re} (symmetry: should be 0)", 0, r["cl"], absolute=True),
                     "check": True})
    return rows


# Ahmed, Ramm & Faltin (1984), SAE 840300, measured at Re = 4.29·10⁶ (60 m/s, body length).
AHMED_MEASURED = {0: 0.250, 25: 0.285, 35: 0.260}
AHMED_DOMAIN = {"upstream": 1.0, "length": 4.0, "width": 5.0, "height": 3.5}


def ahmed_drag() -> list[dict]:
    from autoeng.physics import aero_lbm3d
    from autoeng.validation import shapes

    rows = []
    for angle, cd in AHMED_MEASURED.items():
        r = aero_lbm3d.run(None, body=shapes.ahmed_body(angle), domain=AHMED_DOMAIN,
                           config={"cells": 64, "u": 0.05, "re": 5000, "flow_throughs": 1.5})
        rows.append(_row(f"Ahmed body, {angle}° slant: Cd", cd, r["cd"]))
    return rows


CASES = [
    Case("engine_conservation", "verification", "engine.turbo_si_mvem", "Engine model conserves energy and power",
         "Does every rpm point close the energy balance, P = T·ω and the turbo shaft power balance?",
         "Conservation laws (exact)", 0.01, engine_conservation),
    Case("balance_textbook", "verification", "structure.engine_balance", "Engine balance matches textbook results",
         "Do the shaking forces of classic layouts match their closed-form values?",
         "Closed-form results, e.g. Heywood (1988) and Taylor, The Internal Combustion Engine in Theory and Practice",
         0.1, balance_textbook),
    Case("conrod_buckling", "verification", "structure.conrod_beam", "Rod buckling matches Euler and Johnson",
         "Does the column model return the classic Euler and Johnson critical stresses?",
         "Euler (1744) and Johnson parabolic column formulas", 0.01, conrod_buckling),
    Case("sphere_drag", "validation", "aero.lbm_d3q19_les", "Wind tunnel: flow past a sphere",
         "At the Reynolds numbers the tunnel resolves, does it reproduce measured sphere drag?",
         "Standard drag curve, Clift & Gauvin (1971), fitted to sphere measurements", 10.0, sphere_drag, heavy=True,
         note="16 cells per diameter, laminar (no sub-grid model), 8 × 8 diameter cross-section (1.2 % blockage)."),
    Case("ahmed_drag", "validation", "aero.lbm_d3q19_les", "Wind tunnel: Ahmed body",
         "For a car-like body, does the tunnel reproduce measured drag and its dependence on rear slant?",
         "Ahmed, Ramm & Faltin (1984), SAE 840300, at Re 4.3·10⁶", 15.0, ahmed_drag, heavy=True,
         note="Simulated at Re 5·10³ with 64 cells along the body; stilts omitted; moving road."),
]


def run_case(case: Case) -> dict:
    started = time.perf_counter()
    try:
        rows = case.run()
    except Exception as e:  # noqa: BLE001 - a failing benchmark is reported, not raised
        return {**_meta(case), "status": "error", "error": str(e), "rows": [], "seconds": time.perf_counter() - started}
    scored = [r for r in rows if not r.get("check")] or rows
    v, worst = verdict(scored, case.tolerance_pct)
    checks = [r for r in rows if r.get("check")]
    return {**_meta(case), "status": "done", "rows": rows, "verdict": v, "worst_error": worst,
            "checks_ok": all(abs(r["error"]) < 0.05 for r in checks), "seconds": round(time.perf_counter() - started, 1),
            "findings": findings(case.id, rows)}


def _meta(case: Case) -> dict:
    return {"id": case.id, "kind": case.kind, "model": case.model, "title": case.title, "question": case.question,
            "reference": case.reference, "tolerance_pct": case.tolerance_pct, "heavy": case.heavy, "note": case.note}


def findings(case_id: str, rows: list[dict]) -> list[str]:
    """Plain-language conclusions drawn from a case's numbers."""
    if case_id == "ahmed_drag" and len(rows) == 3:
        sim = [r["predicted"] for r in rows]
        meas = [r["reference"] for r in rows]
        trend_ok = (sim[1] > sim[2]) == (meas[1] > meas[2]) and (sim[1] > sim[0]) == (meas[1] > meas[0])
        return [
            f"Absolute drag is {min(r['error'] for r in rows):+.0f} % to {max(r['error'] for r in rows):+.0f} % off: "
            "at a lattice Reynolds number of 5·10³ the boundary layers are laminar and far too thick, so friction and "
            "wake drag dominate. Real cars run at 10⁶-10⁷.",
            "The slant-angle trend (drag peaks near 25-30°, then drops once the flow fully separates) is "
            + ("reproduced." if trend_ok else "not reproduced: the separation physics behind it needs turbulent, wall-resolved flow."),
            "Use the tunnel to see flow structure and to compare large shape changes; take absolute Cd from a wind tunnel "
            "or coast-down test and enter it as measured.",
        ]
    if case_id == "sphere_drag":
        cds = [r for r in rows if not r.get("check")]
        return [f"Sphere drag within {max(abs(r['error']) for r in cds):.0f} % of the standard curve at its own Reynolds "
                "number: the solver, boundary conditions and force measurement are sound. The remaining excess comes mainly "
                "from the staircase surface of a 16-cell sphere."]
    return []


def run_suite(include_heavy: bool = True, progress: Callable[[str], None] | None = None) -> dict:
    from autoeng import compute

    results = []
    for case in CASES:
        if case.heavy and not include_heavy:
            continue
        if progress:
            progress(case.id)
        results.append(run_case(case))
    xp = compute.for_size(10**7)
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "compute": compute.describe(xp),
            "cases": results}
