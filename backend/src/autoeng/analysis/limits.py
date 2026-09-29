"""Engineering limit evaluation (spec §15): SF = allowable / actual, with uncertainty.

Status bands are a project convention, not an industry standard, and they are
reported with every result so nobody mistakes them for certification:

  failure   nominal SF < 1
  critical  nominal SF < CRITICAL_SF, or the conservative (5th percentile) SF < 1
  warning   conservative SF < WARNING_SF
  ok        otherwise
  no_data   the allowable (or a material property) is not known
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from autoeng.core.params import Param, Source

WARNING_SF = 1.25
CRITICAL_SF = 1.10
# Temperature limits compare the rise above ambient (a ratio of °C values is meaningless),
# and use tighter bands because thermal allowables usually already contain margin.
THERMAL_WARNING_SF = 1.10
THERMAL_CRITICAL_SF = 1.05
STATUS_ORDER = ["no_data", "ok", "warning", "critical", "failure"]

STATUS_RULES = {
    "failure": "Nominal safety factor below 1.0: the model predicts the allowable is exceeded.",
    "critical": f"Nominal SF below {CRITICAL_SF}, or the 5th-percentile SF below 1.0 (exceedance plausible within uncertainty).",
    "warning": f"5th-percentile SF below {WARNING_SF}.",
    "ok": f"5th-percentile SF at or above {WARNING_SF}.",
    "no_data": "No documented allowable or material property: the check cannot be made.",
    "thermal": f"Temperature limits use SF = (allowable − ambient) / (actual − ambient) with bands {THERMAL_CRITICAL_SF} "
               f"and {THERMAL_WARNING_SF} instead of {CRITICAL_SF} and {WARNING_SF}.",
}


@dataclass
class LimitResult:
    id: str
    kind: str  # "limit" (user allowable on a channel) or "check" (structural model)
    component: str
    label: str
    unit: str
    channel: str | None
    actual_nominal: float | None
    actual_p95: float | None
    allowable_nominal: float | None
    allowable_source: str | None
    allowable_ref: str | None
    sf_nominal: float | None
    sf_p05: float | None
    p_exceed: float | None
    at_rpm: float | None
    status: str
    note: str = ""
    reference: float = 0.0  # SF is computed on (value − reference); ambient for temperatures
    warning_sf: float = WARNING_SF

    def as_dict(self) -> dict:
        return asdict(self)


def status_from_sf(sf_nominal: float, sf_p05: float, warning: float = WARNING_SF, critical: float = CRITICAL_SF) -> str:
    if sf_nominal < 1.0:
        return "failure"
    if sf_nominal < critical or sf_p05 < 1.0:
        return "critical"
    if sf_p05 < warning:
        return "warning"
    return "ok"


def worst(statuses: list[str]) -> str:
    return max(statuses, key=STATUS_ORDER.index) if statuses else "no_data"


def evaluate_max_limit(
    *,
    id: str,
    component: str,
    label: str,
    unit: str,
    channel: str,
    nominal_curve: np.ndarray,  # (R,)
    sample_curves: np.ndarray,  # (S, R)
    rpm: np.ndarray,
    allowable: Param,
    allowable_samples: np.ndarray,  # (S,)
    reference: float = 0.0,
    thermal: bool = False,
) -> LimitResult:
    idx = int(np.nanargmax(nominal_curve))
    actual_nom = float(nominal_curve[idx])
    worst_per_sample = np.nanmax(sample_curves, axis=1)
    warning, critical = (THERMAL_WARNING_SF, THERMAL_CRITICAL_SF) if thermal else (WARNING_SF, CRITICAL_SF)
    note = ""
    if allowable.source == Source.UNKNOWN:
        note = "Allowable has unknown provenance; treat this check as unverified."
    if thermal:
        note = (note + " " if note else "") + "SF computed on temperature rise above ambient."
    if actual_nom - reference <= 0:
        return LimitResult(id, "limit", component, label, unit, channel, actual_nom,
                           float(np.percentile(worst_per_sample, 95)), allowable.value, allowable.source,
                           allowable.ref, None, None, 0.0, float(rpm[idx]), "ok", "Load is zero or negative.",
                           reference, warning)
    sf_nom = (allowable.value - reference) / (actual_nom - reference)
    sf_samples = (allowable_samples - reference) / np.maximum(worst_per_sample - reference, 1e-12)
    sf_p05 = float(np.percentile(sf_samples, 5))
    return LimitResult(
        id=id,
        kind="limit",
        component=component,
        label=label,
        unit=unit,
        channel=channel,
        actual_nominal=actual_nom,
        actual_p95=float(np.percentile(worst_per_sample, 95)),
        allowable_nominal=allowable.value,
        allowable_source=allowable.source,
        allowable_ref=allowable.ref,
        sf_nominal=sf_nom,
        sf_p05=sf_p05,
        p_exceed=float(np.mean(sf_samples < 1.0)),
        at_rpm=float(rpm[idx]),
        status=status_from_sf(sf_nom, sf_p05, warning, critical),
        note=note,
        reference=reference,
        warning_sf=warning,
    )


def evaluate_sf_check(
    *,
    id: str,
    component: str,
    label: str,
    unit: str,
    actual_nominal: np.ndarray,  # (R,) load (e.g. stress)
    actual_samples: np.ndarray,  # (S, R)
    sf_nominal_curve: np.ndarray,  # (R,)
    sf_sample_curves: np.ndarray,  # (S, R)
    rpm: np.ndarray,
    allowable_nominal: float | None,
    allowable_source: str | None,
    note: str = "",
) -> LimitResult:
    """A model-computed safety factor; the governing point is the rpm with the lowest SF."""
    idx = int(np.nanargmin(sf_nominal_curve))
    sf_nom = float(sf_nominal_curve[idx])
    sf_per_sample = np.nanmin(sf_sample_curves, axis=1)
    sf_p05 = float(np.percentile(sf_per_sample, 5))
    load_per_sample = np.nanmax(actual_samples, axis=1)
    return LimitResult(
        id=id,
        kind="check",
        component=component,
        label=label,
        unit=unit,
        channel=None,
        actual_nominal=float(actual_nominal[idx]),
        actual_p95=float(np.percentile(load_per_sample, 95)),
        allowable_nominal=allowable_nominal,
        allowable_source=allowable_source,
        allowable_ref=None,
        sf_nominal=sf_nom,
        sf_p05=sf_p05,
        p_exceed=float(np.mean(sf_per_sample < 1.0)),
        at_rpm=float(rpm[idx]),
        status=status_from_sf(sf_nom, sf_p05),
        note=note,
    )


def no_data(id: str, component: str, label: str, unit: str, note: str) -> LimitResult:
    return LimitResult(id, "check", component, label, unit, None, None, None, None, None, None,
                       None, None, None, None, "no_data", note)
