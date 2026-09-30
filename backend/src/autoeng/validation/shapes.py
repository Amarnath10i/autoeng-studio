"""Reference geometries for the validation benchmarks, as closed triangle surfaces in the tunnel frame (m)."""

from __future__ import annotations

import numpy as np

from autoeng.physics.aero_lbm3d import Body


def _tube(rings: np.ndarray) -> np.ndarray:
    """Close a stack of rings (S, R, 3) into triangles: side quads plus flat end caps."""
    S, R, _ = rings.shape
    a, b = rings[:-1], rings[1:]
    a1, b1 = np.roll(a, -1, axis=1), np.roll(b, -1, axis=1)
    side = np.concatenate([np.stack([a, a1, b1], axis=2), np.stack([a, b1, b], axis=2)], axis=1).reshape(-1, 3, 3)
    caps = []
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        c = np.broadcast_to(ring.mean(axis=0), ring.shape)
        tri = np.stack([c, ring, np.roll(ring, -1, axis=0)], axis=1)
        caps.append(tri[:, ::-1] if flip else tri)
    return np.concatenate([side, *caps])


def sphere(diameter: float = 1.0, centre_height: float = 2.5, n: int = 48) -> Body:
    """A UV sphere whose centre sits `centre_height` diameters above the tunnel floor."""
    r = diameter / 2
    zc = centre_height * diameter
    theta = np.linspace(0, np.pi, n + 1)[1:-1]  # polar angle from the upstream pole (x axis)
    phi = np.linspace(0, 2 * np.pi, 2 * n, endpoint=False)
    rings = np.stack([
        np.stack([r - r * np.cos(t) + 0 * phi, r * np.sin(t) * np.cos(phi), zc + r * np.sin(t) * np.sin(phi)], axis=1)
        for t in theta
    ])
    tris = _tube(rings)  # the end caps sit within 0.3 % of a radius of the poles
    return Body(tris, diameter * 1000, diameter * 1000, (zc + r) * 1000, [], "sphere")


# Ahmed, Ramm & Faltin (1984), SAE 840300: the standard simplified-car benchmark.
AHMED = {"length": 1.044, "width": 0.389, "height": 0.288, "front_radius": 0.100, "slant_length": 0.222,
         "clearance": 0.050}


def ahmed_body(slant_deg: float, stations: int = 90, per_edge: int = 10) -> Body:
    """Ahmed body with a rear slant of `slant_deg`, on the road at 50 mm clearance (stilts omitted)."""
    a = AHMED
    L, R = a["length"], a["front_radius"]
    phi = np.radians(slant_deg)
    slant_x = a["slant_length"] * np.cos(phi)
    u = np.linspace(0, 1, stations)
    xs = np.unique(np.concatenate([R * (1 - np.cos(u * np.pi / 2)), np.linspace(R, L, stations)]))
    rings = []
    for x in xs:
        inset = R - np.sqrt(max(R * R - (R - x) ** 2, 0.0)) if x < R else 0.0  # R100 front edges
        hw = a["width"] / 2 - inset
        zb = a["clearance"] + inset
        zt = a["clearance"] + a["height"] - inset - max(0.0, x - (L - slant_x)) * np.tan(phi)
        t = np.linspace(0, 1, per_edge, endpoint=False)
        ring = np.concatenate([
            np.stack([np.full_like(t, x), -hw + 2 * hw * t, np.full_like(t, zb)], axis=1),  # floor, left → right
            np.stack([np.full_like(t, x), np.full_like(t, hw), zb + (zt - zb) * t], axis=1),  # right side up
            np.stack([np.full_like(t, x), hw - 2 * hw * t, np.full_like(t, zt)], axis=1),  # top, right → left
            np.stack([np.full_like(t, x), np.full_like(t, -hw), zt - (zt - zb) * t], axis=1),  # left side down
        ])
        rings.append(ring)
    tris = _tube(np.array(rings))
    return Body(tris, L * 1000, a["width"] * 1000, (a["clearance"] + a["height"]) * 1000, [], "ahmed")
