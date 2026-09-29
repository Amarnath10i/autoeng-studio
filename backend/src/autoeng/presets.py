"""Starter designs.

These are illustrative, generic engines. They are not specifications of any real
product and every value is labelled `estimated`, so the trust layer never presents
them as data. Users replace values with measured or manufacturer data as they get it.
"""

from __future__ import annotations

from autoeng.core.params import P, Source
from autoeng.domain.engine_design import EngineDesign

EST = Source.ESTIMATED
ILLUSTRATIVE = "Illustrative starter value; not taken from any specific engine"
LIMIT_NOTE = "Illustrative allowable; replace with manufacturer or test data for your part"
BARNES_MOSS = "Barnes-Moss correlation as given in Heywood (1988) ch. 13; derived from older SI engines"


def _e(value: float, tol: float = 0.0, ref: str = ILLUSTRATIVE):
    return P(value, EST, tol, ref)


def generic_2l_turbo() -> EngineDesign:
    return EngineDesign.model_validate({
        "name": "Generic 2.0 L turbo I4",
        "description": "Illustrative inline-four with a single turbocharger and air-to-air intercooler.",
        "engine": {
            "cylinders": 4,
            "bore": _e(86.0),
            "stroke": _e(86.0),
            "rod_length": _e(145.0),
            "compression_ratio": _e(9.6, 0.1),
        },
        "operating": {"rpm_min": 1500, "rpm_max": 6500, "rpm_step": 100},
        "breathing": {
            "ve_peak": _e(0.95, 0.03),
            "ve_peak_rpm": _e(4500, 250),
            "ve_falloff": _e(0.30, 0.05),
        },
        "turbo": {
            "boost_target": _e(1.0, 0.03),
            "compressor_efficiency": _e(0.72, 0.03),
            "turbine_efficiency": _e(0.70, 0.04),
            "mechanical_efficiency": _e(0.95, 0.02),
            "turbine_flow_area": _e(4.2, 0.3),
        },
        "intercooler": {"effectiveness": _e(0.75, 0.05), "pressure_drop": _e(0.10, 0.03)},
        "combustion": {
            "lambda_ratio": _e(0.85, 0.02),
            "efficiency_ratio": _e(0.75, 0.04),
            "cycle_gamma": _e(1.30, 0.01),
            "combustion_efficiency": _e(0.98, 0.01),
            "pressure_rise_ratio": _e(3.0, 0.3),
            "polytropic_n": _e(1.32, 0.02),
            "coolant_heat_fraction": _e(0.28, 0.04),
        },
        "exhaust": {
            "backpressure": _e(0.15, 0.05),
            "gas_cp": _e(1150, 40, "Typical mean cp of lean-to-rich exhaust at 800-1200 K"),
            "gas_gamma": _e(1.33, 0.01, "Typical exhaust γ at turbine-inlet temperatures"),
        },
        "friction": {
            "a": P(0.97, Source.LITERATURE, 0.1, BARNES_MOSS),
            "b": P(0.15, Source.LITERATURE, 0.02, BARNES_MOSS),
            "c": P(0.05, Source.LITERATURE, 0.01, BARNES_MOSS),
        },
        "fuel": {"fuel_id": "gasoline_e0", "injector_flow": _e(500, 10), "injector_count": 4},
        "ambient": {
            "temperature": P(25.0, Source.USER, 0.0, "Test condition"),
            "pressure": P(101.325, Source.USER, 0.0, "Test condition (sea level)"),
        },
        "conrod": {
            "material_id": "aisi_4340_normalized",
            "section_height": _e(20.0),
            "section_width": _e(16.0),
            "flange_thickness": _e(4.0),
            "web_thickness": _e(5.0),
            "volume": _e(75.0, 3),
            "piston_group_mass": _e(420.0, 15),
            "small_end_fraction": _e(0.30, 0.03),
            "fatigue_factor": _e(0.5, 0.1, "Estimated product of Marin factors for a forged, shot-peened rod"),
            "overspeed_factor": _e(1.10, 0.0, "Missed-shift load case: 10 % above redline"),
        },
        "targets": {"peak_power": P(180.0, Source.USER), "peak_torque": P(350.0, Source.USER)},
        "limits": [
            {"id": "pcp", "component": "combustion_chamber", "channel": "peak_pressure", "label": "Peak cylinder pressure",
             "allowable": _e(140.0, 10, LIMIT_NOTE)},
            {"id": "egt", "component": "turbine", "channel": "egt", "label": "Turbine inlet temperature",
             "allowable": _e(980.0, 25, LIMIT_NOTE)},
            {"id": "pr", "component": "compressor", "channel": "pressure_ratio", "label": "Compressor pressure ratio",
             "allowable": _e(2.8, 0.1, LIMIT_NOTE)},
            {"id": "iat", "component": "intercooler", "channel": "charge_temp", "label": "Charge air temperature",
             "allowable": _e(60.0, 5, LIMIT_NOTE)},
            {"id": "clutch", "component": "clutch", "channel": "torque", "label": "Clutch torque capacity",
             "allowable": _e(400.0, 20, LIMIT_NOTE)},
            {"id": "gearbox", "component": "gearbox", "channel": "torque", "label": "Gearbox input torque rating",
             "allowable": _e(380.0, 10, LIMIT_NOTE)},
            {"id": "cooling", "component": "cooling_system", "channel": "heat_to_coolant", "label": "Cooling capacity",
             "allowable": _e(200.0, 15, LIMIT_NOTE)},
            {"id": "injectors", "component": "fuel_system", "channel": "injector_duty", "label": "Injector duty cycle",
             "allowable": P(0.85, EST, 0.0, "Common tuning practice: keep static-injector duty below ~80-85 %")},
            {"id": "piston_speed", "component": "crankshaft", "channel": "piston_speed", "label": "Mean piston speed",
             "allowable": _e(22.0, 1, LIMIT_NOTE)},
        ],
    })


def stage2_variant() -> EngineDesign:
    """Same engine with the boost raised and a larger turbine: a classic what-if."""
    d = generic_2l_turbo().model_dump()
    d["name"] = "Generic 2.0 L turbo I4, 1.5 bar"
    d["description"] = "Boost raised from 1.0 to 1.5 bar with a larger turbine housing."
    d["turbo"]["boost_target"]["value"] = 1.5
    d["turbo"]["turbine_flow_area"]["value"] = 5.0
    return EngineDesign.model_validate(d)


PRESETS = {
    "generic_2l_turbo": ("Generic 2.0 L turbo I4", generic_2l_turbo),
    "generic_2l_turbo_stage2": ("Generic 2.0 L turbo I4, 1.5 bar", stage2_variant),
}
