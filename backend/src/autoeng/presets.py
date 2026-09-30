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


def _derive(name: str, description: str, *, layout: str, cylinders: int, bore: float, stroke: float, rod: float,
            cr: float, induction: str, boost: float, rpm_max: int, ve_peak_rpm: float, bank_angle: float = 90.0,
            crank: str = "standard", turbine_area: float = 4.2, compressor_eff: float = 0.72,
            injector_flow: float = 450, limits: dict[str, float] | None = None, lam: float = 0.85,
            ve_peak: float = 0.95, low_friction: bool = False) -> EngineDesign:
    """A generic engine of another layout, derived from the base design (all values illustrative estimates)."""
    d = generic_2l_turbo().model_dump()
    d["name"], d["description"] = name, description
    d["architecture"].update(layout=layout, crank=crank, induction=induction)
    d["architecture"]["bank_angle"]["value"] = bank_angle
    d["engine"].update(cylinders=cylinders)
    d["engine"]["bore"]["value"], d["engine"]["stroke"]["value"] = bore, stroke
    d["engine"]["rod_length"]["value"], d["engine"]["compression_ratio"]["value"] = rod, cr
    d["operating"]["rpm_max"] = rpm_max
    d["breathing"]["ve_peak_rpm"]["value"] = ve_peak_rpm
    d["turbo"]["boost_target"]["value"] = boost
    d["turbo"]["turbine_flow_area"]["value"] = turbine_area
    d["turbo"]["compressor_efficiency"]["value"] = compressor_eff
    d["combustion"]["lambda_ratio"]["value"] = lam
    d["fuel"]["injector_count"] = cylinders
    d["fuel"]["injector_flow"]["value"] = injector_flow
    d["conrod"]["piston_group_mass"]["value"] = round(420 * (bore / 86) ** 2)
    d["breathing"]["ve_peak"]["value"] = ve_peak
    if low_friction:
        # The Barnes-Moss coefficients come from 1970s engines; a modern high-revving engine loses far less.
        for key, value in (("a", 0.9), ("b", 0.12), ("c", 0.025)):
            d["friction"][key] = P(value, EST, value * 0.15, "Estimated for a modern low-friction engine")
    for lim in d["limits"]:
        if limits and lim["id"] in limits:
            lim["allowable"]["value"] = limits[lim["id"]]
    return EngineDesign.model_validate(d)


def v8_na() -> EngineDesign:
    return _derive("Generic 5.0 L V8 naturally aspirated", "Cross-plane 90° V8, high compression, no boost device.",
                   layout="v", cylinders=8, bore=92.0, stroke=93.0, rod=150.0, cr=11.5, induction="naturally_aspirated",
                   boost=0.0, rpm_max=7500, ve_peak_rpm=5500, crank="cross_plane", injector_flow=400, lam=0.88,
                   ve_peak=1.02, low_friction=True,
                   limits={"clutch": 650, "gearbox": 700, "cooling": 320, "pcp": 120, "piston_speed": 24})


def v8_supercharged() -> EngineDesign:
    return _derive("Generic 4.0 L V8 supercharged", "Cross-plane V8 with a positive-displacement (screw) supercharger.",
                   layout="v", cylinders=8, bore=89.0, stroke=80.0, rod=150.0, cr=9.5, induction="supercharger_pd",
                   boost=0.7, rpm_max=7000, ve_peak_rpm=5000, crank="cross_plane", compressor_eff=0.65, injector_flow=550,
                   low_friction=True,
                   limits={"clutch": 800, "gearbox": 850, "cooling": 380, "pcp": 150, "piston_speed": 22})


def flat4_turbo() -> EngineDesign:
    return _derive("Generic 2.5 L flat-4 turbo", "Horizontally opposed four with a single turbocharger.",
                   layout="flat", cylinders=4, bore=99.5, stroke=79.0, rod=130.5, cr=8.2, induction="turbo",
                   boost=1.1, rpm_max=6700, ve_peak_rpm=4500, bank_angle=180, turbine_area=4.8, injector_flow=560,
                   limits={"clutch": 480, "gearbox": 500, "cooling": 260})


def v6_turbo() -> EngineDesign:
    return _derive("Generic 3.0 L V6 turbo", "90° V6 with split crankpins for even firing; turbocharged.",
                   layout="v", cylinders=6, bore=86.0, stroke=86.0, rod=145.0, cr=9.8, induction="turbo",
                   boost=1.0, rpm_max=7000, ve_peak_rpm=4800, bank_angle=90, turbine_area=6.2, injector_flow=480,
                   limits={"clutch": 600, "gearbox": 620, "cooling": 300})


PRESETS = {
    "generic_2l_turbo": ("Generic 2.0 L turbo I4", generic_2l_turbo),
    "generic_2l_turbo_stage2": ("Generic 2.0 L turbo I4, 1.5 bar", stage2_variant),
    "generic_v6_turbo": ("Generic 3.0 L V6 turbo", v6_turbo),
    "generic_flat4_turbo": ("Generic 2.5 L flat-4 turbo", flat4_turbo),
    "generic_v8_na": ("Generic 5.0 L V8 naturally aspirated", v8_na),
    "generic_v8_supercharged": ("Generic 4.0 L V8 supercharged", v8_supercharged),
}
