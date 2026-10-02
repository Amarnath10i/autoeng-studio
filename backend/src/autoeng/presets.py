"""Starter designs.

These are illustrative, generic engines. They are not specifications of any real
product and every value is labelled `estimated`, so the trust layer never presents
them as data. Users replace values with measured or manufacturer data as they get it.
"""

from __future__ import annotations

from functools import lru_cache

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
    if induction == "naturally_aspirated":  # no compressor: boost-device limits do not apply
        d["limits"] = [lim for lim in d["limits"] if lim["component"] not in ("compressor", "turbine", "intercooler")]
    elif induction != "turbo":
        d["limits"] = [lim for lim in d["limits"] if lim["component"] != "turbine"]
    d["targets"] = {}  # the base engine's power and torque targets do not carry over
    return _size_supporting(EngineDesign.model_validate(d), limits or {})


SIZED = "Illustrative allowable, sized with margin over this engine's stock operating point"
# Channel → (limit id, margin). Mechanical loads get ×1.3; thermal limits get a margin in °C above the peak.
MARGINS = {"peak_pressure": ("pcp", 1.3), "pressure_ratio": ("pr", 1.15), "torque_clutch": ("clutch", 1.3),
           "torque_gearbox": ("gearbox", 1.3), "heat_to_coolant": ("cooling", 1.3), "piston_speed": ("piston_speed", 1.15)}
THERMAL_MARGINS = {"egt": ("egt", 120.0), "charge_temp": ("iat", 25.0)}


def _size_supporting(design: EngineDesign, given: dict[str, float]) -> EngineDesign:
    """Size what a manufacturer would size for a stock engine: injectors for ~75 % duty, and the allowables of the
    clutch, gearbox, cooling and other limits with margin over this engine's nominal peak. Limits given explicitly
    in the library stay as floors (the larger value wins)."""
    import numpy as np

    from autoeng.analysis.sampling import sample_design
    from autoeng.domain.materials import LIBRARY
    from autoeng.physics import engine_mvem

    s = sample_design(design, LIBRARY, 1, 0)
    rpm = np.arange(design.operating.rpm_min, design.operating.rpm_max + 1, 250.0)
    out = engine_mvem.run(s.engine, rpm)
    peak = {k: float(np.max(v)) for k, v in out.items() if np.ndim(v) == 2}
    peak["torque_clutch"] = peak["torque_gearbox"] = peak["torque"]
    d = design.model_dump()
    duty = peak.get("injector_duty", 0.0)
    if duty > 0:
        d["fuel"]["injector_flow"]["value"] = 10 * np.ceil(d["fuel"]["injector_flow"]["value"] * duty / 0.72 / 10)
    by_id = {lim["id"]: lim for lim in d["limits"]}
    for channel, (lim_id, margin) in MARGINS.items():
        if lim_id in by_id and channel in peak:
            value = max(peak[channel] * margin, given.get(lim_id, 0.0))
            by_id[lim_id]["allowable"].update(value=round(value, 2 if value < 10 else 0), ref=SIZED)
    for channel, (lim_id, margin) in THERMAL_MARGINS.items():
        if lim_id in by_id and channel in peak:
            value = max(peak[channel] + margin, given.get(lim_id, 0.0))
            by_id[lim_id]["allowable"].update(value=round(value), ref=SIZED)
    return EngineDesign.model_validate(d)


# --------------------------------------------------------------------- engine library
#
# Generic engines across layouts and induction types. Dimensions are typical of each class (bore × stroke giving the
# stated displacement); they describe no particular product. Twin- and quad-turbo engines are modelled with one
# equivalent turbine (the summed effective flow area).

