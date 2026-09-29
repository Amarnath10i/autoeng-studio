"""Learning from real engines (spec §20, §35): community priors from shared calibrations.

Every calibration a user shares adds one real engine's fitted parameters. For a
new design the platform finds similar engines (kernel-weighted by displacement,
compression ratio, boost, bore/stroke ratio and cylinder count) and suggests
parameter values with an honest spread:

    mean   = Σ wᵢ xᵢ / Σ wᵢ
    spread = √(between-engine variance + mean fit variance)
    n_eff  = (Σ wᵢ)² / Σ wᵢ²      (effective number of similar engines)

Suggestions need n_eff ≥ MIN_EFFECTIVE. They are labelled `community` and applied
only when the user accepts them.

Next step, once enough data exists: a hybrid model that learns the physics model's
systematic residuals against measurements (a discrepancy model with its own
validated error), rather than replacing the physics.
"""

from __future__ import annotations

import math

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from autoeng.analysis.calibration import CALIBRATABLE
from autoeng.core.params import Source
from autoeng.db.models import CalibrationRecord, User
from autoeng.domain.engine_design import PARAM_SPECS, EngineDesign

MIN_EFFECTIVE = 3.0
# Similarity length scales: one "unit" of difference per descriptor.
SCALES = {"displacement_l": 0.5, "compression_ratio": 1.0, "boost_bar": 0.5, "bore_stroke": 0.15, "cylinders": 2.0}


def descriptors(design: EngineDesign) -> dict:
    e = design.engine
    disp = e.cylinders * math.pi / 4 * (e.bore.value / 1000) ** 2 * (e.stroke.value / 1000) * 1000
    return {
        "displacement_l": round(disp, 3),
        "cylinders": e.cylinders,
        "compression_ratio": e.compression_ratio.value,
        "bore_stroke": round(e.bore.value / e.stroke.value, 3),
        "boost_bar": design.turbo.boost_target.value,
        "fuel_id": design.fuel.fuel_id,
    }


def share(db: Session, user: User, project_id: str | None, design: EngineDesign, calibration: dict,
          measurement_kind: str = "dyno") -> CalibrationRecord:
    params = {p["path"]: {"value": p["after"], "ci95": p["ci95"]} for p in calibration["parameters"]}
    rec = CalibrationRecord(
        owner_id=user.id, project_id=project_id, descriptors=descriptors(design), parameters=params,
        quality={"torque_rmse": calibration["torque_rmse_after"], "points": len(calibration["curves"]["rpm"]),
                 "kind": measurement_kind},
    )
    db.add(rec)
    db.commit()
    return rec


def _weight(a: dict, b: dict) -> float:
    d2 = sum(((a[k] - b[k]) / s) ** 2 for k, s in SCALES.items())
    same_fuel = a.get("fuel_id") == b.get("fuel_id")
    return math.exp(-0.5 * d2) * (1.0 if same_fuel else 0.3)


def suggest(db: Session, design: EngineDesign) -> dict:
    target = descriptors(design)
    records = list(db.scalars(select(CalibrationRecord)))
    suggestions = []
    for path in CALIBRATABLE:
        rows = [(r, r.parameters[path]) for r in records if path in r.parameters]
        if not rows:
            continue
        w = np.array([_weight(target, r.descriptors) for r, _ in rows])
        if w.sum() <= 1e-9:
            continue
        x = np.array([p["value"] for _, p in rows])
        fit_var = np.array([(p.get("ci95", 0.0) / 1.96) ** 2 for _, p in rows])
        n_eff = float(w.sum() ** 2 / (w**2).sum())
        if n_eff < MIN_EFFECTIVE:
            continue
        mean = float((w * x).sum() / w.sum())
        between = float((w * (x - mean) ** 2).sum() / w.sum())
        spread = math.sqrt(between + float((w * fit_var).sum() / w.sum()))
        spec = PARAM_SPECS[path]
        suggestions.append({
            "path": path,
            "label": spec.label,
            "unit": spec.unit,
            "value": mean,
            "tol": 1.96 * spread,
            "source": Source.COMMUNITY.value,
            "n_records": len(rows),
            "n_effective": round(n_eff, 1),
            "ref": f"Learned from {len(rows)} shared calibrations (≈{n_eff:.0f} similar engines)",
        })
    return {
        "descriptors": target,
        "total_records": len(records),
        "min_effective": MIN_EFFECTIVE,
        "suggestions": suggestions,
        "note": "Values learned from other users' real engines with similar size, compression, boost and fuel. "
                "They are better starting points than generic estimates, not measurements of your engine.",
    }
