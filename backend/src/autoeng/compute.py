"""Compute backend selection: NumPy on CPU, or CuPy on an NVIDIA GPU.

Physics modules do array maths through `xp`, which is NumPy or CuPy (CuPy mirrors
the NumPy API). Selection is by the AUTOENG_COMPUTE environment variable:

  auto   (default) use the GPU when CuPy and a CUDA device are available, else CPU
  gpu    require the GPU; fail loudly if unavailable
  cpu    always NumPy

Monte Carlo ensembles, parameter sweeps and optimisation are where the GPU pays
off; a single nominal run is faster on the CPU, so `for_size` falls back to NumPy
for small arrays.
"""

from __future__ import annotations

import os
import warnings
from functools import cache
from types import ModuleType

import numpy

GPU_MIN_ELEMENTS = 50_000


@cache
def _gpu() -> tuple[ModuleType | None, str | None]:
    mode = os.environ.get("AUTOENG_COMPUTE", "auto").lower()
    if mode == "cpu":
        return None, None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # CuPy warns about CUDA_PATH even when pip CUDA wheels work
            import cupy  # type: ignore[import-not-found]

        if cupy.cuda.runtime.getDeviceCount() < 1:
            raise RuntimeError("no CUDA device")
        props = cupy.cuda.runtime.getDeviceProperties(0)
        name = props["name"].decode() if isinstance(props["name"], bytes) else str(props["name"])
        cupy.zeros(1).sum()  # fail here, not mid-simulation, if the driver/runtime is broken
        return cupy, name
    except Exception as exc:  # noqa: BLE001 - any CuPy/CUDA failure means "no GPU"
        if mode == "gpu":
            raise RuntimeError(f"AUTOENG_COMPUTE=gpu but the GPU is unavailable: {exc}") from exc
        return None, None


def gpu_available() -> bool:
    return _gpu()[0] is not None


def for_size(elements: int) -> ModuleType:
    """Array module to use for a workload of roughly `elements` array entries."""
    cp, _ = _gpu()
    if cp is not None and (elements >= GPU_MIN_ELEMENTS or os.environ.get("AUTOENG_COMPUTE", "").lower() == "gpu"):
        return cp
    return numpy


def ns(*arrays) -> ModuleType:
    """The array module that owns `arrays` (CuPy if any is a GPU array)."""
    for a in arrays:
        if type(a).__module__.startswith("cupy"):
            return _gpu()[0]
    return numpy


def to_numpy(a):
    if hasattr(a, "get"):
        return a.get()
    return numpy.asarray(a)


def describe(xp: ModuleType) -> dict:
    cp, name = _gpu()
    if cp is not None and xp is cp:
        return {"backend": "cupy", "device": name}
    return {"backend": "numpy", "device": "CPU"}


def status() -> dict:
    cp, name = _gpu()
    return {
        "mode": os.environ.get("AUTOENG_COMPUTE", "auto").lower(),
        "gpu_available": cp is not None,
        "gpu_device": name,
        "gpu_min_elements": GPU_MIN_ELEMENTS,
    }
