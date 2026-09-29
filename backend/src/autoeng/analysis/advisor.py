"""Upgrade advisor (spec §2, §18): "what must change to reach this target?"

For a power target the advisor evaluates alternative strategies, each a concrete
candidate design, and reports for each: the boost needed, the resulting curves,
the probability of meeting the target, and every component whose documented
allowable would need to rise, with the rating it would need. Strategies are
shown side by side; the advisor does not declare one "best" (spec §18).

Only levers the physics captures are offered. Fuel changes such as E85 are
deliberately not proposed: their main benefit (knock resistance and charge
cooling) is not modelled yet, so the comparison would mislead.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from autoeng.analysis import limits as lim
from autoeng.analysis.simulate import run_raw, simulate
from autoeng.core.params import P, Source
from autoeng.domain.engine_design import PARAM_SPECS, EngineDesign
from autoeng.domain.materials import Material

BOOST_CAP = 3.5  # bar gauge; search ceiling, well inside the parameter range
TURBINE_SCALES = (1.0, 1.2, 1.4, 1.7, 2.0)


def _with(design: EngineDesign, boost: float, turbine_area: float, target_kw: float) -> EngineDesign:
    d = design.model_dump()
    d["turbo"]["boost_target"]["value"] = round(boost, 3)
    d["turbo"]["turbine_flow_area"]["value"] = round(turbine_area, 2)
    d["targets"]["peak_power"] = P(target_kw, Source.USER).model_dump()
    return EngineDesign.model_validate(d)


def _peak_power(design: EngineDesign, materials, boost: float, area: float) -> float:
    run = run_raw(_with(design, boost, area, 1.0), materials, 1, 0)
    return float(np.nanmax(run.channels["power"][0]))


def _solve_boost(design, materials, area: float, target_kw: float) -> float | None:
    """Smallest boost target (bar) whose nominal peak power reaches the target, or None."""
    lo = 0.0
    if _peak_power(design, materials, BOOST_CAP, area) < target_kw:
        return None
    hi = BOOST_CAP
    for _ in range(18):  # ~1e-5 bar resolution
        mid = 0.5 * (lo + hi)
        if _peak_power(design, materials, mid, area) >= target_kw:
            hi = mid
        else:
            lo = mid
    return hi


def _upgrades(design: EngineDesign, res: dict) -> list[dict]:
    items = []
    for r in res["limits"]:
        if r["status"] in ("ok", "no_data"):
            continue
        item = {
            "limit_id": r["id"],
            "component": r["component"],
            "label": r["label"],
            "unit": r["unit"],
            "status": r["status"],
            "sf_nominal": r["sf_nominal"],
            "current_allowable": r["allowable_nominal"],
        }
        if r["kind"] == "limit" and r["actual_p95"] is not None:
            ref = r["reference"]
            item["required_allowable"] = ref + (r["actual_p95"] - ref) * r["warning_sf"]
            item["action"] = f"Needs a documented rating of at least {item['required_allowable']:.3g} {r['unit']}"
            if r["id"] == "injectors" or r.get("channel") == "injector_duty":
                flow = design.fuel.injector_flow.value * r["actual_p95"] / r["allowable_nominal"]
                item["action"] = f"Injectors of at least {flow:.0f} cc/min each (or more injectors) to stay under {r['allowable_nominal']:.0%} duty"
                item["required_injector_flow"] = flow
        else:
            item["action"] = "Stronger material or larger section; see the material comparison below"
        items.append(item)
    return items


def _spool_rpm(res: dict) -> float | None:
    limited = res["channels"]["boost_limited"]["nominal"]
    for rpm, flag in zip(res["rpm"], limited, strict=True):
        if flag is not None and flag < 0.5:
            return rpm
    return None


def _rod_material_options(design: EngineDesign, materials: Mapping[str, Material], samples: int, seed: int) -> list[dict]:
    out = []
    for mid, mat in materials.items():
        needed = ("density", "youngs_modulus", "yield_strength", "ultimate_strength")
        if any(k not in mat.properties for k in needed):
            continue
        d = design.model_dump()
        d["conrod"]["material_id"] = mid
        res = simulate(EngineDesign.model_validate(d), materials, samples, seed)
        checks = {r["id"]: r for r in res["limits"] if r["component"] == "connecting_rods"}
        out.append({
            "material_id": mid,
            "name": f"{mat.name} {mat.condition}".strip(),
            "custom": mat.custom,
            "rod_mass_g": res["summary"]["rod_mass_g"]["nominal"],
            "checks": {k: {"status": v["status"], "sf_nominal": v["sf_nominal"]} for k, v in checks.items()},
            "worst": lim.worst([v["status"] for v in checks.values()]),
        })
    out.sort(key=lambda o: (lim.STATUS_ORDER.index(o["worst"]) if o["worst"] != "no_data" else 5, o["rod_mass_g"]))
    return out


def advise(
    design: EngineDesign,
    materials: Mapping[str, Material],
    target_kw: float,
    samples: int = 200,
    seed: int = 42,
) -> dict:
    base_area = design.turbo.turbine_flow_area.value
    spec = PARAM_SPECS["turbo.turbine_flow_area"]
    strategies = []

    boost = _solve_boost(design, materials, base_area, target_kw)
    if boost is not None:
        strategies.append(("boost", "Raise boost on the current turbo", base_area, boost))

    for scale in TURBINE_SCALES[1:]:
        area = min(base_area * scale, spec.max)
        b = _solve_boost(design, materials, area, target_kw)
        if b is not None:
            strategies.append(("bigger_turbine", f"Larger turbine ({area:.1f} cm², ×{scale:g}) plus boost", area, b))
            break

    current = simulate(design, materials, samples, seed)
    out_strategies = []
    for sid, label, area, b in strategies:
        candidate = _with(design, b, area, target_kw)
        candidate = candidate.model_copy(update={"name": f"{design.name} → {target_kw:.0f} kW ({sid.replace('_', ' ')})"})
        res = simulate(candidate, materials, samples, seed)
        upgrades = _upgrades(candidate, res)
        rod_bad = any(u["component"] == "connecting_rods" for u in upgrades)
        out_strategies.append({
            "id": sid,
            "label": label,
            "boost_bar": b,
            "turbine_flow_area_cm2": area,
            "peak_power": res["summary"]["peak_power"],
            "peak_torque": res["summary"]["peak_torque"],
            "spool_rpm": _spool_rpm(res),
            "max_egt": res["summary"]["max_egt"],
            "probability_met": next((t["probability_met"] for t in res["targets"] if t["id"] == "peak_power"), None),
            "upgrades": upgrades,
            "upgrade_count": len(upgrades),
            "rod_material_options": _rod_material_options(candidate, materials, min(samples, 100), seed) if rod_bad else [],
            "design": candidate.model_dump(mode="json"),
            "warnings": res["warnings"],
        })

    notes = [
        "Each strategy reaches the target at nominal inputs; 'probability_met' shows the share of Monte Carlo samples "
        "that also reach it.",
        f"Required ratings are the 95th-percentile load × {lim.WARNING_SF} ({lim.THERMAL_WARNING_SF} on temperature rise "
        "above ambient) so the conservative safety factor clears the warning band. Buy parts on documented ratings, "
        "not on these estimates alone.",
        "Temperature limits can often be met by changing the operating point instead of the part (e.g. a richer mixture "
        "lowers turbine inlet temperature; a larger intercooler lowers charge temperature).",
        "Knock is not modelled: higher boost may need lower compression, better fuel or less ignition advance in reality.",
    ]
    if not strategies:
        notes.insert(0, f"No strategy reaches {target_kw:.0f} kW within {BOOST_CAP} bar boost and a turbine up to "
                        f"×{TURBINE_SCALES[-1]:g} flow area. Consider more displacement or a different architecture.")
    return {
        "target_kw": target_kw,
        "current_peak_power": current["summary"]["peak_power"],
        "strategies": out_strategies,
        "notes": notes,
    }
