"""Virtual wind tunnel: 3D lattice-Boltzmann flow around a vehicle body (fidelity level 3).

Solver: D3Q19 lattice, BGK collision with a Smagorinsky sub-grid model (LES) for
stability at higher Reynolds numbers, full-way bounce-back on the body and
wheels, equilibrium inlet and far-field boundaries, zero-gradient outlet and a
moving road (the ground moves at the free-stream speed, as in a rolling-road wind
tunnel). Forces come from momentum exchange at the body surface.

Honest scope: the lattice Reynolds number is 10³-10⁴, far below a real car
(~10⁶-10⁷), and the body is a voxelised sketch. Absolute Cd values are therefore
indicative only; the tool is built for comparing shapes and for seeing where the
flow separates, stagnates and forms a wake.
"""

from __future__ import annotations

import time

import numpy as np

from autoeng import compute

MODEL_ID = "aero.lbm_d3q19_les"
MODEL_VERSION = "1.0.0"
FIDELITY_LEVEL = 3

# D3Q19 lattice: velocity set (cx, cy, cz) and weights.
C = np.array(
    [(0, 0, 0),
     (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
     (1, 1, 0), (-1, -1, 0), (1, -1, 0), (-1, 1, 0),
     (1, 0, 1), (-1, 0, -1), (1, 0, -1), (-1, 0, 1),
     (0, 1, 1), (0, -1, -1), (0, 1, -1), (0, -1, 1)], dtype=np.int64)
W = np.array([1 / 3] + [1 / 18] * 6 + [1 / 36] * 12, dtype=np.float32)
OPP = np.array([int(np.where((-c == C).all(axis=1))[0][0]) for c in C])

RESOLUTIONS = {
    # cells along the car, lattice speed, Reynolds number, flow-throughs simulated
    "draft": {"cells": 36, "u": 0.08, "re": 1200, "flow_throughs": 1.3},
    "standard": {"cells": 72, "u": 0.06, "re": 3000, "flow_throughs": 1.5},
    "fine": {"cells": 104, "u": 0.05, "re": 5000, "flow_throughs": 1.6},
}

ASSUMPTIONS = [
    "3D lattice-Boltzmann (D3Q19) with Smagorinsky LES, incompressible regime (lattice Mach < 0.15).",
    "Lattice Reynolds number 10³-10⁴, far below a real car (10⁶-10⁷): boundary layers are too thick and separation "
    "can differ from reality. Use results to compare shapes and study flow structure, not as a certified Cd.",
    "Body voxelised from the side-profile and front-section sketches (staircase surface); mirrors, underbody detail, "
    "cooling flow and wheel rotation are not modelled.",
    "Moving road at free-stream speed; inlet, top and sides held at free-stream equilibrium; zero-gradient outlet. "
    "Blockage from the finite tunnel is not corrected.",
    "Cd and Cl are referenced to the voxelised frontal area and averaged over the last 30 % of the run.",
]


def _catmull_rom(points: np.ndarray, per_segment: int = 16) -> np.ndarray:
    out = []
    n = len(points)
    for i in range(n - 1):
        p0, p1, p2, p3 = points[max(i - 1, 0)], points[i], points[i + 1], points[min(i + 2, n - 1)]
        for t in np.linspace(0, 1, per_segment, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(points[-1])
    return np.array(out)


def voxelize(g, cells_along: int) -> dict:
    """Solid mask (nz, ny, nx) for the body and wheels inside a tunnel sized around the car."""
    L, Wd, H = g.length_mm / 1000, g.width_mm / 1000, g.height_mm / 1000
    gc = g.ground_clearance_mm / 1000
    dx = L / cells_along
    nx = int(round(3.4 * cells_along))
    ny = int(round(Wd * 2.8 / dx)) // 2 * 2
    nz = int(round(H * 2.6 / dx))
    x0 = 0.9 * L  # car nose position from the inlet
    xs = (np.arange(nx) + 0.5) * dx - x0
    ys = (np.arange(ny) + 0.5) * dx - ny * dx / 2
    zs = (np.arange(nz) + 0.5) * dx
    Z, Y, X = np.meshgrid(zs, ys, xs, indexing="ij")

    side = _catmull_rom(np.array(sorted(g.side_profile, key=lambda p: p[0]), dtype=float))
    top = np.interp(np.clip(xs / L, 0, 1), side[:, 0], gc + side[:, 1] * (H - gc))
    top[(xs < side[0, 0] * L) | (xs > side[-1, 0] * L)] = -1.0
    section = _catmull_rom(np.array(g.front_section, dtype=float))
    zbins = np.linspace(0, 1, 41)
    halfw = np.array([section[np.abs(section[:, 1] - zb) < 0.05, 0].max(initial=0.0) for zb in zbins])
    zn = np.clip((Z - gc) / (H - gc), 0, 1)
    xn = np.clip(X / L, 0, 1)
    taper = 1 - 0.16 * np.abs(2 * xn - 1) ** 4
    width_here = (Wd / 2) * np.interp(zn, zbins, halfw) * taper
    solid = (X >= 0) & (X <= L) & (gc <= Z) & (top[None, None, :] >= Z) & (np.abs(Y) <= width_here)

    r = g.wheel_diameter_mm / 2000
    wheel_w = 0.24
    for ax in (g.front_overhang_mm / 1000, (g.front_overhang_mm + g.wheelbase_mm) / 1000):
        for side_y in (-1, 1):
            yc = side_y * (Wd / 2 - wheel_w / 2)
            solid |= ((X - ax) ** 2 + (Z - r) ** 2 <= r**2) & (np.abs(Y - yc) <= wheel_w / 2)
    return {"solid": solid, "dx": dx, "nx": nx, "ny": ny, "nz": nz, "x0": x0, "xs": xs, "ys": ys, "zs": zs}


_CUDA_SOURCE = r"""
__constant__ int CX[19] = {0,1,-1,0,0,0,0,1,-1,1,-1,1,-1,1,-1,0,0,0,0};
__constant__ int CY[19] = {0,0,0,1,-1,0,0,1,-1,-1,1,0,0,0,0,1,-1,1,-1};
__constant__ int CZ[19] = {0,0,0,0,0,1,-1,0,0,0,0,1,-1,-1,1,1,-1,-1,1};
__constant__ int OPPOSITE[19] = {0,2,1,4,3,6,5,8,7,10,9,12,11,14,13,16,15,18,17};
__constant__ float WT[19] = {1.f/3,1.f/18,1.f/18,1.f/18,1.f/18,1.f/18,1.f/18,
                             1.f/36,1.f/36,1.f/36,1.f/36,1.f/36,1.f/36,1.f/36,1.f/36,1.f/36,1.f/36,1.f/36,1.f/36};

extern "C" __global__
void collide_stream(const float* __restrict__ f, float* __restrict__ fnew, const unsigned char* __restrict__ solid,
                    const int nx, const int ny, const int nz, const float tau0, const float smag)
{
    const int n = blockDim.x * blockIdx.x + threadIdx.x;
    const int N = nx * ny * nz;
    if (n >= N) return;
    const int x = n % nx, y = (n / nx) % ny, z = n / (nx * ny);
    float fi[19], post[19];
    #pragma unroll
    for (int i = 0; i < 19; i++) fi[i] = f[i * N + n];
    if (solid[n]) {
        #pragma unroll
        for (int i = 0; i < 19; i++) post[i] = fi[OPPOSITE[i]];     // full-way bounce-back
    } else {
        float rho = 0.f, ux = 0.f, uy = 0.f, uz = 0.f;
        #pragma unroll
        for (int i = 0; i < 19; i++) { rho += fi[i]; ux += CX[i] * fi[i]; uy += CY[i] * fi[i]; uz += CZ[i] * fi[i]; }
        ux /= rho; uy /= rho; uz /= rho;
        const float usq = 1.5f * (ux * ux + uy * uy + uz * uz);
        float feq[19];
        float pxx = 0.f, pyy = 0.f, pzz = 0.f, pxy = 0.f, pxz = 0.f, pyz = 0.f;
        #pragma unroll
        for (int i = 0; i < 19; i++) {
            const float cu = 3.f * (CX[i] * ux + CY[i] * uy + CZ[i] * uz);
            feq[i] = WT[i] * rho * (1.f + cu + 0.5f * cu * cu - usq);
            const float neq = fi[i] - feq[i];
            pxx += CX[i] * CX[i] * neq; pyy += CY[i] * CY[i] * neq; pzz += CZ[i] * CZ[i] * neq;
            pxy += CX[i] * CY[i] * neq; pxz += CX[i] * CZ[i] * neq; pyz += CY[i] * CZ[i] * neq;
        }
        const float pi = sqrtf(pxx * pxx + pyy * pyy + pzz * pzz + 2.f * (pxy * pxy + pxz * pxz + pyz * pyz));
        const float tau = 0.5f * (tau0 + sqrtf(tau0 * tau0 + smag * pi / rho));   // Smagorinsky LES
        #pragma unroll
        for (int i = 0; i < 19; i++) post[i] = fi[i] - (fi[i] - feq[i]) / tau;
    }
    #pragma unroll
    for (int i = 0; i < 19; i++) {                                   // push streaming (periodic wrap; boundaries reset after)
        const int xn = (x + CX[i] + nx) % nx, yn = (y + CY[i] + ny) % ny, zn = (z + CZ[i] + nz) % nz;
        fnew[i * N + (zn * ny + yn) * nx + xn] = post[i];
    }
}
"""
_KERNEL = None


def _cuda_kernel():
    """Compile the fused collide-and-stream kernel once per process."""
    global _KERNEL
    if _KERNEL is None:
        import cupy

        _KERNEL = cupy.RawKernel(_CUDA_SOURCE, "collide_stream")
    return _KERNEL


def run(g, resolution: str = "standard", progress=None) -> dict:
    if resolution not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of {', '.join(RESOLUTIONS)}")
    cfg = RESOLUTIONS[resolution]
    vox = voxelize(g, cfg["cells"])
    nx, ny, nz = vox["nx"], vox["ny"], vox["nz"]
    n_cells = nx * ny * nz
    xp = compute.for_size(n_cells * 19)
    dev = compute.describe(xp)
    started = time.perf_counter()
    f32 = xp.float32

    U = float(cfg["u"])
    nu = U * cfg["cells"] / cfg["re"]
    tau0 = 3 * nu + 0.5
    smag = 18 * 1.41421356 * 0.17**2
    steps = int(cfg["flow_throughs"] * nx / U)
    avg_from = int(steps * 0.7)

    solid_np = vox["solid"]
    sidx = xp.asarray(np.flatnonzero(solid_np.ravel()))
    cmat = xp.asarray(C.astype(np.float32))  # (19, 3)
    ct = cmat.T.copy()  # (3, 19)
    q6 = xp.asarray(np.stack([C[:, 0] ** 2, C[:, 1] ** 2, C[:, 2] ** 2,
                              C[:, 0] * C[:, 1], C[:, 0] * C[:, 2], C[:, 1] * C[:, 2]]).astype(np.float32))
    w = xp.asarray(W)[:, None]
    opp = xp.asarray(OPP)

    def feq(rho, u):
        cu = 3.0 * (cmat @ u)
        return w * rho * (1.0 + cu + 0.5 * cu * cu - 1.5 * (u * u).sum(0))

    free_u = xp.asarray(np.array([[U], [0.0], [0.0]], dtype=np.float32))
    f_free = feq(xp.ones((1,), dtype=f32), free_u)[:, 0]  # (19,)
    ff = f_free.reshape(19, 1, 1)
    f = xp.empty((19, nz, ny, nx), dtype=f32)
    f[:] = f_free.reshape(19, 1, 1, 1)
    f.reshape(19, -1)[:, sidx] = w
    post = xp.empty_like(f)

    # Momentum exchange: for each direction, body cells whose upstream neighbour is fluid.
    fluid_np = ~solid_np
    incoming = []
    for i in range(1, 19):
        if C[i, 0] == 0 and C[i, 2] == 0:
            continue
        mask = solid_np & np.roll(fluid_np, shift=(int(C[i, 2]), int(C[i, 1]), int(C[i, 0])), axis=(0, 1, 2))
        mask[:2] = False  # the tyre contact patch touches the moving road: exclude it from the aero force
        incoming.append((i, xp.asarray(np.flatnonzero(mask.ravel()))))
    frontal = float(solid_np.any(axis=2).sum())  # cells projected on the (z, y) plane
    q = 0.5 * U * U

    history = []
    u_sum = xp.zeros((3, n_cells), dtype=f32)
    rho_sum = xp.zeros((n_cells,), dtype=f32)
    n_avg = 0
    fx_acc = fz_acc = 0.0
    n_force = 0

    fused = None
    if xp is not np:
        try:
            fused = _cuda_kernel()
            solid_dev = xp.asarray(solid_np.astype(np.uint8))
            threads = 256
            blocks = (n_cells + threads - 1) // threads
        except Exception:  # noqa: BLE001 - fall back to the array implementation
            fused = None
    dev["kernel"] = "fused CUDA collide-stream" if fused is not None else "array operations"

    def macroscopic(f2):
        rho = f2.sum(0)
        u = (ct @ f2) / rho
        u[:, sidx] = 0.0
        return rho, u

    for step in range(steps):
        averaging = step >= avg_from and step % 5 == 0
        if fused is not None:
            fused((blocks,), (threads,), (f, post, solid_dev, np.int32(nx), np.int32(ny), np.int32(nz),
                                          np.float32(tau0), np.float32(smag)))
            f, post = post, f
            if averaging:
                rho, u = macroscopic(f.reshape(19, -1))
        else:
            f2 = f.reshape(19, -1)
            rho, u = macroscopic(f2)
            fe = feq(rho, u)
            neq = f2 - fe
            p6 = q6 @ neq
            pi = xp.sqrt(p6[0] ** 2 + p6[1] ** 2 + p6[2] ** 2 + 2.0 * (p6[3] ** 2 + p6[4] ** 2 + p6[5] ** 2))
            tau = 0.5 * (tau0 + xp.sqrt(tau0 * tau0 + smag * pi / rho))
            p2 = post.reshape(19, -1)
            xp.subtract(f2, neq / tau, out=p2)
            p2[:, sidx] = f2[:, sidx][opp]  # full-way bounce-back on the body
            for i in range(19):
                f[i] = xp.roll(post[i], shift=(int(C[i, 2]), int(C[i, 1]), int(C[i, 0])), axis=(0, 1, 2))

        # Free stream at inlet, sides and top; moving road; open outlet.
        f[:, :, :, 0] = ff
        f[:, :, :, -1] = f[:, :, :, -2]
        f[:, -1, :, :] = ff
        f[:, :, 0, :] = ff
        f[:, :, -1, :] = ff
        f[:, 0, :, :] = ff

        if step % 10 == 0:
            f2 = f.reshape(19, -1)
            fx = fz = 0.0
            for i, idx in incoming:
                # Gauge form: subtract the rest population so the open contact patch adds no pressure force.
                s_i = 2.0 * (float(f2[i, idx].sum()) - float(W[i]) * int(idx.size))
                fx += C[i, 0] * s_i
                fz += C[i, 2] * s_i
            if not np.isfinite(fx):
                raise RuntimeError("The flow solution became unstable; try a coarser resolution")
            history.append({"step": step, "cd": fx / (q * frontal), "cl": fz / (q * frontal)})
            if step >= avg_from:
                fx_acc += fx
                fz_acc += fz
                n_force += 1
            if progress and step % 200 == 0:
                progress(step / steps)
        if averaging:
            u_sum += u
            rho_sum += rho
            n_avg += 1

    u_avg = compute.to_numpy(u_sum / max(n_avg, 1)).reshape(3, nz, ny, nx)
    rho_avg = compute.to_numpy(rho_sum / max(n_avg, 1)).reshape(nz, ny, nx)
    cd = fx_acc / max(n_force, 1) / (q * frontal)
    cl = fz_acc / max(n_force, 1) / (q * frontal)
    return _package(g, vox, u_avg, rho_avg, solid_np, U, cd, cl, history, frontal, cfg, resolution, steps,
                    time.perf_counter() - started, dev)


def _package(g, vox, u, rho, solid, U, cd, cl, history, frontal, cfg, resolution, steps, seconds, dev) -> dict:
    dx, x0 = vox["dx"], vox["x0"]
    nz, ny, nx = solid.shape
    speed = np.sqrt((u**2).sum(axis=0)) / U
    cp = (rho - 1.0) / 3.0 / (0.5 * U * U)

    def slice_(arr2d, stride):
        # Cells inside the body become null so the result stays valid JSON.
        a = np.round(arr2d[::stride, ::stride], 3)
        return [[None if not np.isfinite(v) else float(v) for v in row] for row in a]

    stride = max(1, nx // 220)
    jmid = ny // 2
    kmid = int(np.clip((g.height_mm / 1000 * 0.45) / dx, 1, nz - 2))
    centre = {"speed": slice_(np.where(solid[:, jmid, :], np.nan, speed[:, jmid, :]), stride),
              "cp": slice_(np.where(solid[:, jmid, :], np.nan, cp[:, jmid, :]), stride)}
    plan = {"speed": slice_(np.where(solid[kmid], np.nan, speed[kmid]), stride)}

    # Surface pressure: fluid cells touching the body.
    touching = np.zeros_like(solid)
    for i in range(1, 7):
        touching |= np.roll(solid, shift=(int(C[i, 2]), int(C[i, 1]), int(C[i, 0])), axis=(0, 1, 2))
    surface = touching & ~solid
    kk, jj, ii = np.nonzero(surface)
    keep = np.linspace(0, len(ii) - 1, min(len(ii), 6000)).astype(int) if len(ii) else np.array([], dtype=int)
    surf = {
        "x": np.round((ii[keep] + 0.5) * dx - x0, 3).tolist(),
        "y": np.round((jj[keep] + 0.5) * dx - ny * dx / 2, 3).tolist(),
        "z": np.round((kk[keep] + 0.5) * dx, 3).tolist(),
        "cp": np.round(cp[kk[keep], jj[keep], ii[keep]], 3).tolist(),
    }

    lines = _streamlines(u, solid, dx, x0, g, U)
    finite = np.nan_to_num(speed, nan=0.0)
    return {
        "cd": cd,
        "cl": cl,
        "history": history,
        "frontal_area_m2": frontal * dx * dx,
        "grid": {"nx": nx, "ny": ny, "nz": nz, "cells": nx * ny * nz, "dx_m": dx, "steps": steps,
                 "reynolds": cfg["re"], "resolution": resolution},
        "slices": {"centre_plane": centre, "plan_view": plan, "stride": stride, "dx_m": dx, "x0_m": x0,
                   "plan_height_m": (kmid + 0.5) * dx, "extent_x_m": nx * dx, "extent_y_m": ny * dx, "extent_z_m": nz * dx},
        "surface_pressure": surf,
        "streamlines": lines,
        "max_speed_ratio": float(finite.max()),
        "seconds": round(seconds, 1),
        "compute": dev,
        "model": {"id": MODEL_ID, "version": MODEL_VERSION, "fidelity_level": FIDELITY_LEVEL,
                  "name": "3D lattice-Boltzmann wind tunnel"},
        "assumptions": ASSUMPTIONS,
    }


def _trilinear(u, p):
    """Sample a (3, nz, ny, nx) field at fractional (z, y, x) cell coordinates."""
    _, nz, ny, nx = u.shape
    z, y, x = np.clip(p[0], 0, nz - 1.001), np.clip(p[1], 0, ny - 1.001), np.clip(p[2], 0, nx - 1.001)
    k, j, i = int(z), int(y), int(x)
    dz, dy, dx = z - k, y - j, x - i
    c = u[:, k:k + 2, j:j + 2, i:i + 2]
    wz = np.array([1 - dz, dz])[:, None, None]
    wy = np.array([1 - dy, dy])[None, :, None]
    wx = np.array([1 - dx, dx])[None, None, :]
    return (c * (wz * wy * wx)).sum(axis=(1, 2, 3))


def _streamlines(u, solid, dx, x0, g, U, max_lines: int = 64) -> list[dict]:
    _, nz, ny, nx = u.shape
    W, H = g.width_mm / 1000, g.height_mm / 1000
    lines = []
    ys = np.linspace(-0.55 * W, 0.55 * W, 8)
    zs = np.linspace(0.12, 1.2 * H, 8)
    for zc in zs:
        for yc in ys:
            if len(lines) >= max_lines:
                break
            p = np.array([zc / dx, yc / dx + ny / 2, 2.0])
            pts, spd = [], []
            for n_step in range(int(3 * nx)):
                k, j, i = int(p[0]), int(p[1]), int(p[2])
                if not (0 <= k < nz - 1 and 0 <= j < ny - 1 and 0 <= i < nx - 1) or solid[k, j, i]:
                    break
                v1 = _trilinear(u, p)
                vel = np.array([v1[2], v1[1], v1[0]])  # to (z, y, x) order
                mag = np.linalg.norm(vel)
                if mag < 1e-5:
                    break
                mid = p + 0.35 * vel / mag
                v2 = _trilinear(u, mid)
                vel2 = np.array([v2[2], v2[1], v2[0]])
                p = p + 0.7 * vel2 / max(np.linalg.norm(vel2), 1e-9)
                if n_step % 3 == 0:
                    pts.append([round((p[2] + 0.5) * dx - x0, 3), round((p[1] + 0.5) * dx - ny * dx / 2, 3),
                                round((p[0] + 0.5) * dx, 3)])
                    spd.append(round(float(mag / U), 3))
            if len(pts) > 4:
                lines.append({"points": pts, "speed": spd})
    return lines
