"""3D wind tunnel: stability, sensible coefficients and shape ranking on a coarse grid."""

import json

import numpy as np
import pytest

from autoeng.physics import aero_lbm3d
from autoeng.platform.body import BodyGeometry, default_geometry

TINY = {"cells": 20, "u": 0.08, "re": 600, "flow_throughs": 1.0}


@pytest.fixture(autouse=True)
def tiny_resolution(monkeypatch):
    monkeypatch.setitem(aero_lbm3d.RESOLUTIONS, "tiny", TINY)


def _box() -> BodyGeometry:
    d = default_geometry()
    d["side_profile"] = [[0.0, 0.2], [0.001, 1.0], [0.999, 1.0], [1.0, 0.2]]
    d["front_section"] = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    return BodyGeometry(**d)


@pytest.fixture(scope="module")
def car():
    aero_lbm3d.RESOLUTIONS["tiny"] = TINY
    try:
        return aero_lbm3d.run(BodyGeometry(**default_geometry()), "tiny")
    finally:
        aero_lbm3d.RESOLUTIONS.pop("tiny", None)


def test_voxelised_body_matches_the_sketch():
    g = BodyGeometry(**default_geometry())
    vox = aero_lbm3d.voxelize(aero_lbm3d.body_from_geometry(g), 40)
    solid = vox["solid"]
    assert solid.any()
    height = (np.nonzero(solid.any(axis=(1, 2)))[0].max() + 1) * vox["dx"]
    assert height == pytest.approx(g.height_mm / 1000, abs=2 * vox["dx"])
    assert not solid[:, :, 0].any() and not solid[:, :, -1].any()  # clear of inlet and outlet


def test_run_is_stable_and_coefficients_are_sensible(car):
    assert np.isfinite(car["cd"]) and np.isfinite(car["cl"])
    assert 0.1 < car["cd"] < 3.0
    assert car["frontal_area_m2"] == pytest.approx(2.2, rel=0.25)
    assert car["max_speed_ratio"] < 3.0
    assert len(car["streamlines"]) > 0 and len(car["surface_pressure"]["cp"]) > 0
    assert car["history"] and all(np.isfinite(h["cd"]) for h in car["history"])


def test_force_history_settles_without_oscillating(car):
    tail = np.array([h["cd"] for h in car["history"][-10:]])
    assert tail.std() < 0.05  # trapped fluid slivers would make Cd alternate between samples


def test_result_is_strict_json(car):
    json.dumps(car, allow_nan=False)  # raises on NaN or Infinity


def test_front_stagnation_pressure_is_positive(car):
    s = car["surface_pressure"]
    x, cp = np.array(s["x"]), np.array(s["cp"])
    assert cp[x < x.min() + 0.15].max() > 0.3  # near Cp = 1 at the nose


def test_bluff_box_has_more_drag_than_the_car(car):
    box = aero_lbm3d.run(_box(), "tiny")
    assert box["cd"] > car["cd"]


def test_unknown_resolution_is_rejected():
    with pytest.raises(ValueError, match="resolution"):
        aero_lbm3d.run(BodyGeometry(**default_geometry()), "ultra")
