"""Detailed body surface: a lofted quad mesh from the sketch, imported meshes, and voxelisation.

The loft builds the outer skin as rings of points along the car. Each ring is the
intersection of the side profile (roofline) and the front section, shaped by:

  * a plan-view taper that rounds the corners of the bumpers;
  * a beltline above which the greenhouse leans inwards (tumblehome);
  * an underbody that sweeps up at the nose and into a rear diffuser;
  * wheel wells recessed into the sides around each wheel.

Every ring is closed and the ends are capped, so the surface is watertight: it
can be exported, rendered with its quad wireframe, and voxelised for the wind tunnel.
Imported STL/OBJ meshes (from Blender, Fusion, Onshape…) go through the same
voxeliser, which votes across three ray directions so small holes in a mesh do
not flood the result.

Car frame: x from the nose rearwards, y to the right of the centreline, z up from the road; metres.
"""

from __future__ import annotations

import re
import struct

import numpy as np

MODEL_ID = "geometry.body_loft"
MODEL_VERSION = "1.0.0"

WHEEL_WIDTH = 0.24
MAX_TRIANGLES = 400_000

N_STATIONS = 120
N_FLOOR, N_SIDE, N_TOP = 6, 30, 8


# --------------------------------------------------------------------- sketch curves

def _catmull_rom(points: np.ndarray, per_segment: int = 24) -> np.ndarray:
    out = []
    n = len(points)
    for i in range(n - 1):
        p0, p1, p2, p3 = points[max(i - 1, 0)], points[i], points[i + 1], points[min(i + 2, n - 1)]
        t = np.linspace(0, 1, per_segment, endpoint=False)[:, None]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t**2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t**3))
    out.append(points[-1:])
    return np.vstack(out)


def _roofline(g):
    """Normalised roof height (0-1 of body height above clearance) as a function of normalised length."""
    side = _catmull_rom(np.array(sorted(g.side_profile, key=lambda p: p[0]), dtype=float))
    order = np.argsort(side[:, 0])
    xs, hs = side[order, 0], np.clip(side[order, 1], 0.02, 1.0)
    return lambda xn: np.interp(xn, xs, hs)


def _section_width(g, bins: int = 161):
    """Half-width share of the front section as a function of normalised height (0 = underbody, 1 = roof)."""
    sec = _catmull_rom(np.array(g.front_section, dtype=float), 32)
    zb = np.linspace(0, 1, bins)
    w = np.full(bins, np.nan)
    idx = np.clip(np.round(np.clip(sec[:, 1], 0, 1) * (bins - 1)).astype(int), 0, bins - 1)
    for i, x in zip(idx, sec[:, 0], strict=True):
        w[i] = x if np.isnan(w[i]) else max(w[i], x)
    ok = ~np.isnan(w)
    w = np.interp(zb, zb[ok], w[ok])
    return lambda zn: np.interp(zn, zb, np.clip(w, 0.02, 1.0))


# --------------------------------------------------------------------- loft

def _stations(n: int) -> np.ndarray:
    u = np.linspace(0, 1, n)
    return 0.55 * u + 0.45 * (0.5 - 0.5 * np.cos(np.pi * u))  # denser at the bumpers


def wheel_positions(g) -> list[dict]:
    """Wheel centres and lateral positions, flush with the body side at hub height."""
    L, W = g.length_mm / 1000, g.width_mm / 1000
    H, gc = g.height_mm / 1000, g.ground_clearance_mm / 1000
    r = g.wheel_diameter_mm / 2000
    width = _section_width(g)
    out = []
    for x in (g.front_overhang_mm / 1000, (g.front_overhang_mm + g.wheelbase_mm) / 1000):
        side = (W / 2) * _plan(g, x / L) * float(width(np.clip((r - gc) / (H - gc), 0, 1)))
        out.append({"x": x, "r": r, "y": max(side - WHEEL_WIDTH / 2 - 0.01, WHEEL_WIDTH), "width": WHEEL_WIDTH})
    return out


def _plan(g, xn):
    """Plan-view taper: the half-width share left at each station (rounded bumper corners)."""
    tf, tr = g.plan_taper_front, g.plan_taper_rear
    front = np.clip((0.2 - xn) / 0.2, 0, 1) ** 2
    rear = np.clip((xn - 0.84) / 0.16, 0, 1) ** 2
    return 1.0 - tf * front - tr * rear


