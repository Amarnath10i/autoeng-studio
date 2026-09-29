"""Component catalog: the building blocks every automobile model is assembled from (spec §4-§6).

A component type declares its category, typed ports, parameter schema, the physics
models that can evaluate it, and its failure modes. Adding a new kind of part to
the platform means adding one entry here plus, when available, a physics model.
Types marked `planned` are part of the architecture (they can be placed and
wired) but have no physics model yet; simulations report them as not evaluated
rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from autoeng.core.params import Param
from autoeng.domain.engine_design import EngineDesign
from autoeng.platform.body import BodyGeometry


class PortKind(StrEnum):
    ROTATION = "rotation"  # rotating mechanical shaft (torque, speed)
    MOUNT = "mount"  # structural attachment (forces, moments)
    AIR = "air"
    EXHAUST = "exhaust"
    FUEL = "fuel"
    COOLANT = "coolant"
    DC = "dc"  # high-voltage DC bus
    AC = "ac"  # three-phase AC
    ROAD = "road"  # tyre contact patch
    SIGNAL = "signal"


@dataclass(frozen=True)
class Port:
    name: str
    kind: PortKind
    label: str


@dataclass(frozen=True)
class ComponentType:
    id: str
    name: str
    category: str
    description: str
    ports: tuple[Port, ...]
    params_model: type[BaseModel] | None
    status: str = "available"  # "available" or "planned"
    models: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    passport: dict = field(default_factory=dict)

    def port(self, name: str) -> Port | None:
        return next((p for p in self.ports if p.name == name), None)


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClutchParams(_Params):
    torque_capacity: Param  # N·m
    launch_rpm: Param | None = None  # rpm held while the clutch slips at launch; default: bottom of the engine sweep
    mass: Param | None = None  # kg


class GearboxParams(_Params):
    ratios: list[float] = Field(min_length=1, max_length=12)
    efficiency: Param  # -
    input_torque_rating: Param  # N·m
    shift_time: Param  # s, torque interruption per shift

    @field_validator("ratios")
    @classmethod
    def _descending(cls, v: list[float]) -> list[float]:
        if any(r <= 0 for r in v) or any(a <= b for a, b in zip(v, v[1:], strict=False)):
            raise ValueError("gear ratios must be positive and strictly decreasing (1st gear first)")
        return v


class FinalDriveParams(_Params):
    ratio: Param
    efficiency: Param
    axle_torque_rating: Param | None = None  # N·m per driven axle (both halfshafts)


class WheelTireParams(_Params):
    rolling_radius: Param  # m
    rolling_resistance: Param  # Crr, -
    peak_friction: Param  # μ, dry road
    driven_axle: str = Field(pattern="^(front|rear|all)$")


class BodyParams(_Params):
    mass: Param  # kg, test mass including driver
    drag_coefficient: Param  # Cd
    frontal_area: Param  # m²
    wheelbase: Param  # m
    cg_height: Param  # m
    front_weight_fraction: Param  # static share of weight on the front axle
    geometry: BodyGeometry | None = None  # sketch from the body designer


class CoolingParams(_Params):
    """Engine cooling circuit: radiator, fan, thermostat and the engine's thermal mass."""

    rated_heat_rejection: Param  # kW, at the rated coolant-to-air temperature difference and airspeed
    rated_delta_t: Param  # K
    rated_airspeed: Param  # km/h
    fan_airflow_fraction: Param  # share of rated airflow the fan provides at standstill
    airflow_exponent: Param  # UA ∝ airflow^n
    circuit_thermal_capacity: Param  # kJ/K, engine block + coolant + oil
    thermostat_open: Param  # °C
    thermostat_full_open: Param  # °C
    max_coolant_temp: Param  # °C allowable (boiling margin of the pressurised system)


class BrakeParams(_Params):
    """Front-axle brakes (the axle that takes most of the braking energy)."""

    disc_material_id: str
    disc_mass: Param  # kg per disc
    disc_cooling_area: Param  # m² per disc exposed to air
    front_bias: Param  # share of braking force on the front axle
    h_standstill: Param  # W/(m²·K) convective coefficient at rest
    h_speed_coeff: Param  # W/(m²·K) per (m/s)^0.8
    emissivity: Param
    max_disc_temp: Param  # °C allowable (fade / pad limit)


class EngineParams(EngineDesign):
    """The engine is a full engine design (see the engine lab)."""


def _p(name: str, kind: PortKind, label: str) -> Port:
    return Port(name, kind, label)


