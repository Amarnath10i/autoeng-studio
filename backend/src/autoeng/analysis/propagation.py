"""Declared dependency graph of the physics models (spec §14, §17).

Each model node lists the inputs it reads (design-parameter prefixes ending in
"." or exact names of quantities other models produce) and the quantities it
outputs. Tracing a change walks this graph breadth-first, which gives the
propagation path "boost → turbo matching → air flow → combustion → torque → …".
The what-if engine then attaches the actual numeric change to each step, so the
trace shows both the causal path and its magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelNode:
    id: str
    label: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


GRAPH: list[ModelNode] = [
    ModelNode("geometry", "Engine geometry",
              ("engine.bore", "engine.stroke", "engine.cylinders", "operating."), ("displacement", "piston_speed")),
    ModelNode("breathing", "Volumetric efficiency", ("breathing.", "operating."), ("ve",)),
    ModelNode("fuel_props", "Fuel properties", ("fuel.fuel_id",), ("fuel_properties",)),
    ModelNode("material", "Rod material", ("conrod.material_id",), ("material_properties",)),
    ModelNode("turbo_match", "Turbo matching (turbine ⇄ compressor power balance)",
              ("turbo.", "intercooler.", "ambient.", "exhaust.", "combustion.", "engine.compression_ratio",
               "displacement", "ve", "fuel_properties"),
              ("boost", "manifold_pressure", "pressure_ratio", "compressor_outlet_temp", "charge_temp", "air_flow",
               "corrected_air_flow", "compressor_power", "turbine_power", "exhaust_manifold_pressure", "egt",
               "wastegate_fraction", "boost_limited")),
    ModelNode("combustion", "Combustion and indicated work",
              ("air_flow", "combustion.", "engine.compression_ratio", "fuel_properties"),
              ("fuel_flow", "heat_released", "imep")),
    ModelNode("cylinder_pressure", "Peak cylinder pressure",
              ("manifold_pressure", "engine.compression_ratio", "combustion.pressure_rise_ratio", "combustion.polytropic_n"),
              ("peak_pressure",)),
    ModelNode("losses", "Friction and gas exchange",
              ("friction.", "manifold_pressure", "exhaust_manifold_pressure"), ("fmep", "pmep")),
    ModelNode("brake", "Brake output", ("imep", "pmep", "fmep", "displacement"),
              ("bmep", "torque", "power", "bsfc", "brake_efficiency")),
    ModelNode("thermal", "Heat rejection", ("heat_released", "combustion.coolant_heat_fraction"),
              ("heat_to_coolant", "exhaust_heat")),
    ModelNode("fuel_delivery", "Fuel delivery", ("fuel_flow", "fuel.", "fuel_properties"), ("injector_duty",)),
    ModelNode("conrod", "Connecting-rod loads",
              ("peak_pressure", "conrod.", "material_properties", "engine.bore", "engine.stroke", "engine.rod_length",
               "operating.rpm_max"),
              ("rod_compressive_stress", "rod_tensile_stress")),
]


def _matches(token: str, changed: str) -> bool:
    return changed.startswith(token) if token.endswith(".") else changed == token


def trace(changed_paths: list[str]) -> list[dict]:
    """Breadth-first propagation. Each step: the model, what triggered it, what it outputs."""
    frontier = set(changed_paths)
    seen_quantities = set(changed_paths)
    fired: set[str] = set()
    steps = []
    depth = 0
    while frontier:
        depth += 1
        next_frontier: set[str] = set()
        for node in GRAPH:
            if node.id in fired:
                continue
            triggers = sorted(q for q in frontier if any(_matches(t, q) for t in node.inputs))
            if not triggers:
                continue
            fired.add(node.id)
            steps.append({"model": node.id, "label": node.label, "depth": depth,
                          "triggered_by": triggers, "outputs": list(node.outputs)})
            for out in node.outputs:
                if out not in seen_quantities:
                    seen_quantities.add(out)
                    next_frontier.add(out)
        frontier = next_frontier
    return steps


def graph_dict() -> list[dict]:
    return [{"id": n.id, "label": n.label, "inputs": list(n.inputs), "outputs": list(n.outputs)} for n in GRAPH]
