"""Field validation: how far the uncalibrated engine model was from real engines users measured and shared."""

from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from autoeng.db.models import CalibrationRecord


def field_report(db: Session) -> dict:
    rows = []
    for rec in db.scalars(select(CalibrationRecord)):
        q, d = rec.quality or {}, rec.descriptors or {}
        mean = q.get("mean_torque")
        if not mean or q.get("torque_rmse_before") is None:
            continue  # shared before this evidence was recorded
        rows.append({
            "cylinders": d.get("cylinders"),
            "displacement_l": d.get("displacement_l"),
            "boost_bar": d.get("boost_bar"),
            "points": q.get("points"),
            "kind": q.get("kind", "dyno"),
            "error_before_pct": 100 * q["torque_rmse_before"] / mean,
            "error_after_pct": 100 * q["torque_rmse"] / mean,
        })
    if not rows:
        return {"engines": 0, "rows": []}
    before = np.array([r["error_before_pct"] for r in rows])
    after = np.array([r["error_after_pct"] for r in rows])
    return {
        "engines": len(rows),
        "median_error_before_pct": float(np.median(before)),
        "p90_error_before_pct": float(np.percentile(before, 90)),
        "median_error_after_pct": float(np.median(after)),
        "rows": sorted(rows, key=lambda r: r["error_before_pct"]),
    }
