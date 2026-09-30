"""Body geometry (spec §9): a simplified engineering sketch that feeds the physics.

The body is described by two sketches, as a designer would start one:
  * a side profile: the upper outline from the front bumper to the rear bumper
    (normalised 0-1 along the length and height), closed along the underbody at
    ground clearance;
  * a front half-section: the outline from the underbody centreline round the
    side to the roof centreline (normalised to half-width and height).

From these and the main dimensions the model derives frontal area, side area,
an approximate outer-panel area and mass (panel thickness × material density),
the panels' centre-of-gravity height and the envelope volume. Aerodynamic drag
cannot be derived from a sketch without CFD, so Cd stays an input.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from autoeng.domain.materials import Material

MODEL_ID = "geometry.body_sketch"
MODEL_VERSION = "1.0.0"

ASSUMPTIONS = [
    "Frontal area is the area of the front section (mirrored half-section) above ground clearance; mirrors, "
    "wheels and underbody details are not included.",
    "Outer-panel area ≈ 2 × side area + side-profile perimeter × mean width (a prismatic-body approximation); "
    "real panels add flanges, openings and inner skins.",
    "Panel mass = panel area × thickness × material density. It is the outer skin only, not the load-bearing structure.",
    "Drag coefficient is not computed: it needs a CFD or wind-tunnel result (planned for stage 4).",
]


def _check_points(v: list[list[float]], name: str) -> list[list[float]]:
    if len(v) < 4:
        raise ValueError(f"{name} needs at least 4 points")
    for p in v:
        if len(p) != 2 or not (-0.05 <= p[0] <= 1.05 and -0.05 <= p[1] <= 1.05):
            raise ValueError(f"{name}: points must be [x, y] pairs normalised to 0-1")
    return v


class BodyGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    length_mm: float = Field(ge=1500, le=7000)
    width_mm: float = Field(ge=1000, le=2600)
    height_mm: float = Field(ge=800, le=2500)
    wheelbase_mm: float = Field(ge=1500, le=4500)
    front_overhang_mm: float = Field(ge=200, le=1800)
    ground_clearance_mm: float = Field(ge=50, le=400)
    wheel_diameter_mm: float = Field(ge=450, le=950)
    panel_thickness_mm: float = Field(ge=0.3, le=10)
    panel_material_id: str
    side_profile: list[list[float]]  # front bumper → roof → rear bumper, x 0→1
    front_section: list[list[float]]  # underbody centreline → side → roof centreline, x = half-width share
    applied_panel_mass_kg: float | None = None  # panel mass at the time the vehicle mass was last updated
    # Surface detail for the lofted 3D body (see body_mesh.py).
    beltline: float = Field(default=0.6, ge=0.3, le=0.85)  # share of body height where the glasshouse starts
    tumblehome: float = Field(default=0.14, ge=0.0, le=0.4)  # inward lean of the glasshouse at the roof
    plan_taper_front: float = Field(default=0.14, ge=0.0, le=0.4)  # rounding of the front bumper corners (plan view)
    plan_taper_rear: float = Field(default=0.08, ge=0.0, le=0.4)
    arch_clearance_mm: float = Field(default=40.0, ge=10, le=150)  # wheel-well gap around the tyre
    mesh_id: str | None = None  # imported surface mesh that replaces the loft in the wind tunnel

    @field_validator("side_profile")
    @classmethod
    def _side(cls, v):
        return _check_points(v, "side_profile")

    @field_validator("front_section")
    @classmethod
    def _front(cls, v):
        return _check_points(v, "front_section")


def _polygon_area(xy: np.ndarray) -> float:
    x, y = xy[:, 0], xy[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _polygon_centroid_y(xy: np.ndarray) -> float:
    x, y = xy[:, 0], xy[:, 1]
    cross = x * np.roll(y, -1) - np.roll(x, -1) * y
    a = cross.sum() / 2
    if abs(a) < 1e-12:
        return float(y.mean())
    return float(((y + np.roll(y, -1)) * cross).sum() / (6 * a))


def _perimeter(xy: np.ndarray, closed: bool = True) -> float:
    d = np.diff(np.vstack([xy, xy[:1]]) if closed else xy, axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


def side_polygon(g: BodyGeometry) -> np.ndarray:
    """Side outline in metres: sketch points scaled, closed along the underbody."""
    L, H, gc = g.length_mm / 1000, g.height_mm / 1000, g.ground_clearance_mm / 1000
    pts = np.array(sorted(g.side_profile, key=lambda p: p[0]), dtype=float)
    upper = np.column_stack([pts[:, 0] * L, gc + pts[:, 1] * (H - gc)])
    return upper[::-1]  # rear → front along the top; the closing edge runs along the underbody


def section_polygon(g: BodyGeometry) -> np.ndarray:
    """Full front section in metres (half-section mirrored about the centreline)."""
    W, H, gc = g.width_mm / 1000, g.height_mm / 1000, g.ground_clearance_mm / 1000
    half = np.array(g.front_section, dtype=float)
    right = np.column_stack([half[:, 0] * W / 2, gc + half[:, 1] * (H - gc)])
    left = right[::-1].copy()
    left[:, 0] *= -1
    return np.vstack([right, left])


def analyse(g: BodyGeometry, materials: Mapping[str, Material]) -> dict:
    mat = materials.get(g.panel_material_id)
    if mat is None or mat.prop("density") is None:
        raise ValueError(f"Panel material '{g.panel_material_id}' needs a density")
    side = side_polygon(g)
    section = section_polygon(g)
    frontal = _polygon_area(section)
    side_area = _polygon_area(side)
    height_eff = g.height_mm / 1000 - g.ground_clearance_mm / 1000
    mean_width = frontal / max(height_eff, 1e-6)
    panel_area = 2 * side_area + _perimeter(side) * mean_width
    t = g.panel_thickness_mm / 1000
    density = mat.prop("density")
    panel_mass = panel_area * t * density.value
    panel_mass_tol = panel_area * t * density.tol
    rear_overhang = g.length_mm - g.wheelbase_mm - g.front_overhang_mm
    warnings = []
    if rear_overhang < 150:
        warnings.append("Rear overhang is under 150 mm: wheelbase plus front overhang nearly exceeds the length.")
    if g.wheel_diameter_mm / 2 + 30 > g.height_mm - g.ground_clearance_mm:
        warnings.append("Wheels are taller than the body side: check height and wheel diameter.")
    if frontal / (g.width_mm / 1000 * height_eff) < 0.55:
        warnings.append("The front section fills under 55 % of its bounding box; check the section sketch.")
    return {
        "frontal_area_m2": frontal,
        "side_area_m2": side_area,
        "panel_area_m2": panel_area,
        "panel_mass_kg": panel_mass,
        "panel_mass_tol_kg": panel_mass_tol,
        "panel_cg_height_m": _polygon_centroid_y(side),
        "envelope_volume_m3": side_area * mean_width,
        "mean_width_m": mean_width,
        "rear_overhang_mm": rear_overhang,
        "fill_ratio_front": frontal / (g.width_mm / 1000 * height_eff),
        "material": {"id": mat.id, "name": f"{mat.name} {mat.condition}".strip(), "density": density.value,
                     "density_source": density.source},
        "warnings": warnings,
        "model": {"id": MODEL_ID, "version": MODEL_VERSION},
        "assumptions": ASSUMPTIONS,
    }


def default_geometry() -> dict:
    """A generic two-box hatchback sketch to start from."""
    return BodyGeometry(
        length_mm=4260, width_mm=1790, height_mm=1440, wheelbase_mm=2630, front_overhang_mm=890,
        ground_clearance_mm=140, wheel_diameter_mm=640, panel_thickness_mm=0.8, panel_material_id="steel_dc04",
        side_profile=[[0.0, 0.22], [0.02, 0.42], [0.1, 0.5], [0.3, 0.58], [0.42, 0.92], [0.55, 1.0], [0.78, 0.98],
                      [0.92, 0.8], [0.99, 0.55], [1.0, 0.2]],
        front_section=[[0.0, 0.0], [0.9, 0.0], [1.0, 0.15], [1.0, 0.5], [0.93, 0.62], [0.8, 0.95], [0.5, 1.0],
                       [0.0, 1.0]],
    ).model_dump()
