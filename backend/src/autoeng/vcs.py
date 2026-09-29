"""Design version-control primitives (spec §22): flatten, diff and three-way merge.

A design is flattened into {path: leaf}. `Param` dicts are leaves (their value,
source and tolerance change together), and limits are keyed by their id, so
reordering limits is not a change.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

MISSING = object()


def _is_param(node: Any) -> bool:
    return isinstance(node, dict) and "value" in node and "source" in node


def flatten(design: dict, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, node in design.items():
        path = f"{prefix}{key}"
        if key == "limits" and isinstance(node, list):
            for limit in node:
                out[f"{prefix}limits[{limit['id']}]"] = limit
        elif _is_param(node) or not isinstance(node, dict):
            out[path] = node
        else:
            out.update(flatten(node, f"{path}."))
    return out


def unflatten(flat: dict[str, Any]) -> dict:
    out: dict = {}
    for path, value in sorted(flat.items()):
        node = out
        *parents, leaf = path.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        if leaf.startswith("limits["):
            node.setdefault("limits", []).append(value)
        else:
            node[leaf] = value
    return out


def canonical_hash(design: dict) -> str:
    return hashlib.sha256(json.dumps(design, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def diff(a: dict, b: dict) -> list[dict]:
    fa, fb = flatten(a), flatten(b)
    changes = []
    for path in sorted(set(fa) | set(fb)):
        va, vb = fa.get(path, MISSING), fb.get(path, MISSING)
        if va == vb:
            continue
        kind = "added" if va is MISSING else "removed" if vb is MISSING else "changed"
        changes.append({
            "path": path,
            "kind": kind,
            "before": None if va is MISSING else va,
            "after": None if vb is MISSING else vb,
        })
    return changes


def merge3(base: dict, ours: dict, theirs: dict) -> tuple[dict, list[dict]]:
    """Three-way merge. Returns (merged design, conflicts). Ours wins nothing silently:
    a path changed differently on both sides is a conflict and keeps our value."""
    fb, fo, ft = flatten(base), flatten(ours), flatten(theirs)
    merged: dict[str, Any] = {}
    conflicts = []
    for path in sorted(set(fb) | set(fo) | set(ft)):
        b, o, t = fb.get(path, MISSING), fo.get(path, MISSING), ft.get(path, MISSING)
        if o == t:
            result = o
        elif o == b:
            result = t
        elif t == b:
            result = o
        else:
            conflicts.append({"path": path, "base": _none(b), "ours": _none(o), "theirs": _none(t)})
            result = o
        if result is not MISSING:
            merged[path] = result
    return unflatten(merged), conflicts


def _none(v: Any) -> Any:
    return None if v is MISSING else v
