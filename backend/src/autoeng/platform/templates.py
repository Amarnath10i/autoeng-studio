"""Vehicle templates: a blank vehicle (spec §3 mode B) and a library of illustrative complete layouts.

Every template is generic and every value is labelled `estimated`: a starting point to edit, not the
specification of any real car. Supporting components (clutch, gearbox, axles, radiator, brakes) are sized
from each template's own engine and mass, the way a manufacturer would size them.
"""

from __future__ import annotations

from autoeng.core.params import P, Source
from autoeng.platform.body_styles import style_geometry
from autoeng.platform.vehicle import VehicleDesign
from autoeng.presets import ILLUSTRATIVE, PRESETS

EST = Source.ESTIMATED
RATING = "Illustrative rating; replace with the manufacturer's documented value"
SIZED = "Illustrative rating sized with margin over this vehicle's engine"


def _e(value: float, tol: float = 0.0, ref: str = ILLUSTRATIVE) -> dict:
    return P(round(value, 4), EST, tol, ref).model_dump(mode="json")


def blank_vehicle(name: str = "New vehicle") -> VehicleDesign:
    return VehicleDesign(name=name, description="Empty vehicle: add components from the catalog and wire them up.")


def _limit(engine: dict, lim_id: str, default: float) -> float:
    return next((lim["allowable"]["value"] for lim in engine["limits"] if lim["id"] == lim_id), default)