CATALOG: dict[str, ComponentType] = {
    t.id: t
    for t in [
        ComponentType(
            "engine_turbo_si", "Turbocharged SI engine", "Powertrain",
            "Four-stroke spark-ignition engine with turbocharger and intercooler.",
            (_p("crank", PortKind.ROTATION, "Crankshaft output"), _p("air_in", PortKind.AIR, "Air inlet"),
             _p("exhaust_out", PortKind.EXHAUST, "Exhaust outlet"), _p("fuel_in", PortKind.FUEL, "Fuel supply"),
             _p("coolant", PortKind.COOLANT, "Coolant circuit"), _p("mounts", PortKind.MOUNT, "Engine mounts")),
            EngineParams, models=("engine.turbo_si_mvem", "structure.conrod_beam"),
            failure_modes=("knock (not modelled)", "rod failure", "overheating", "turbo overspeed"),
        ),
        ComponentType(
            "clutch", "Clutch", "Driveline", "Friction clutch between engine and gearbox.",
            (_p("in", PortKind.ROTATION, "Engine side"), _p("out", PortKind.ROTATION, "Gearbox side")),
            ClutchParams, models=("vehicle.longitudinal",), failure_modes=("slip", "glazing"),
        ),
        ComponentType(
            "gearbox", "Manual/automated gearbox", "Driveline", "Fixed-ratio gearbox with a set of forward gears.",
            (_p("in", PortKind.ROTATION, "Input shaft"), _p("out", PortKind.ROTATION, "Output shaft"),
             _p("mounts", PortKind.MOUNT, "Mounts")),
            GearboxParams, models=("vehicle.longitudinal",), failure_modes=("tooth bending", "pitting", "bearing failure"),
        ),
        ComponentType(
            "final_drive", "Final drive & differential", "Driveline", "Final reduction and open differential.",
            (_p("in", PortKind.ROTATION, "Pinion input"), _p("out", PortKind.ROTATION, "Halfshafts")),
            FinalDriveParams, models=("vehicle.longitudinal",), failure_modes=("ring-gear failure", "halfshaft torsion"),
        ),
        ComponentType(
            "wheel_tire", "Wheels & tyres (driven axle set)", "Chassis", "Wheel and tyre set; defines the driven axle.",
            (_p("hub", PortKind.ROTATION, "Hub"), _p("road", PortKind.ROAD, "Contact patch"),
             _p("mount", PortKind.MOUNT, "Suspension upright")),
            WheelTireParams, models=("vehicle.longitudinal",), failure_modes=("wheelspin", "tyre overload"),
        ),
        ComponentType(
            "body", "Vehicle body & mass properties", "Body",
            "Mass, centre of gravity and aerodynamic properties of the whole vehicle.",
            (_p("mounts", PortKind.MOUNT, "Chassis mounts"),),
            BodyParams, models=("vehicle.longitudinal",),
        ),
        # --- Planned: part of the architecture, no physics model yet --------------------------------
        ComponentType("battery_pack", "Battery pack", "Electric powertrain", "High-voltage traction battery.",
                      (_p("dc", PortKind.DC, "HV DC"), _p("coolant", PortKind.COOLANT, "Cooling plate"),
                       _p("mounts", PortKind.MOUNT, "Mounts")), None, status="planned",
                      failure_modes=("thermal runaway", "capacity fade")),
        ComponentType("inverter", "Inverter", "Electric powertrain", "DC/AC traction inverter.",
                      (_p("dc", PortKind.DC, "HV DC"), _p("ac", PortKind.AC, "Motor phases")), None, status="planned"),
        ComponentType("electric_motor", "Traction motor", "Electric powertrain", "Electric traction machine.",
                      (_p("ac", PortKind.AC, "Phases"), _p("shaft", PortKind.ROTATION, "Rotor shaft"),
                       _p("coolant", PortKind.COOLANT, "Cooling jacket")), None, status="planned",
                      failure_modes=("winding overtemperature", "demagnetisation")),
        ComponentType("suspension_corner", "Suspension corner", "Chassis", "Spring, damper and linkage at one corner.",
                      (_p("upright", PortKind.MOUNT, "Upright"), _p("body", PortKind.MOUNT, "Body mounts")), None,
                      status="planned", failure_modes=("fatigue", "bushing failure")),
        ComponentType("brakes_front", "Front brakes", "Chassis", "Front discs, calipers and pads (thermal model).",
                      (_p("mount", PortKind.MOUNT, "Uprights"),), BrakeParams, models=("thermal.duty_cycle",),
                      failure_modes=("fade", "disc cracking", "pad overheating")),
        ComponentType("chassis_structure", "Chassis structure", "Body", "Load-bearing structure (FEA in stage 3).",
                      (_p("mounts", PortKind.MOUNT, "Mount points"),), None, status="planned",
                      failure_modes=("yield", "fatigue", "buckling")),
        ComponentType("radiator", "Cooling circuit", "Thermal",
                      "Radiator, fan and thermostat, plus the engine's thermal mass.",
                      (_p("coolant", PortKind.COOLANT, "Coolant"),), CoolingParams, models=("thermal.duty_cycle",),
                      failure_modes=("overheating", "boil-over")),
        ComponentType("fuel_tank", "Fuel tank & pump", "Fuel", "Fuel storage and delivery.",
                      (_p("fuel_out", PortKind.FUEL, "Fuel out"),), None, status="planned"),
    ]
}


def catalog_dict() -> list[dict]:
    from autoeng.platform.templates import generic_hatch

    defaults = {c.type: c.params for c in generic_hatch().components.values() if c.params is not None}
    out = []
    for t in CATALOG.values():
        out.append({
            "id": t.id, "name": t.name, "category": t.category, "description": t.description, "status": t.status,
            "models": list(t.models), "failure_modes": list(t.failure_modes),
            "ports": [{"name": p.name, "kind": p.kind.value, "label": p.label} for p in t.ports],
            "params_schema": t.params_model.model_json_schema() if t.params_model and t.id != "engine_turbo_si" else None,
            "default_params": defaults.get(t.id),
        })
    return out
