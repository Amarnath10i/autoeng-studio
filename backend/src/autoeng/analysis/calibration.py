"""Model calibration against measured data (spec §20): SIMULATION → MEASUREMENT → BETTER SIMULATION.

Selected model parameters are fitted by bounded nonlinear least squares so the
simulated curves match a measured dyno run. The fitted parameters come back as
`calibrated` Params whose tolerance is the fit's 95 % confidence half-width, so
the calibration's own uncertainty flows into every later simulation.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import numpy as np
from pydantic import BaseModel, Field, model_validator
from scipy.optimize import least_squares

from autoeng.analysis.simulate import run_raw
from autoeng.core.params import Param, Source
from autoeng.domain.engine_design import PARAM_SPECS, EngineDesign, get_path
from autoeng.domain.materials import Material

CALIBRATABLE = [
    "combustion.efficiency_ratio",
    "friction.a",
    "friction.b",
    "breathing.ve_peak",
    "breathing.ve_peak_rpm",
    "breathing.ve_falloff",
    "turbo.turbine_flow_area",
    "turbo.compressor_efficiency",
    "turbo.turbine_efficiency",
    "intercooler.effectiveness",
]

TORQUE_SIGMA_REL = 0.01  # residual scale: 1 % of mean measured torque
BOOST_SIGMA = 0.02  # bar


class DynoRun(BaseModel):
    """A measured full-load run. Torque is required; boost is optional but lets spool be calibrated."""

    name: str = "Dyno run"
    rpm: list[float] = Field(min_length=3)
    torque: list[float]  # N·m at the crankshaft (convert wheel figures before upload)
    boost: list[float] | None = None  # bar gauge
    notes: str = ""

    @model_validator(mode="after")
    def _lengths(self) -> DynoRun:
        n = len(self.rpm)
        if len(self.torque) != n or (self.boost is not None and len(self.boost) != n):
            raise ValueError("rpm, torque and boost must have the same length")
        if sorted(self.rpm) != self.rpm:
            raise ValueError("rpm must be ascending")
        return self


def default_parameters(run: DynoRun) -> list[str]:
    params = ["combustion.efficiency_ratio", "friction.a"]
    if run.boost is not None:
        params.append("turbo.turbine_flow_area")
    return params


def _simulate(design: EngineDesign, materials, rpm: np.ndarray, overrides: dict[str, float]):
    raw = run_raw(design, materials, 1, 0, rpm=rpm, overrides=overrides)
    return raw.channels["torque"][0], raw.channels["boost"][0]


def calibrate(
    design: EngineDesign,
    materials: Mapping[str, Material],
    run: DynoRun,
    parameters: list[str] | None = None,
) -> dict:
    parameters = parameters or default_parameters(run)
    unknown = [p for p in parameters if p not in CALIBRATABLE]
    if unknown:
        raise ValueError(f"Not calibratable: {', '.join(unknown)}. Choose from {', '.join(CALIBRATABLE)}")
    if len(parameters) > len(run.rpm):
        raise ValueError("More parameters than measured points")

    rpm = np.asarray(run.rpm, dtype=float)
    torque_meas = np.asarray(run.torque, dtype=float)
    boost_meas = None if run.boost is None else np.asarray(run.boost, dtype=float)
    t_sigma = TORQUE_SIGMA_REL * float(np.mean(np.abs(torque_meas)))

    x0 = np.array([get_path(design, p).value for p in parameters], dtype=float)
    lo = np.array([PARAM_SPECS[p].min for p in parameters])
    hi = np.array([PARAM_SPECS[p].max for p in parameters])

    def residuals(x: np.ndarray) -> np.ndarray:
        t, b = _simulate(design, materials, rpm, dict(zip(parameters, x, strict=True)))
        r = [(t - torque_meas) / t_sigma]
        if boost_meas is not None:
            r.append((b - boost_meas) / BOOST_SIGMA)
        return np.concatenate(r)

    r0 = residuals(x0)
    fit = least_squares(residuals, x0, bounds=(lo, hi), x_scale=np.maximum(np.abs(x0), 1e-3), diff_step=1e-4)

    # Linearised covariance: (JᵀJ)⁻¹ · s², s² = RSS / (m − n).
    m, n = fit.fun.size, len(parameters)
    dof = max(m - n, 1)
    s2 = float(fit.fun @ fit.fun) / dof
    jtj = fit.jac.T @ fit.jac
    try:
        cov = np.linalg.inv(jtj) * s2
        sigma = np.sqrt(np.clip(np.diag(cov), 0, None))
        corr = cov / np.outer(sigma, sigma)
    except np.linalg.LinAlgError:
        sigma = np.full(n, np.nan)
        corr = np.full((n, n), np.nan)

    warnings = []
    for i in range(n):
        for j in range(i + 1, n):
            if np.isfinite(corr[i, j]) and abs(corr[i, j]) > 0.95:
                warnings.append(
                    f"{PARAM_SPECS[parameters[i]].label} and {PARAM_SPECS[parameters[j]].label} are strongly correlated "
                    f"(ρ = {corr[i, j]:.2f}): this data cannot tell them apart. Fix one of them, or add data that separates them (e.g. part-load or motoring-friction runs)."
                )
    at_bound = [p for p, v, a, b in zip(parameters, fit.x, lo, hi, strict=True) if np.isclose(v, a) or np.isclose(v, b)]
    if at_bound:
        warnings.append(f"Hit the allowed range for {', '.join(at_bound)}: the model may be missing physics, "
                        "or the data may contain an error.")

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    calibrated = design.model_dump()
    fitted = []
    for p, v0, v, s in zip(parameters, x0, fit.x, sigma, strict=True):
        tol = float(1.96 * s) if np.isfinite(s) else 0.0
        section, key = p.split(".")
        calibrated[section][key] = Param(
            value=float(v), source=Source.CALIBRATED, tol=tol,
            ref=f"Fitted to measurement '{run.name}' on {stamp} ({m} residuals)",
        ).model_dump()
        fitted.append({"path": p, "label": PARAM_SPECS[p].label, "unit": PARAM_SPECS[p].unit,
                       "before": float(v0), "after": float(v), "ci95": tol})

    t_before, b_before = _simulate(design, materials, rpm, {})
    t_after, b_after = _simulate(design, materials, rpm, dict(zip(parameters, fit.x, strict=True)))

    def rmse(a, b):
        return float(np.sqrt(np.mean((a - b) ** 2)))

    return {
        "parameters": fitted,
        "success": bool(fit.success),
        "message": fit.message,
        "torque_rmse_before": rmse(t_before, torque_meas),
        "torque_rmse_after": rmse(t_after, torque_meas),
        "boost_rmse_before": None if boost_meas is None else rmse(b_before, boost_meas),
        "boost_rmse_after": None if boost_meas is None else rmse(b_after, boost_meas),
        "cost_before": float(r0 @ r0) / 2,
        "cost_after": float(fit.cost),
        "curves": {
            "rpm": rpm.tolist(),
            "torque_measured": torque_meas.tolist(),
            "torque_before": t_before.tolist(),
            "torque_after": t_after.tolist(),
            "boost_measured": None if boost_meas is None else boost_meas.tolist(),
            "boost_before": b_before.tolist(),
            "boost_after": b_after.tolist(),
        },
        "correlation": corr.tolist(),
        "warnings": warnings,
        "calibrated_design": calibrated,
        "notes": [
            "Calibration adjusts lumped model parameters so the model reproduces this data. It improves predictions "
            "near the measured conditions; extrapolating far beyond them (e.g. much higher boost) is less certain.",
            "Confidence intervals come from a linearised fit; they assume the model form is right and the errors are independent.",
        ],
    }
