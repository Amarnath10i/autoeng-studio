"""What-if engine (spec §14, §17): what happens if I change this?

Both designs are simulated with the same random streams, so differences come from
the change and not from sampling noise. The result explains the change three ways:
the declared propagation path through the models, the size of the change in every
physical quantity, and how each component's limits moved.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from autoeng import vcs
from autoeng.analysis import limits as lim
from autoeng.analysis.propagation import trace
from autoeng.analysis.simulate import simulate
from autoeng.domain.components import CHANNELS, COMPONENTS
from autoeng.domain.engine_design import EngineDesign
from autoeng.domain.materials import Material

SIGNIFICANT_REL = 0.005  # changes under 0.5 % are reported as "no significant change"

HEADLINE = [
    ("peak_power", "Peak power", "kW"),
    ("peak_torque", "Peak torque", "N·m"),
    ("max_boost", "Max boost", "bar"),
    ("max_peak_pressure", "Peak cylinder pressure", "bar"),
    ("max_egt", "Max turbine inlet temp.", "°C"),
    ("max_heat_to_coolant", "Max heat to coolant", "kW"),
    ("max_injector_duty", "Max injector duty", "-"),
    ("min_bsfc", "Best BSFC", "g/kWh"),
    ("recip_mass_g", "Reciprocating mass", "g"),
]


def _rel(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return (b - a) / abs(a)


def _channel_change(before: list, after: list) -> dict:
    a = np.array([np.nan if v is None else v for v in before], dtype=float)
    b = np.array([np.nan if v is None else v for v in after], dtype=float)
    with np.errstate(all="ignore"):
        max_a, max_b = np.nanmax(a), np.nanmax(b)
        delta = b - a
        i = int(np.nanargmax(np.abs(delta))) if np.isfinite(delta).any() else 0
        scale = max(abs(max_a), abs(max_b), 1e-12)
    return {
        "max_before": float(max_a),
        "max_after": float(max_b),
        "max_rel_change": _rel(float(max_a), float(max_b)),
        "largest_delta": float(delta[i]) if np.isfinite(delta[i]) else 0.0,
        "largest_delta_index": i,
        "significant": bool(np.nanmax(np.abs(delta)) / scale > SIGNIFICANT_REL) if np.isfinite(delta).any() else False,
    }


def compare(
    baseline: EngineDesign,
    variant: EngineDesign,
    materials: Mapping[str, Material],
    samples: int = 200,
    seed: int = 42,
) -> dict:
    base_res = simulate(baseline, materials, samples, seed)
    var_res = simulate(variant, materials, samples, seed)
    if base_res["rpm"] != var_res["rpm"]:
        rpm_note = "The rpm sweeps differ; curve-by-curve changes compare points by index."
    else:
        rpm_note = None

    changes = vcs.diff(baseline.model_dump(mode="json"), variant.model_dump(mode="json"))
    physical = [c["path"] for c in changes if not c["path"].startswith(("limits[", "targets.", "name", "description"))]
    for c in changes:
        c["label"] = _change_label(c["path"])

    channel_changes = {}
    for name in CHANNELS:
        if name == "rpm":
            continue
        channel_changes[name] = _channel_change(base_res["channels"][name]["nominal"], var_res["channels"][name]["nominal"])

    steps = trace(physical)
    for step in steps:
        step["output_changes"] = {
            o: channel_changes[o]["max_rel_change"] for o in step["outputs"] if o in channel_changes
        }

    headline = []
    for key, label, unit in HEADLINE:
        a, b = base_res["summary"][key], var_res["summary"][key]
        headline.append({
            "key": key, "label": label, "unit": unit,
            "before": a, "after": b,
            "delta": b["nominal"] - a["nominal"],
            "rel": _rel(a["nominal"], b["nominal"]),
        })

    base_limits = {r["id"]: r for r in base_res["limits"]}
    var_limits = {r["id"]: r for r in var_res["limits"]}
    limit_changes = []
    for lid in sorted(set(base_limits) | set(var_limits)):
        a, b = base_limits.get(lid), var_limits.get(lid)
        ref = b or a
        sa, sb = (a or {}).get("status", "no_data"), (b or {}).get("status", "no_data")
        limit_changes.append({
            "id": lid,
            "component": ref["component"],
            "label": ref["label"],
            "unit": ref["unit"],
            "status_before": sa,
            "status_after": sb,
            "sf_before": (a or {}).get("sf_nominal"),
            "sf_after": (b or {}).get("sf_nominal"),
            "actual_before": (a or {}).get("actual_nominal"),
            "actual_after": (b or {}).get("actual_nominal"),
            "worsened": lim.STATUS_ORDER.index(sb) > lim.STATUS_ORDER.index(sa),
            "improved": lim.STATUS_ORDER.index(sb) < lim.STATUS_ORDER.index(sa),
        })

    components = []
    for cid, comp in COMPONENTS.items():
        changed = [
            {"channel": ch, "label": CHANNELS[ch].label, "unit": CHANNELS[ch].unit, **channel_changes[ch]}
            for ch in comp.channels if ch in channel_changes and channel_changes[ch]["significant"]
        ]
        param_changed = any(any(p.startswith(prefix) for prefix in comp.params) for p in physical)
        if not changed and not param_changed:
            continue
        components.append({
            "id": cid,
            "name": comp.name,
            "system": comp.system,
            "status_before": base_res["component_status"][cid],
            "status_after": var_res["component_status"][cid],
            "directly_modified": param_changed,
            "changed_channels": changed,
            "limits": [lc for lc in limit_changes if lc["component"] == cid],
        })

    # Limiting components after the change: lowest nominal safety factor first.
    limiting = sorted(
        (lc for lc in limit_changes if lc["sf_after"] is not None),
        key=lambda lc: lc["sf_after"],
    )[:5]

    return {
        "changes": changes,
        "propagation": steps,
        "headline": headline,
        "channel_changes": channel_changes,
        "components": components,
        "limit_changes": limit_changes,
        "limiting": limiting,
        "newly_limiting": [lc for lc in limit_changes if lc["worsened"]],
        "baseline": base_res,
        "variant": var_res,
        "notes": [n for n in [rpm_note] if n] + [
            "Both designs were simulated with identical random streams (common random numbers), so the "
            "differences reflect the change, not sampling noise.",
        ],
    }


def _change_label(path: str) -> str:
    from autoeng.domain.engine_design import PARAM_SPECS

    if "limits[" in path:
        return f"Limit '{path.split('limits[')[1][:-1]}'"
    spec = PARAM_SPECS.get(path)
    return spec.label if spec else path