def loft(g) -> dict:
    """Quad-dominant closed surface of the body. Returns vertices (V, 3), quads (Q, 4), cap triangles (T, 3) and tags."""
    L, W, H = g.length_mm / 1000, g.width_mm / 1000, g.height_mm / 1000
    gc = g.ground_clearance_mm / 1000
    roof, width = _roofline(g), _section_width(g)
    belt = gc + g.beltline * (H - gc)
    wheels = wheel_positions(g)

    xn = _stations(N_STATIONS)
    top = gc + roof(xn) * (H - gc)
    # Underbody: flat floor that sweeps up at the nose (splitter) and into a rear diffuser.
    nose = np.clip((0.06 - xn) / 0.06, 0, 1) ** 2
    tail = np.clip((xn - 0.88) / 0.12, 0, 1) ** 1.5
    bottom = gc + (top - gc) * (0.35 * nose + 0.4 * tail)
    bottom = np.minimum(bottom, top - 0.03)

    def half_width(z, i):
        zn = np.clip((z - gc) / (H - gc), 0, 1)
        w = (W / 2) * _plan(g, xn[i]) * width(zn)
        lean = np.clip((z - belt) / max(H - belt, 1e-6), 0, 1)
        return w * (1 - g.tumblehome * lean**1.3)

    rings = []
    for i in range(N_STATIONS):
        zb, zt = bottom[i], top[i]
        # Underbody centre → out along the floor → up the side → across the top → roof centre.
        yf = half_width(np.array([zb]), i)[0]
        floor = np.column_stack([np.linspace(0, yf, N_FLOOR, endpoint=False), np.full(N_FLOOR, zb)])
        # A gentle roof/bonnet crown: the shoulder sits 1.5 % of the width below the centreline height.
        drop = min(0.015 * W, 0.3 * (zt - zb)) if zt > gc + 0.1 else 0.0
        shoulder = zt - drop
        zs = zb + (shoulder - zb) * (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, N_SIDE, endpoint=False)))
        side = np.column_stack([half_width(zs, i), zs])
        yt = half_width(np.array([shoulder]), i)[0]
        crown = np.linspace(yt, 0, N_TOP + 1)
        ztop = zt - drop * (crown / max(yt, 1e-6)) ** 2
        topc = np.column_stack([crown, ztop])
        half = np.vstack([floor, side, topc])  # (m, 2): y, z; ends on the centreline
        # Wheel wells: push the skin in around each wheel so the tyre sits in a recess.
        x = xn[i] * L
        for wh in wheels:
            y_in = wh["y"] - wh["width"] / 2 - 0.035
            inside = ((x - wh["x"]) ** 2 + (half[:, 1] - wh["r"]) ** 2 < (wh["r"] + g.arch_clearance_mm / 1000) ** 2)
            inside &= half[:, 0] > y_in
            half[inside, 0] = y_in
        right = np.column_stack([np.full(len(half), x), half[:, 0], half[:, 1]])
        left = right[-2:0:-1].copy()
        left[:, 1] *= -1
        rings.append(np.vstack([right, left]))
    rings = np.array(rings)  # (S, R, 3)
    S, R, _ = rings.shape
    verts = rings.reshape(-1, 3)
    idx = np.arange(S * R).reshape(S, R)
    a, b = idx[:-1], idx[1:]
    quads = np.stack([a, np.roll(a, -1, axis=1), np.roll(b, -1, axis=1), b], axis=-1).reshape(-1, 4)

    # Caps: fan from each end ring's centre.
    caps = []
    for s, flip in ((0, True), (S - 1, False)):
        c = len(verts)
        verts = np.vstack([verts, rings[s].mean(axis=0, keepdims=True)])
        ring = idx[s]
        tri = np.stack([np.full(R, c), ring, np.roll(ring, -1)], axis=1)
        caps.append(tri[:, ::-1] if flip else tri)
    caps = np.vstack(caps)

    # Glass: greenhouse faces above the beltline that are not the roof itself.
    q = verts[quads]
    centre = q.mean(axis=1)
    n = np.cross(q[:, 2] - q[:, 0], q[:, 3] - q[:, 1])
    nz = np.abs(n[:, 2]) / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    xq = centre[:, 0] / L
    glass = (centre[:, 2] > belt + 0.035) & (nz < 0.86) & (roof(xq) * (H - gc) + gc > belt + 0.12)
    return {"vertices": verts, "quads": quads, "triangles": caps, "glass": glass, "wheels": wheels,
            "bounds": {"length": L, "width": W, "height": float(verts[:, 2].max())}}