ENGINES: list[dict] = [
    dict(id="generic_1l_i3_turbo", group="Small & economy", name="Generic 1.0 L turbo I3",
         description="Downsized three-cylinder with a small, quick-spooling turbo.",
         layout="inline", cylinders=3, bore=74.5, stroke=76.4, rod=130, cr=10.0, induction="turbo", boost=1.1,
         rpm_max=6300, ve_peak_rpm=3500, turbine_area=2.3, injector_flow=280, low_friction=True,
         limits={"clutch": 260, "gearbox": 250, "cooling": 110, "pcp": 130}),
    dict(id="generic_1_6_i4_na", group="Small & economy", name="Generic 1.6 L I4 naturally aspirated",
         description="Port-injected inline-four of the kind found in small family cars.",
         layout="inline", cylinders=4, bore=78.0, stroke=83.6, rod=140, cr=11.0, induction="naturally_aspirated",
         boost=0.0, rpm_max=6800, ve_peak_rpm=4500, injector_flow=220, lam=0.9, low_friction=True,
         limits={"clutch": 220, "gearbox": 220, "cooling": 110, "pcp": 100}),
    dict(id="generic_2l_i4_hot", group="Four-cylinder performance", name="Generic 2.0 L turbo I4, high output",
         description="Hot-hatch four with a large turbo and forged internals.",
         layout="inline", cylinders=4, bore=82.5, stroke=92.8, rod=144, cr=9.3, induction="turbo", boost=1.6,
         rpm_max=7000, ve_peak_rpm=5000, turbine_area=5.4, compressor_eff=0.74, injector_flow=650, lam=0.82,
         limits={"clutch": 560, "gearbox": 600, "cooling": 280, "pcp": 175, "egt": 1000, "pr": 3.0}),
    dict(id="generic_2l_i4_na_screamer", group="Four-cylinder performance", name="Generic 2.0 L I4 high-revving NA",
         description="Short-stroke, high-compression four built to rev.",
         layout="inline", cylinders=4, bore=87.0, stroke=84.0, rod=153, cr=12.5, induction="naturally_aspirated",
         boost=0.0, rpm_max=8800, ve_peak_rpm=7000, injector_flow=320, lam=0.88, ve_peak=1.05, low_friction=True,
         limits={"clutch": 300, "gearbox": 300, "cooling": 170, "pcp": 120, "piston_speed": 25.5}),
    dict(id="generic_2_5_i5_turbo", group="Four-cylinder performance", name="Generic 2.5 L turbo I5",
         description="Inline-five firing every 144°.",
         layout="inline", cylinders=5, bore=82.5, stroke=92.8, rod=144, cr=10.0, induction="turbo", boost=1.4,
         rpm_max=7000, ve_peak_rpm=5000, turbine_area=5.8, injector_flow=550,
         limits={"clutch": 560, "gearbox": 620, "cooling": 300, "pcp": 160}),
    dict(id="generic_3l_i6_na", group="Six-cylinder", name="Generic 3.0 L I6 naturally aspirated",
         description="Smooth, inherently balanced straight-six.",
         layout="inline", cylinders=6, bore=84.0, stroke=89.6, rod=145, cr=11.5, induction="naturally_aspirated",
         boost=0.0, rpm_max=7500, ve_peak_rpm=5500, injector_flow=280, ve_peak=1.0, lam=0.88, low_friction=True,
         limits={"clutch": 420, "gearbox": 450, "cooling": 220, "pcp": 115}),
    dict(id="generic_3l_i6_turbo", group="Six-cylinder", name="Generic 3.0 L turbo I6",
         description="Straight-six with a twin-scroll turbo.",
         layout="inline", cylinders=6, bore=84.0, stroke=90.0, rod=144, cr=10.2, induction="turbo", boost=1.2,
         rpm_max=7000, ve_peak_rpm=4800, turbine_area=6.6, injector_flow=480,
         limits={"clutch": 650, "gearbox": 700, "cooling": 330, "pcp": 155}),
    dict(id="generic_3_5_v6_na", group="Six-cylinder", name="Generic 3.5 L V6 naturally aspirated",
         description="60° V6 with even firing and a compact block.",
         layout="v", cylinders=6, bore=94.0, stroke=83.0, rod=152, cr=11.0, bank_angle=60,
         induction="naturally_aspirated", boost=0.0, rpm_max=7000, ve_peak_rpm=5000, injector_flow=300, ve_peak=1.0,
         lam=0.88, low_friction=True, limits={"clutch": 450, "gearbox": 480, "cooling": 240, "pcp": 110}),
    dict(id="generic_3_8_v6_twin_turbo", group="Six-cylinder", name="Generic 3.8 L V6 twin-turbo",
         description="60° V6 with one turbo per bank (modelled as one equivalent turbine).",
         layout="v", cylinders=6, bore=95.5, stroke=88.4, rod=156, cr=9.0, bank_angle=60, induction="turbo",
         boost=1.3, rpm_max=7100, ve_peak_rpm=4500, turbine_area=8.6, injector_flow=650,
         limits={"clutch": 800, "gearbox": 850, "cooling": 420, "pcp": 165}),
    dict(id="generic_5_2_v8_flat_plane", group="V8", name="Generic 5.2 L V8 flat-plane NA",
         description="High-revving flat-plane V8: light crank, free secondary force.",
         layout="v", cylinders=8, bore=94.0, stroke=93.0, rod=150, cr=12.0, crank="flat_plane",
         induction="naturally_aspirated", boost=0.0, rpm_max=8250, ve_peak_rpm=6500, injector_flow=380, ve_peak=1.05,
         lam=0.88, low_friction=True,
         limits={"clutch": 650, "gearbox": 700, "cooling": 350, "pcp": 125, "piston_speed": 26}),
    dict(id="generic_4l_v8_twin_turbo", group="V8", name="Generic 4.0 L V8 twin-turbo",
         description="Cross-plane V8 with the turbos in the valley (hot-vee).",
         layout="v", cylinders=8, bore=86.0, stroke=86.0, rod=145, cr=9.5, crank="cross_plane", induction="turbo",
         boost=1.2, rpm_max=7200, ve_peak_rpm=4500, turbine_area=9.5, injector_flow=600,
         limits={"clutch": 950, "gearbox": 1000, "cooling": 480, "pcp": 160}),
    dict(id="generic_6_2_v8_supercharged", group="V8", name="Generic 6.2 L V8 supercharged",
         description="Large-displacement cross-plane V8 with a screw supercharger.",
         layout="v", cylinders=8, bore=103.25, stroke=92.0, rod=154, cr=9.5, crank="cross_plane",
         induction="supercharger_pd", boost=0.75, rpm_max=6600, ve_peak_rpm=4500, compressor_eff=0.65,
         injector_flow=800, low_friction=True, limits={"clutch": 1100, "gearbox": 1150, "cooling": 520, "pcp": 150}),
    dict(id="generic_5_2_v10_na", group="Exotic", name="Generic 5.2 L V10 naturally aspirated",
         description="90° V10 with split crankpins for even 72° firing.",
         layout="v", cylinders=10, bore=84.5, stroke=92.8, rod=154, cr=12.5, bank_angle=90,
         induction="naturally_aspirated", boost=0.0, rpm_max=8700, ve_peak_rpm=6500, injector_flow=300, ve_peak=1.05,
         lam=0.88, low_friction=True,
         limits={"clutch": 700, "gearbox": 750, "cooling": 400, "pcp": 125, "piston_speed": 27.5}),
    dict(id="generic_6_5_v12_na", group="Exotic", name="Generic 6.5 L V12 naturally aspirated",
         description="60° V12: perfectly balanced, firing every 60°.",
         layout="v", cylinders=12, bore=95.0, stroke=76.4, rod=150, cr=12.5, bank_angle=60,
         induction="naturally_aspirated", boost=0.0, rpm_max=8700, ve_peak_rpm=6750, injector_flow=330, ve_peak=1.05,
         lam=0.88, low_friction=True, limits={"clutch": 800, "gearbox": 850, "cooling": 500, "pcp": 125}),
    dict(id="generic_4l_w8_twin_turbo", group="Exotic", name="Generic 4.0 L W8 twin-turbo",
         description="Compact W8: two narrow-angle VR4 banks set at 72°.",
         layout="w", cylinders=8, bore=84.0, stroke=90.2, rod=148, cr=9.5, bank_angle=72, induction="turbo",
         boost=1.0, rpm_max=6500, ve_peak_rpm=4200, turbine_area=8.0, injector_flow=450,
         limits={"clutch": 780, "gearbox": 820, "cooling": 400, "pcp": 150}),
    dict(id="generic_6l_w12_twin_turbo", group="Exotic", name="Generic 6.0 L W12 twin-turbo",
         description="Two narrow-angle VR6 banks set at 72°: twelve cylinders in the length of a V8.",
         layout="w", cylinders=12, bore=84.0, stroke=90.2, rod=148, cr=9.3, bank_angle=72, induction="turbo",
         boost=1.1, rpm_max=6500, ve_peak_rpm=4000, turbine_area=11.0, injector_flow=480,
         limits={"clutch": 1150, "gearbox": 1200, "cooling": 560, "pcp": 155}),
    dict(id="generic_8l_w16_quad_turbo", group="Exotic", name="Generic 8.0 L W16 quad-turbo",
         description="Two VR8 banks in a W at 90°, fed by four turbos (one equivalent turbine).",
         layout="w", cylinders=16, bore=86.0, stroke=86.0, rod=145, cr=9.0, bank_angle=90, induction="turbo",
         boost=1.5, rpm_max=7000, ve_peak_rpm=4500, turbine_area=18.0, injector_flow=650,
         limits={"clutch": 1800, "gearbox": 1900, "cooling": 1000, "pcp": 170}),
    dict(id="generic_2l_flat4_na", group="Boxer", name="Generic 2.0 L flat-4 naturally aspirated",
         description="Square boxer four for a light sports car; low centre of gravity.",
         layout="flat", cylinders=4, bore=86.0, stroke=86.0, rod=130, cr=12.5, bank_angle=180,
         induction="naturally_aspirated", boost=0.0, rpm_max=7500, ve_peak_rpm=6400, injector_flow=250, ve_peak=1.0,
         lam=0.9, low_friction=True, limits={"clutch": 260, "gearbox": 280, "cooling": 150, "pcp": 115}),
    dict(id="generic_4l_flat6_na", group="Boxer", name="Generic 4.0 L flat-6 naturally aspirated",
         description="High-revving boxer six for a rear-engined sports car.",
         layout="flat", cylinders=6, bore=102.0, stroke=81.5, rod=137, cr=13.0, bank_angle=180,
         induction="naturally_aspirated", boost=0.0, rpm_max=9000, ve_peak_rpm=7000, injector_flow=360, ve_peak=1.05,
         lam=0.88, low_friction=True, limits={"clutch": 550, "gearbox": 600, "cooling": 330, "pcp": 125}),
    dict(id="generic_3_8_flat6_turbo", group="Boxer", name="Generic 3.8 L flat-6 twin-turbo",
         description="Boxer six with a turbo per bank (one equivalent turbine).",
         layout="flat", cylinders=6, bore=102.0, stroke=77.5, rod=137, cr=9.0, bank_angle=180, induction="turbo",
         boost=1.2, rpm_max=7200, ve_peak_rpm=4500, turbine_area=8.4, injector_flow=600,
         limits={"clutch": 850, "gearbox": 900, "cooling": 450, "pcp": 160}),
    dict(id="generic_1_2_v_twin", group="Motorcycle", name="Generic 1.2 L 90° V-twin",
         description="Big motorcycle twin: 270/450° firing, primary force cancelled by counterweights.",
         layout="v", cylinders=2, bore=106.0, stroke=67.9, rod=124, cr=13.0, bank_angle=90,
         induction="naturally_aspirated", boost=0.0, rpm_max=10500, ve_peak_rpm=8500, injector_flow=420, ve_peak=1.05,
         lam=0.88, low_friction=True, limits={"clutch": 150, "gearbox": 160, "cooling": 110, "pcp": 125}),
]