def _vehicle(*, name: str, description: str, engine: str, style: str, drive: str, ratios: list[float],
             final: float, tyre_radius: float, mu: float, mass: float, cd: float, area: float, cg: float,
             front: float, gearbox: str, crr: float = 0.011, launch_rpm: float = 3500, shift: float = 0.3,
             disc_material: str = "grey_cast_iron", disc_temp: float = 650, targets: dict | None = None,
             vehicle_type: str = "passenger_car", panel: str = "steel_dc04") -> VehicleDesign:
    eng = PRESETS[engine][1]().model_dump(mode="json")
    clutch_rating = _limit(eng, "clutch", 400)
    gearbox_rating = _limit(eng, "gearbox", 400)
    heat = _limit(eng, "cooling", 150) / 1.3  # the engine's peak heat to coolant
    eng["limits"] = [lim for lim in eng["limits"] if lim["component"] not in ("clutch", "gearbox")]
    geometry = style_geometry(style, panel)
    wheelbase = geometry["wheelbase_mm"] / 1000
    axle_rating = gearbox_rating * ratios[0] * final * 1.15
    disc_mass = 6.0 + 0.0045 * mass  # kg per front disc, scaled with vehicle mass
    is_dct = "dual-clutch" in gearbox or "sequential" in gearbox
    return VehicleDesign.model_validate({
        "name": name,
        "description": description,
        "vehicle_type": vehicle_type,
        "components": {
            "engine": {"type": "engine_turbo_si", "name": PRESETS[engine][0].removeprefix("Generic "), "params": eng},
            "clutch": {"type": "clutch", "name": "Twin wet clutch" if is_dct else "Clutch",
                       "params": {"torque_capacity": _e(clutch_rating, clutch_rating * 0.05, SIZED),
                                  "launch_rpm": _e(launch_rpm, 300, "Driver launch technique (engine rpm held during clutch slip)")}},
            "gearbox": {"type": "gearbox", "name": gearbox,
                        "params": {"ratios": ratios, "efficiency": _e(0.95 if "automatic" in gearbox else 0.96, 0.01),
                                   "input_torque_rating": _e(gearbox_rating, gearbox_rating * 0.03, SIZED),
                                   "shift_time": _e(shift, shift * 0.2)}},
            "final_drive": {"type": "final_drive", "name": "Final drive & differential" + (" (AWD)" if drive == "all" else ""),
                            "params": {"ratio": _e(final), "efficiency": _e(0.95 if drive == "all" else 0.97, 0.01),
                                       "axle_torque_rating": _e(axle_rating, axle_rating * 0.05, SIZED)}},
            "wheels": {"type": "wheel_tire", "name": "Wheels & tyres",
                       "params": {"rolling_radius": _e(tyre_radius, 0.003), "rolling_resistance": _e(crr, 0.002),
                                  "peak_friction": _e(mu, 0.1, "Typical dry-asphalt peak friction for this tyre class"),
                                  "driven_axle": drive}},
            "body": {"type": "body", "name": "Body & mass properties",
                     "params": {"mass": _e(mass, mass * 0.015), "drag_coefficient": _e(cd, 0.02), "frontal_area": _e(area, 0.05),
                                "wheelbase": _e(wheelbase), "cg_height": _e(cg, 0.03),
                                "front_weight_fraction": _e(front, 0.01), "geometry": geometry}},
            "radiator": {"type": "radiator", "name": "Radiator, fan & thermostat",
                         "params": {"rated_heat_rejection": _e(heat * 0.75, heat * 0.06, SIZED), "rated_delta_t": _e(70),
                                    "rated_airspeed": _e(100), "fan_airflow_fraction": _e(0.35, 0.05),
                                    "airflow_exponent": _e(0.6, 0.1, "Typical heat-exchanger airflow scaling (estimated)"),
                                    "circuit_thermal_capacity": _e(80 + 0.05 * mass, 30), "thermostat_open": _e(88),
                                    "thermostat_full_open": _e(100),
                                    "max_coolant_temp": _e(118, 3, "Boiling margin of a ~1.2 bar pressurised system")}},
            "brakes": {"type": "brakes_front", "name": "Front brakes",
                       "params": {"disc_material_id": disc_material,
                                  "disc_mass": _e(disc_mass * (0.5 if disc_material == "carbon_ceramic_csic" else 1.0), 0.3),
                                  "disc_cooling_area": _e(0.10 + 0.00004 * mass, 0.02), "front_bias": _e(0.62 + 0.2 * front, 0.02),
                                  "h_standstill": _e(15, 5), "h_speed_coeff": _e(12, 3),
                                  "emissivity": _e(0.55, 0.1, "Oxidised disc surface (estimated)"),
                                  "max_disc_temp": _e(disc_temp, 30, "Illustrative fade limit for this pad and disc")}},
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
        "targets": targets or {},
    })


AUTO8 = [5.0, 3.2, 2.14, 1.72, 1.31, 1.0, 0.82, 0.64]

TEMPLATES: list[dict] = [
    dict(id="generic_city_fwd", group="Everyday", name="Generic city car (FWD)",
         description="Small front-wheel-drive city car with a 1.0 L turbo three.",
         engine="generic_1l_i3_turbo", style="city", drive="front", gearbox="5-speed manual",
         ratios=[3.55, 1.95, 1.28, 0.97, 0.78], final=4.1, tyre_radius=0.30, mu=0.95, mass=1100, cd=0.31, area=2.05,
         cg=0.52, front=0.62, crr=0.010, launch_rpm=2800, targets={"accel_0_100_s": 10.5}),
    dict(id="generic_hatch", group="Everyday", name="Generic 2.0 L turbo hatchback (FWD)",
         description="Front-wheel-drive hatchback with a six-speed manual gearbox.",
         engine="generic_2l_turbo", style="hatch", drive="front", gearbox="6-speed manual",
         ratios=[3.46, 2.05, 1.30, 1.03, 0.84, 0.69], final=3.47, tyre_radius=0.315, mu=1.0, mass=1525, cd=0.32,
         area=2.2, cg=0.53, front=0.61, targets={"accel_0_100_s": 7.0, "top_speed_kmh": 240}),
    dict(id="generic_estate_fwd", group="Everyday", name="Generic family estate (FWD)",
         description="Practical estate with a 1.6 L naturally aspirated four.",
         engine="generic_1_6_i4_na", style="estate", drive="front", gearbox="6-speed manual",
         ratios=[3.73, 2.05, 1.36, 1.03, 0.82, 0.69], final=4.06, tyre_radius=0.315, mu=0.95, mass=1450, cd=0.30,
         area=2.25, cg=0.55, front=0.6, launch_rpm=2500),
    dict(id="generic_hot_hatch_awd", group="Performance", name="Generic hot hatch (AWD)",
         description="All-wheel-drive hot hatch with a high-output 2.0 L turbo and a dual-clutch gearbox.",
         engine="generic_2l_i4_hot", style="hatch", drive="all", gearbox="7-speed dual-clutch",
         ratios=[3.56, 2.53, 1.68, 1.02, 0.79, 0.79 * 0.85, 0.79 * 0.72], final=3.6, tyre_radius=0.325, mu=1.05,
         mass=1550, cd=0.33, area=2.2, cg=0.52, front=0.6, launch_rpm=4000, shift=0.1,
         targets={"accel_0_100_s": 4.8}),
    dict(id="generic_saloon_rwd", group="Performance", name="Generic sports saloon (RWD)",
         description="Rear-wheel-drive saloon with a 3.0 L turbo straight-six and an 8-speed automatic.",
         engine="generic_3l_i6_turbo", style="saloon", drive="rear", gearbox="8-speed automatic", ratios=AUTO8,
         final=3.15, tyre_radius=0.335, mu=1.05, mass=1720, cd=0.27, area=2.3, cg=0.55, front=0.52, shift=0.15,
         targets={"accel_0_100_s": 4.6, "top_speed_kmh": 250}),
    dict(id="generic_coupe_v8_rwd", group="Performance", name="Generic GT coupé, V8 twin-turbo (RWD)",
         description="Front-engined grand tourer with a 4.0 L twin-turbo V8 and a transaxle dual-clutch gearbox.",
         engine="generic_4l_v8_twin_turbo", style="coupe", drive="rear", gearbox="7-speed dual-clutch",
         ratios=[3.40, 2.19, 1.63, 1.29, 1.03, 0.84, 0.63], final=3.3, tyre_radius=0.345, mu=1.15, mass=1750,
         cd=0.32, area=2.15, cg=0.5, front=0.53, launch_rpm=3800, shift=0.1, targets={"accel_0_100_s": 3.8}),
    dict(id="generic_muscle_rwd", group="Performance", name="Generic muscle car, supercharged V8 (RWD)",
         description="Big supercharged V8, six-speed manual, rear-wheel drive.",
         engine="generic_6_2_v8_supercharged", style="coupe", drive="rear", gearbox="6-speed manual",
         ratios=[2.66, 1.78, 1.30, 1.00, 0.74, 0.50], final=3.73, tyre_radius=0.35, mu=1.1, mass=1870, cd=0.36,
         area=2.3, cg=0.53, front=0.54, launch_rpm=3000),
    dict(id="generic_roadster_rwd", group="Sports", name="Generic lightweight roadster (RWD)",
         description="Small open two-seater with a high-revving 2.0 L four and a short-throw six-speed.",
         engine="generic_2l_i4_na_screamer", style="roadster", drive="rear", gearbox="6-speed manual",
         ratios=[3.50, 2.20, 1.57, 1.21, 1.00, 0.84], final=4.1, tyre_radius=0.30, mu=1.05, mass=1080, cd=0.36,
         area=1.9, cg=0.45, front=0.5, launch_rpm=5000, panel="al_6016_t4"),
    dict(id="generic_rear_engine_flat6", group="Sports", name="Generic rear-engined sports car, flat-6 (RWD)",
         description="Boxer six behind the rear axle: traction-rich, tail-heavy.",
         engine="generic_4l_flat6_na", style="coupe", drive="rear", gearbox="7-speed dual-clutch",
         ratios=[3.75, 2.38, 1.72, 1.34, 1.11, 0.96, 0.84], final=3.97, tyre_radius=0.345, mu=1.2, mass=1450,
         cd=0.33, area=2.0, cg=0.46, front=0.39, launch_rpm=5500, shift=0.08, disc_temp=750),
    dict(id="generic_track_car", group="Sports", name="Generic track car (RWD, semi-slicks)",
         description="Stripped-out 900 kg track car on semi-slick tyres with a sequential gearbox.",
         engine="generic_2l_i4_na_screamer", style="roadster", drive="rear", gearbox="6-speed sequential",
         ratios=[2.92, 2.06, 1.62, 1.32, 1.10, 0.95], final=4.1, tyre_radius=0.31, mu=1.4, mass=900, cd=0.45,
         area=1.7, cg=0.38, front=0.42, launch_rpm=6000, shift=0.05, disc_material="grey_iron_high_carbon",
         disc_temp=750, panel="cfrp_qi"),
    dict(id="generic_supercar_v10", group="Supercar", name="Generic mid-engine supercar, V10 (RWD)",
         description="Mid-engined V10 with carbon-ceramic brakes.",
         engine="generic_5_2_v10_na", style="supercar", drive="rear", gearbox="7-speed dual-clutch",
         ratios=[3.13, 2.19, 1.69, 1.38, 1.16, 0.97, 0.82], final=4.0, tyre_radius=0.355, mu=1.25, mass=1600,
         cd=0.36, area=2.0, cg=0.42, front=0.42, launch_rpm=6000, shift=0.07, disc_material="carbon_ceramic_csic",
         disc_temp=900, panel="al_6016_t4", targets={"accel_0_100_s": 3.2}),
    dict(id="generic_supercar_v8tt", group="Supercar", name="Generic mid-engine supercar, V8 twin-turbo (RWD)",
         description="Mid-engined twin-turbo V8 with carbon bodywork and carbon-ceramic brakes.",
         engine="generic_4l_v8_twin_turbo", style="supercar", drive="rear", gearbox="7-speed dual-clutch",
         ratios=[3.13, 2.19, 1.69, 1.38, 1.16, 0.97, 0.82], final=3.6, tyre_radius=0.355, mu=1.25, mass=1500,
         cd=0.36, area=2.0, cg=0.41, front=0.41, launch_rpm=4500, shift=0.07, disc_material="carbon_ceramic_csic",
         disc_temp=900, panel="cfrp_qi"),
    dict(id="generic_hypercar_w16", group="Supercar", name="Generic hypercar, W16 quad-turbo (AWD)",
         description="Eight-litre W16 with all-wheel drive: the extreme end of the combustion era.",
         engine="generic_8l_w16_quad_turbo", style="supercar", drive="all", gearbox="7-speed dual-clutch",
         ratios=[3.18, 2.26, 1.68, 1.29, 1.02, 0.84, 0.69], final=3.6, tyre_radius=0.36, mu=1.25, mass=1995,
         cd=0.38, area=2.1, cg=0.45, front=0.44, launch_rpm=3500, shift=0.08, disc_material="carbon_ceramic_csic",
         disc_temp=950, panel="cfrp_qi", targets={"accel_0_100_s": 2.6, "top_speed_kmh": 400}),
    dict(id="generic_suv_awd", group="Utility", name="Generic SUV, V6 turbo (AWD)",
         description="Tall all-wheel-drive SUV with an 8-speed automatic.",
         engine="generic_v6_turbo", style="suv", drive="all", gearbox="8-speed automatic", ratios=AUTO8,
         final=3.55, tyre_radius=0.37, mu=0.95, mass=2150, cd=0.35, area=2.8, cg=0.68, front=0.53, crr=0.012,
         shift=0.15, vehicle_type="suv"),
    dict(id="generic_pickup_rwd", group="Utility", name="Generic pickup, V8 (RWD)",
         description="Full-size pickup with a naturally aspirated V8 and a 6-speed automatic.",
         engine="generic_v8_na", style="pickup", drive="rear", gearbox="6-speed automatic",
         ratios=[4.17, 2.34, 1.52, 1.14, 0.86, 0.69], final=3.55, tyre_radius=0.40, mu=0.9, mass=2350, cd=0.45,
         area=3.3, cg=0.75, front=0.57, crr=0.013, launch_rpm=2500, shift=0.2, vehicle_type="light_truck"),
    dict(id="generic_van_fwd", group="Utility", name="Generic people carrier (FWD)",
         description="Seven-seat MPV with a 2.0 L turbo and an 8-speed automatic.",
         engine="generic_2l_turbo", style="van", drive="front", gearbox="8-speed automatic", ratios=AUTO8,
         final=3.4, tyre_radius=0.34, mu=0.95, mass=1950, cd=0.33, area=3.1, cg=0.65, front=0.58, crr=0.012,
         shift=0.15, vehicle_type="mpv"),
]


def _template_factory(spec: dict):
    kw = {k: v for k, v in spec.items() if k not in ("id", "group")}
    return lambda: _vehicle(**kw)


VEHICLE_TEMPLATES = {
    **{t["id"]: (t["name"], _template_factory(t), t["group"]) for t in TEMPLATES},
    "blank": ("Blank vehicle (build from scratch)", blank_vehicle, "Start from scratch"),
}
TEMPLATE_GROUPS = ["Everyday", "Performance", "Sports", "Supercar", "Utility", "Start from scratch"]


def generic_hatch() -> VehicleDesign:
    return VEHICLE_TEMPLATES["generic_hatch"][1]()


def template_summaries() -> list[dict]:
    """Template list for the app: id, name, group, description and the engine and drive it uses."""
    by_id = {t["id"]: t for t in TEMPLATES}
    drive = {"front": "FWD", "rear": "RWD", "all": "AWD"}
    out = []
    for tid, (name, _, group) in VEHICLE_TEMPLATES.items():
        t = by_id.get(tid)
        out.append({"id": tid, "name": name, "group": group,
                    "description": t["description"] if t else "Empty vehicle: add components from the catalog.",
                    "summary": f"{PRESETS[t['engine']][0].removeprefix('Generic ')} · {drive[t['drive']]} · {t['mass']:.0f} kg"
                    if t else "Build from scratch"})
    return out

