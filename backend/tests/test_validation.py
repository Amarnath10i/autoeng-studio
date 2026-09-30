"""Validation suite: benchmark geometries, the quick (verification) suite, and the API."""

import math
import time

import numpy as np
import pytest

from autoeng.platform import body_mesh
from autoeng.validation import cases, shapes

DX = 0.01


def voxels(body, pad=0.05):
    t = body.triangles
    lo, hi = t.reshape(-1, 3).min(axis=0) - pad, t.reshape(-1, 3).max(axis=0) + pad
    xs, ys, zs = (np.arange(lo[i], hi[i], DX) + DX / 2 + 0.0013 for i in range(3))
    return body_mesh.voxelize_triangles(t, xs, ys, zs)


def test_sphere_mesh_volume():
    s = voxels(shapes.sphere(0.5, 1.0))
    assert s.sum() * DX**3 == pytest.approx(math.pi / 6 * 0.5**3, rel=0.03)


@pytest.mark.parametrize("angle", [0, 25, 35])
def test_ahmed_body_dimensions(angle):
    body = shapes.ahmed_body(angle)
    pts = body.triangles.reshape(-1, 3)
    a = shapes.AHMED
    assert pts[:, 0].max() == pytest.approx(a["length"])
    assert 2 * pts[:, 1].max() == pytest.approx(a["width"])
    assert pts[:, 2].min() == pytest.approx(a["clearance"])
    rear_top = pts[np.isclose(pts[:, 0], a["length"]), 2].max()
    expected = a["clearance"] + a["height"] - a["slant_length"] * math.sin(math.radians(angle))
    assert rear_top == pytest.approx(expected, abs=1e-6)
    frontal = voxels(body).any(axis=2).sum() * DX**2
    assert frontal == pytest.approx(a["width"] * a["height"], rel=0.05)  # front radii do not change the projection


def test_verdict_bands():
    rows = [{"error": 4.0}, {"error": -12.0}]
    assert cases.verdict(rows, 10) == ("marginal", 12.0)
    assert cases.verdict([{"error": 1.0}], 10)[0] == "pass"
    assert cases.verdict([{"error": 30.0}], 10)[0] == "fail"


def test_clift_gauvin_reference_values():
    assert cases.clift_gauvin(100) == pytest.approx(1.09, abs=0.01)
    assert cases.clift_gauvin(1000) == pytest.approx(0.47, abs=0.01)


def test_quick_suite_passes():
    report = cases.run_suite(include_heavy=False)
    assert {c["id"] for c in report["cases"]} == {"engine_conservation", "balance_textbook", "conrod_buckling"}
    assert all(c["verdict"] == "pass" for c in report["cases"])


def test_published_report_is_shipped(client):
    r = client.get("/api/v1/validation").json()
    assert r["published"] is not None
    assert {c["id"] for c in r["published"]["cases"]} == {c.id for c in cases.CASES}
    assert r["field"]["engines"] >= 0


def test_run_quick_validation_job(client, auth):
    job = client.post("/api/v1/validation/run", json={"include_heavy": False}, headers=auth).json()
    for _ in range(100):
        j = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert j["status"] == "done", j.get("error")
    assert len(j["result"]["cases"]) == 3