def loft_triangles(g) -> np.ndarray:
    m = loft(g)
    v, q = m["vertices"], m["quads"]
    tris = np.concatenate([v[q[:, [0, 1, 2]]], v[q[:, [0, 2, 3]]], v[m["triangles"]]])
    area = np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
    return tris[area > 1e-12]


def loft_dict(g) -> dict:
    """Loft as JSON for rendering: rounded vertices, quads and cap triangles."""
    m = loft(g)
    return {
        "vertices": np.round(m["vertices"], 4).ravel().tolist(),
        "quads": m["quads"].ravel().tolist(),
        "triangles": m["triangles"].ravel().tolist(),
        "glass": m["glass"].astype(int).tolist(),
        "wheels": m["wheels"],
        "stats": {"vertices": len(m["vertices"]), "quads": len(m["quads"]), "stations": N_STATIONS,
                  "ring": 2 * (N_FLOOR + N_SIDE + N_TOP + 1) - 2,
                  "triangles": 2 * len(m["quads"]) + len(m["triangles"])},
        "bounds": m["bounds"],
        "model": {"id": MODEL_ID, "version": MODEL_VERSION},
    }


# --------------------------------------------------------------------- import

UNITS = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254}


def parse_mesh(data: bytes, filename: str) -> np.ndarray:
    """Triangles (T, 3, 3) from STL (binary or ASCII) or OBJ bytes."""
    name = filename.lower()
    if name.endswith(".obj"):
        return _parse_obj(data.decode("utf-8", errors="replace"))
    if name.endswith(".stl"):
        if len(data) >= 84:
            count = struct.unpack("<I", data[80:84])[0]
            if 84 + 50 * count == len(data):
                rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
                                    count=count, offset=84)
                return rec["v"].astype(np.float64)
        text = data.decode("utf-8", errors="replace")
        nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
        if not nums:
            raise ValueError("Could not read the STL: no triangles found")
        return np.array(nums, dtype=np.float64).reshape(-1, 3, 3)
    raise ValueError("Upload an .stl or .obj file")


def _parse_obj(text: str) -> np.ndarray:
    verts, faces = [], []
    for line in text.splitlines():
        if line.startswith("v "):
            verts.append([float(t) for t in line.split()[1:4]])
        elif line.startswith("f "):
            idx = [int(t.split("/")[0]) for t in line.split()[1:]]
            faces.extend([idx[0], idx[k], idx[k + 1]] for k in range(1, len(idx) - 1))
    if not verts or not faces:
        raise ValueError("Could not read the OBJ: no faces found")
    v = np.array(verts)
    f = np.array(faces)
    f = np.where(f < 0, len(v) + f, f - 1)  # OBJ indices are 1-based; negatives count from the end
    if f.min() < 0 or f.max() >= len(v):
        raise ValueError("OBJ face refers to a missing vertex")
    return v[f]


def normalise_mesh(tris: np.ndarray, units: str = "mm", up: str = "z", nose: str = "auto",
                   ground_offset_mm: float = 0.0) -> tuple[np.ndarray, dict]:
    """Put an imported mesh in the car frame: z up, nose at x = 0, centred laterally, lowest point on the road."""
    if len(tris) == 0:
        raise ValueError("The mesh has no triangles")
    if len(tris) > MAX_TRIANGLES:
        raise ValueError(f"The mesh has {len(tris):,} triangles; decimate it to under {MAX_TRIANGLES:,} first")
    if units not in UNITS:
        raise ValueError(f"units must be one of {', '.join(UNITS)}")
    t = tris * UNITS[units]
    if up == "y":  # Y-up (most OBJ exports): (x, y, z) → (x, -z, y)
        t = np.stack([t[..., 0], -t[..., 2], t[..., 1]], axis=-1)
    elif up != "z":
        raise ValueError("up must be 'z' or 'y'")
    pts = t.reshape(-1, 3)
    ext = pts.max(axis=0) - pts.min(axis=0)
    if ext[1] > ext[0]:  # length runs along y: turn the car so it runs along x
        t = np.stack([t[..., 1], -t[..., 0], t[..., 2]], axis=-1)
        pts = t.reshape(-1, 3)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    if nose == "auto":
        # The nose is the end whose frontal slice sits lower (bonnet) than the tail's.
        span = hi[0] - lo[0]
        front = pts[pts[:, 0] < lo[0] + 0.15 * span, 2].max()
        back = pts[pts[:, 0] > hi[0] - 0.15 * span, 2].max()
        flip = back < front
    else:
        flip = nose == "max_x"
    if flip:
        t = np.stack([-t[..., 0], -t[..., 1], t[..., 2]], axis=-1)
        pts = t.reshape(-1, 3)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
    t = t - np.array([lo[0], (lo[1] + hi[1]) / 2, lo[2] - ground_offset_mm / 1000])
    pts = t.reshape(-1, 3)
    size = pts.max(axis=0) - pts.min(axis=0)
    if not (1.0 < size[0] < 12.0):
        raise ValueError(f"The mesh is {size[0]:.2f} m long in these units; check the units setting")
    return t.astype(np.float32), {"length": float(size[0]), "width": float(size[1]), "height": float(pts[:, 2].max()),
                                  "triangles": int(len(t))}