def _from_library(spec: dict):
    kw = {k: v for k, v in spec.items() if k not in ("id", "group", "name", "description")}
    return lambda: _derive(spec["name"], spec["description"], **kw)


def v8_na() -> EngineDesign:
    return _derive("Generic 5.0 L V8 naturally aspirated", "Cross-plane 90° V8, high compression, no boost device.",
                   layout="v", cylinders=8, bore=92.5, stroke=93.0, rod=150.0, cr=11.5, induction="naturally_aspirated",
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


# id → (name, factory, group), in the order shown in the app.
PRESETS = {
    "generic_2l_turbo": ("Generic 2.0 L turbo I4", generic_2l_turbo, "Four-cylinder performance"),
    "generic_2l_turbo_stage2": ("Generic 2.0 L turbo I4, 1.5 bar", stage2_variant, "Four-cylinder performance"),
    "generic_v6_turbo": ("Generic 3.0 L V6 turbo", v6_turbo, "Six-cylinder"),
    "generic_flat4_turbo": ("Generic 2.5 L flat-4 turbo", flat4_turbo, "Boxer"),
    "generic_v8_na": ("Generic 5.0 L V8 naturally aspirated", v8_na, "V8"),
    "generic_v8_supercharged": ("Generic 4.0 L V8 supercharged", v8_supercharged, "V8"),
    **{e["id"]: (e["name"], _from_library(e), e["group"]) for e in ENGINES},
}
PRESET_GROUPS = ["Small & economy", "Four-cylinder performance", "Six-cylinder", "V8", "Exotic", "Boxer", "Motorcycle"]

LAYOUT_PREFIX = {"inline": "I", "v": "V", "w": "W", "flat": "Flat-"}
INDUCTION_SHORT = {"turbo": "turbo", "naturally_aspirated": "NA", "supercharger_pd": "supercharged",
                   "supercharger_centrifugal": "centrifugal supercharger"}


@lru_cache(maxsize=1)
def preset_summaries() -> list[dict]:
    """Preset list for the app: id, name, group and a one-line spec (e.g. "V8 · 5.0 L · NA")."""
    out = []
    for pid, (name, factory, group) in PRESETS.items():
        d = factory()
        e, a = d.engine, d.architecture
        litres = e.cylinders * 3.141592653589793 / 4 * (e.bore.value / 1000) ** 2 * (e.stroke.value / 1000) * 1000
        out.append({"id": pid, "name": name, "group": group, "description": d.description,
                    "summary": f"{LAYOUT_PREFIX[a.layout]}{e.cylinders} · {litres:.1f} L · {INDUCTION_SHORT[a.induction]}"})
    return out
