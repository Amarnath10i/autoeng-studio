"""Engineering values with provenance and uncertainty.

Every input to a physics model is a `Param`: a nominal value, where it came from
(`Source`), and how uncertain it is (`tol`, `dist`). Uncertainty is propagated by
Monte Carlo sampling, so the spread of every result traces back to input spreads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class Source(StrEnum):
    """Where a value came from. Spec §7 and §24: never blur these."""

    MEASURED = "measured"
    MANUFACTURER = "manufacturer"
    LITERATURE = "literature"
    USER = "user"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"
    CALIBRATED = "calibrated"  # fitted to measured data by the calibration engine
    COMMUNITY = "community"  # learned from calibrations other users shared (similar real engines)
    # The two below only describe results, never inputs.
    CALCULATED = "calculated"
    SIMULATED = "simulated"


INPUT_SOURCES = [
    Source.MEASURED,
    Source.MANUFACTURER,
    Source.LITERATURE,
    Source.USER,
    Source.ESTIMATED,
    Source.UNKNOWN,
    Source.CALIBRATED,
    Source.COMMUNITY,
]


class Dist(StrEnum):
    UNIFORM = "uniform"
    NORMAL = "normal"


class Param(BaseModel):
    """A numeric engineering input.

    `tol` is a half-width in the parameter's own unit and is read as an ~95 %
    interval: uniform samples fall in value ± tol, normal samples use σ = tol / 1.96.
    """

    model_config = ConfigDict(extra="forbid")

    value: float
    source: Source = Source.USER
    ref: str | None = Field(default=None, description="Citation, datasheet, or note")
    tol: float = Field(default=0.0, ge=0.0)
    dist: Dist = Dist.UNIFORM

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        if n == 1 or self.tol == 0.0:
            return np.full(n, self.value, dtype=float)
        if self.dist is Dist.NORMAL:
            return rng.normal(self.value, self.tol / 1.96, size=n)
        return rng.uniform(self.value - self.tol, self.value + self.tol, size=n)


def P(
    value: float,
    source: Source = Source.USER,
    tol: float = 0.0,
    ref: str | None = None,
    dist: Dist = Dist.UNIFORM,
) -> Param:
    """Terse constructor used by presets, catalogs and tests."""
    return Param(value=value, source=source, tol=tol, ref=ref, dist=dist)


@dataclass(frozen=True)
class ParamSpec:
    """Metadata for one design parameter: drives validation, the UI and education mode."""

    path: str
    label: str
    unit: str
    min: float
    max: float
    group: str
    beginner: str
    engineer: str
    integer: bool = False
    kind: str = "param"  # "param" (a Param), "int" (plain integer), "choice" (string id)
    step: float | None = None
    choices_from: str | None = None  # e.g. "fuels" or "materials"
    optional: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)
    choices: tuple[tuple[str, str], ...] = ()  # fixed (id, label) options for "choice" parameters

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "label": self.label,
            "unit": self.unit,
            "min": self.min,
            "max": self.max,
            "group": self.group,
            "beginner": self.beginner,
            "engineer": self.engineer,
            "integer": self.integer,
            "kind": self.kind,
            "step": self.step,
            "choices_from": self.choices_from,
            "optional": self.optional,
            "choices": [{"id": i, "label": label} for i, label in self.choices],
        }


def clip_sample(arr: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Keep sampled values inside a parameter's physical range."""
    return np.clip(arr, lo, hi)