# --------------------------------------------------------------------- voxelisation

def _parity(tris: np.ndarray, axes: tuple[int, int, int], centres: list[np.ndarray]) -> np.ndarray:
    """Inside test by counting surface crossings along rays parallel to axis a (a, b, c are axis indices)."""
    a, b, c = axes
    ca, cb, cc = centres[a], centres[b], centres[c]
    na, nb, nc = len(ca), len(cb), len(cc)
    d = ca[1] - ca[0]
    # Nudge ray origins off the cell centres so rays do not graze shared edges exactly.
    cb = cb + 1.37e-4 * d
    cc = cc + 2.71e-4 * d
    p = tris[:, :, [b, c]]  # triangles projected on the (b, c) plane
    lo = np.floor((p.min(axis=1) - [cb[0], cc[0]]) / d).astype(int)
    hi = np.ceil((p.max(axis=1) - [cb[0], cc[0]]) / d).astype(int)
    lo = np.clip(lo, 0, [nb - 1, nc - 1])
    hi = np.clip(hi, 0, [nb - 1, nc - 1])
    nbs, ncs = hi[:, 0] - lo[:, 0] + 1, hi[:, 1] - lo[:, 1] + 1
    counts = nbs * ncs
    t_idx = np.repeat(np.arange(len(tris)), counts)
    local = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    jb = lo[t_idx, 0] + local % nbs[t_idx]
    jc = lo[t_idx, 1] + local // nbs[t_idx]
    qb, qc = cb[jb], cc[jc]
    v0, v1, v2 = p[t_idx, 0], p[t_idx, 1], p[t_idx, 2]
    den = (v1[:, 1] - v2[:, 1]) * (v0[:, 0] - v2[:, 0]) + (v2[:, 0] - v1[:, 0]) * (v0[:, 1] - v2[:, 1])
    ok = np.abs(den) > 1e-14
    den = np.where(ok, den, 1.0)
    l0 = ((v1[:, 1] - v2[:, 1]) * (qb - v2[:, 0]) + (v2[:, 0] - v1[:, 0]) * (qc - v2[:, 1])) / den
    l1 = ((v2[:, 1] - v0[:, 1]) * (qb - v2[:, 0]) + (v0[:, 0] - v2[:, 0]) * (qc - v2[:, 1])) / den
    l2 = 1 - l0 - l1
    hit = ok & (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
    ta = tris[t_idx[hit], :, a]
    za = l0[hit] * ta[:, 0] + l1[hit] * ta[:, 1] + l2[hit] * ta[:, 2]
    k = np.clip(np.ceil((za - ca[0]) / d).astype(int), 0, na)  # first cell centre beyond the crossing
    toggles = np.zeros((nb, nc, na + 1), dtype=np.int32)
    np.add.at(toggles, (jb[hit], jc[hit], k), 1)
    inside = (np.cumsum(toggles, axis=2)[:, :, :na] % 2).astype(bool)  # (nb, nc, na)
    # Back to (z, y, x) order.
    order = {a: 2, b: 0, c: 1}
    return np.transpose(inside, (order[2], order[1], order[0]))


def voxelize_triangles(tris: np.ndarray, xs: np.ndarray, ys: np.ndarray, zs: np.ndarray) -> np.ndarray:
    """Solid mask (nz, ny, nx) of a closed triangle surface on a uniform grid of cell centres.

    A cell is solid when at least two of three ray directions (along x, y and z) find it
    inside, so a mesh with small gaps still voxelises cleanly.
    """
    tris = np.asarray(tris, dtype=np.float64)
    centres = [xs, ys, zs]
    votes = (_parity(tris, (2, 0, 1), centres).astype(np.int8)
             + _parity(tris, (0, 1, 2), centres) + _parity(tris, (1, 2, 0), centres))
    return votes >= 2
