"""Vehicle templates: a blank vehicle (spec §3 mode B) and an illustrative complete layout.

The complete layout is generic and every value is labelled `estimated`; it is a
starting point to edit, not the specification of any real car.
"""

from __future__ import annotations

from autoeng.core.params import P, Source
from autoeng.platform.vehicle import VehicleDesign
from autoeng.presets import ILLUSTRATIVE, generic_2l_turbo

EST = Source.ESTIMATED
RATING = "Illustrative rating; replace with the manufacturer's documented value"


def _e(value: float, tol: float = 0.0, ref: str = ILLUSTRATIVE) -> dict:
    return P(value, EST, tol, ref).model_dump(mode="json")


def blank_vehicle(name: str = "New vehicle") -> VehicleDesign:
    return VehicleDesign(name=name, description="Empty vehicle: add components from the catalog and wire them up.")


def generic_hatch() -> VehicleDesign:
    engine = generic_2l_turbo().model_dump(mode="json")
    engine["limits"] = [lim for lim in engine["limits"] if lim["component"] not in ("clutch", "gearbox")]
    return VehicleDesign.model_validate({
        "name": "Generic 2.0 L turbo hatchback (FWD)",
        "description": "Illustrative front-wheel-drive hatchback with a six-speed manual gearbox.",
        "vehicle_type": "passenger_car",
        "components": {
            "engine": {"type": "engine_turbo_si", "name": "2.0 L turbo I4", "params": engine},
            "clutch": {"type": "clutch", "name": "Single-plate clutch",
                       "params": {"torque_capacity": _e(400, 20, RATING),
                                  "launch_rpm": _e(3500, 300, "Driver launch technique (engine rpm held during clutch slip)")}},
            "gearbox": {"type": "gearbox", "name": "6-speed manual",
                        "params": {"ratios": [3.46, 2.05, 1.30, 1.03, 0.84, 0.69],
                                   "efficiency": _e(0.96, 0.01), "input_torque_rating": _e(380, 10, RATING),
                                   "shift_time": _e(0.30, 0.05)}},
            "final_drive": {"type": "final_drive", "name": "Final drive & open diff",
                            "params": {"ratio": _e(3.47), "efficiency": _e(0.97, 0.01),
                                       "axle_torque_rating": _e(4000, 200, RATING)}},
            "wheels": {"type": "wheel_tire", "name": "225/40 R18 tyres",
                       "params": {"rolling_radius": _e(0.315, 0.003), "rolling_resistance": _e(0.011, 0.002),
                                  "peak_friction": _e(1.0, 0.1, "Typical dry-asphalt peak friction for road tyres"),
                                  "driven_axle": "front"}},
            "body": {"type": "body", "name": "Body & mass properties",
                     "params": {"mass": _e(1525, 25), "drag_coefficient": _e(0.32, 0.02), "frontal_area": _e(2.2, 0.05),
                                "wheelbase": _e(2.63), "cg_height": _e(0.53, 0.03),
                                "front_weight_fraction": _e(0.61, 0.01)}},
            "radiator": {"type": "radiator", "name": "Radiator, fan & thermostat",
                         "params": {"rated_heat_rejection": _e(120, 10, RATING), "rated_delta_t": _e(70),
                                    "rated_airspeed": _e(100), "fan_airflow_fraction": _e(0.35, 0.05),
                                    "airflow_exponent": _e(0.6, 0.1, "Typical heat-exchanger airflow scaling (estimated)"),
                                    "circuit_thermal_capacity": _e(160, 30), "thermostat_open": _e(88),
                                    "thermostat_full_open": _e(100),
                                    "max_coolant_temp": _e(118, 3, "Boiling margin of a ~1.2 bar pressurised system")}},
            "brakes": {"type": "brakes_front", "name": "Front brakes (340 mm discs)",
                       "params": {"disc_material_id": "grey_cast_iron", "disc_mass": _e(9.5, 0.3),
                                  "disc_cooling_area": _e(0.16, 0.02), "front_bias": _e(0.72, 0.02),
                                  "h_standstill": _e(15, 5), "h_speed_coeff": _e(12, 3),
                                  "emissivity": _e(0.55, 0.1, "Oxidised cast iron (estimated)"),
                                  "max_disc_temp": _e(650, 30, "Illustrative fade limit for street pads")}},
            "fuel_tank": {"type": "fuel_tank", "name": "Fuel tank (planned model)"},
        },
        "connections": [
            {"source": "engine.crank", "target": "clutch.in"},
            {"source": "clutch.out", "target": "gearbox.in"},
            {"source": "gearbox.out", "target": "final_drive.in"},
            {"source": "final_drive.out", "target": "wheels.hub"},
            {"source": "engine.coolant", "target": "radiator.coolant"},
            {"source": "fuel_tank.fuel_out", "target": "engine.fuel_in"},
            {"source": "engine.mounts", "target": "body.mounts"},
            {"source": "gearbox.mounts", "target": "body.mounts"},
            {"source": "brakes.mount", "target": "body.mounts"},
        ],
        "targets": {"accel_0_100_s": 7.0, "top_speed_kmh": 240},
    })


VEHICLE_TEMPLATES = {
    "generic_hatch": ("Generic 2.0 L turbo hatchback (FWD)", generic_hatch),
    "blank": ("Blank vehicle (build from scratch)", blank_vehicle),
}
