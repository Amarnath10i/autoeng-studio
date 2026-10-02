"""Body styles: starting sketches for the body designer and the vehicle templates.

Dimensions are typical of each class, not of any particular car. Side profiles run from the front bumper (x = 0)
to the rear (x = 1), heights normalised between ground clearance and roof; front sections run from the underbody
centreline round the side to the roof centreline.
"""

from __future__ import annotations

from autoeng.platform.body import BodyGeometry

CAR_SECTION = [[0.0, 0.0], [0.9, 0.0], [1.0, 0.15], [1.0, 0.5], [0.93, 0.62], [0.8, 0.95], [0.5, 1.0], [0.0, 1.0]]
TALL_SECTION = [[0.0, 0.0], [0.92, 0.0], [1.0, 0.12], [1.0, 0.55], [0.95, 0.66], [0.86, 0.95], [0.55, 1.0], [0.0, 1.0]]
LOW_SECTION = [[0.0, 0.0], [0.95, 0.0], [1.0, 0.1], [1.0, 0.42], [0.9, 0.56], [0.7, 0.9], [0.45, 1.0], [0.0, 1.0]]

STYLES: dict[str, dict] = {
    "city": dict(name="City car", dims=(3650, 1650, 1500, 2400, 680, 140, 600), section=CAR_SECTION,
                 detail=dict(beltline=0.58, tumblehome=0.12),
                 side=[[0, 0.24], [0.02, 0.44], [0.12, 0.54], [0.24, 0.62], [0.38, 0.96], [0.48, 1.0], [0.85, 0.98],
                       [0.96, 0.85], [1.0, 0.3]]),
    "hatch": dict(name="Hatchback", dims=(4260, 1790, 1440, 2630, 890, 140, 640), section=CAR_SECTION,
                  detail=dict(beltline=0.6, tumblehome=0.14),
                  side=[[0.0, 0.22], [0.02, 0.42], [0.1, 0.5], [0.3, 0.58], [0.42, 0.92], [0.55, 1.0], [0.78, 0.98],
                        [0.92, 0.8], [0.99, 0.55], [1.0, 0.2]]),
    "saloon": dict(name="Saloon (sedan)", dims=(4900, 1880, 1450, 2940, 900, 135, 700), section=CAR_SECTION,
                   detail=dict(beltline=0.62, tumblehome=0.16),
                   side=[[0, 0.24], [0.02, 0.42], [0.12, 0.52], [0.3, 0.58], [0.42, 0.9], [0.52, 1.0], [0.68, 0.98],
                         [0.8, 0.72], [0.9, 0.66], [0.99, 0.6], [1.0, 0.28]]),
    "estate": dict(name="Estate (wagon)", dims=(4800, 1850, 1480, 2850, 900, 140, 680), section=CAR_SECTION,
                   detail=dict(beltline=0.6, tumblehome=0.14),
                   side=[[0, 0.22], [0.02, 0.42], [0.1, 0.5], [0.28, 0.57], [0.4, 0.92], [0.52, 1.0], [0.88, 0.97],
                         [0.97, 0.85], [1.0, 0.3]]),
    "coupe": dict(name="Fastback coupé", dims=(4500, 1880, 1320, 2650, 950, 120, 690), section=LOW_SECTION,
                  detail=dict(beltline=0.62, tumblehome=0.2, plan_taper_front=0.18),
                  side=[[0, 0.25], [0.02, 0.4], [0.15, 0.5], [0.33, 0.56], [0.46, 0.95], [0.55, 1.0], [0.7, 0.9],
                        [0.88, 0.62], [0.99, 0.55], [1.0, 0.3]]),
    "roadster": dict(name="Roadster (open top)", dims=(4000, 1740, 1240, 2310, 750, 120, 620), section=LOW_SECTION,
                     detail=dict(beltline=0.66, tumblehome=0.1),
                     side=[[0, 0.3], [0.02, 0.45], [0.2, 0.55], [0.36, 0.62], [0.45, 1.0], [0.5, 0.98], [0.56, 0.7],
                           [0.62, 0.66], [0.9, 0.66], [0.99, 0.6], [1.0, 0.32]]),
    "supercar": dict(name="Mid-engine supercar", dims=(4600, 1960, 1200, 2700, 1050, 100, 700), section=LOW_SECTION,
                     detail=dict(beltline=0.62, tumblehome=0.24, plan_taper_front=0.22, plan_taper_rear=0.12),
                     side=[[0, 0.18], [0.02, 0.3], [0.18, 0.42], [0.32, 0.52], [0.42, 0.92], [0.5, 1.0], [0.6, 0.95],
                           [0.75, 0.72], [0.95, 0.62], [1.0, 0.45]]),
    "suv": dict(name="SUV", dims=(4800, 1950, 1720, 2900, 900, 200, 760), section=TALL_SECTION,
                detail=dict(beltline=0.6, tumblehome=0.1),
                side=[[0, 0.3], [0.02, 0.5], [0.12, 0.6], [0.28, 0.66], [0.38, 0.95], [0.48, 1.0], [0.88, 0.98],
                      [0.97, 0.86], [1.0, 0.35]]),
    "pickup": dict(name="Pickup truck", dims=(5400, 1950, 1850, 3400, 950, 230, 800), section=TALL_SECTION,
                   detail=dict(beltline=0.62, tumblehome=0.08, plan_taper_rear=0.03),
                   side=[[0, 0.35], [0.02, 0.55], [0.18, 0.66], [0.3, 0.7], [0.38, 0.97], [0.44, 1.0], [0.58, 1.0],
                         [0.6, 0.66], [0.98, 0.66], [1.0, 0.4]]),
    "van": dict(name="Van / MPV", dims=(5000, 1930, 1950, 3000, 950, 170, 720), section=TALL_SECTION,
                detail=dict(beltline=0.56, tumblehome=0.06, plan_taper_rear=0.04),
                side=[[0, 0.3], [0.02, 0.5], [0.12, 0.62], [0.22, 0.8], [0.3, 0.97], [0.38, 1.0], [0.95, 1.0],
                      [0.99, 0.9], [1.0, 0.35]]),
}


def style_geometry(style_id: str, panel_material_id: str = "steel_dc04", panel_thickness_mm: float = 0.8) -> dict:
    s = STYLES[style_id]
    length, width, height, wheelbase, front_overhang, clearance, wheel = s["dims"]
    return BodyGeometry(
        length_mm=length, width_mm=width, height_mm=height, wheelbase_mm=wheelbase, front_overhang_mm=front_overhang,
        ground_clearance_mm=clearance, wheel_diameter_mm=wheel, panel_thickness_mm=panel_thickness_mm,
        panel_material_id=panel_material_id, side_profile=s["side"], front_section=s["section"], **s["detail"],
    ).model_dump()


def styles_list() -> list[dict]:
    return [{"id": k, "name": v["name"], "geometry": style_geometry(k)} for k, v in STYLES.items()]
