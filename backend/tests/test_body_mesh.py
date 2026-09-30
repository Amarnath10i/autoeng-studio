"""Detailed body loft, mesh import and voxelisation."""

import struct

import numpy as np
import pytest

from autoeng.platform import body_mesh as bm
from autoeng.platform.body import BodyGeometry, default_geometry

G = BodyGeometry(**default_geometry())
DX = 0.04


def grid(length=4.4, width=2.0, height=1.7):
    # Offset so no cell centre sits exactly on a flat face (such ties are settled by the vote, not a leak).
    off = 0.0037
    xs = np.arange(-0.1, length, DX) + DX / 2 + off
    ys = np.arange(-width / 2, width / 2, DX) + DX / 2 + off
    zs = np.arange(0, height, DX) + DX / 2 + off
    return xs, ys, zs


def extent(solid, axis_keep):
    idx = np.nonzero(solid.any(axis=tuple(a for a in range(3) if a != axis_keep)))[0]
    return (idx.max() - idx.min() + 1) * DX


def binary_stl(tris: np.ndarray) -> bytes:
    out = bytearray(80) + struct.pack("<I", len(tris))
    for t in tris.astype(np.float32):
        out += struct.pack("<3f", 0, 0, 0) + t.tobytes() + b"\0\0"
    return bytes(out)


def test_loft_matches_the_sketch_dimensions():
    m = bm.loft(G)
    v = m["vertices"]
    assert v[:, 0].min() == pytest.approx(0, abs=1e-9)
    assert v[:, 0].max() == pytest.approx(G.length_mm / 1000, abs=1e-9)
    assert v[:, 2].max() == pytest.approx(G.height_mm / 1000, abs=0.005)
    assert 2 * v[:, 1].max() == pytest.approx(G.width_mm / 1000, abs=0.01)
    assert m["glass"].any() and not m["glass"].all()


def test_loft_is_watertight_all_ray_directions_agree():
    tris = bm.loft_triangles(G)
    xs, ys, zs = grid()
    c = [xs, ys, zs]
    z, x, y = bm._parity(tris, (2, 0, 1), c), bm._parity(tris, (0, 1, 2), c), bm._parity(tris, (1, 2, 0), c)
    assert z.sum() > 0
    assert (z != x).mean() < 1e-3 and (z != y).mean() < 1e-3


def test_wheel_wells_are_recessed():
    tris = bm.loft_triangles(G)
    xs, ys, zs = grid()
    solid = bm.voxelize_triangles(tris, xs, ys, zs)
    wh = bm.wheel_positions(G)[0]
    i = np.argmin(np.abs(xs - wh["x"]))
    k = np.argmin(np.abs(zs - wh["r"]))
    j = np.argmin(np.abs(ys - wh["y"]))
    assert not solid[k, j, i]  # where the tyre sits, the body is cut back
    assert solid[k, np.argmin(np.abs(ys)), i]  # but the body is there on the centreline


def test_stl_round_trip_matches_the_loft():
    tris = bm.loft_triangles(G)
    parsed = bm.parse_mesh(binary_stl(tris * 1000), "car.stl")  # exported in millimetres
    norm, info = bm.normalise_mesh(parsed, units="mm")
    assert info["length"] == pytest.approx(G.length_mm / 1000, abs=1e-3)
    xs, ys, zs = grid()
    a = bm.voxelize_triangles(tris, xs, ys, zs)
    b = bm.voxelize_triangles(norm, xs, ys, zs - G.ground_clearance_mm / 1000)  # import rests the car on the road
    assert abs(int(a.sum()) - int(b.sum())) / a.sum() < 0.02


def test_import_restores_orientation_y_up_and_reversed_nose():
    tris = bm.loft_triangles(G)
    # Y-up export with the nose pointing to +x: (x, y, z) → (-x, z, -y) in the file.
    file_tris = np.stack([-tris[..., 0], tris[..., 2], -tris[..., 1]], axis=-1)
    norm, _ = bm.normalise_mesh(file_tris, units="m", up="y")
    pts = norm.reshape(-1, 3)
    span = pts[:, 0].max()
    front = pts[pts[:, 0] < 0.15 * span, 2].max()
    back = pts[pts[:, 0] > 0.85 * span, 2].max()
    assert front < back + 0.2  # bonnet end at x = 0
    assert pts[:, 2].min() == pytest.approx(0, abs=1e-6)


def test_obj_parser_handles_quads_and_slashes():
    text = "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nvt 0 0\nf 1/1/1 2/1/1 3/1/1 4/1/1\n"
    tris = bm.parse_mesh(text.encode(), "plane.obj")
    assert tris.shape == (2, 3, 3)


def test_import_rejects_bad_units_and_formats():
    with pytest.raises(ValueError, match="stl or .obj"):
        bm.parse_mesh(b"xx", "car.fbx")
    tris = bm.loft_triangles(G)
    with pytest.raises(ValueError, match="units must be"):
        bm.normalise_mesh(tris, units="furlong")
    with pytest.raises(ValueError, match="check the units"):
        bm.normalise_mesh(tris, units="mm")  # a model in metres read as millimetres is 4 mm long


def test_upload_and_run_through_the_api(client, auth):
    tris = bm.loft_triangles(G)
    r = client.post("/api/v1/body/meshes?filename=hatch.stl&units=mm", content=binary_stl(tris * 1000),
                    headers={**auth, "content-type": "application/octet-stream"})
    assert r.status_code == 201, r.text
    mesh = r.json()
    assert mesh["triangles"] == len(tris)
    assert client.get("/api/v1/body/meshes", headers=auth).json()[0]["id"] == mesh["id"]
    full = client.get(f"/api/v1/body/meshes/{mesh['id']}", headers=auth).json()
    assert len(full["triangles_b64"]) > 1000
    loft = client.post("/api/v1/body/mesh", json={"geometry": default_geometry()}).json()
    assert loft["stats"]["quads"] > 5000
    geometry = {**default_geometry(), "mesh_id": mesh["id"]}
    job = client.post("/api/v1/aero/run", json={"geometry": geometry, "resolution": "draft"}, headers=auth)
    assert job.status_code == 202, job.text
    assert client.delete(f"/api/v1/body/meshes/{mesh['id']}", headers=auth).status_code == 204
