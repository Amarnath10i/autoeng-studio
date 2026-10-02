"""The built-in libraries: every engine, vehicle, body style, material, fuel and scenario is usable."""

import numpy as np
import pytest

from autoeng.domain.fuels import FUELS
from autoeng.domain.materials import LIBRARY, PROPERTY_UNITS
from autoeng.domain.materials_library import SYSTEMS
from autoeng.physics import longitudinal
from autoeng.platform import body_mesh
from autoeng.platform.body import BodyGeometry, analyse
from autoeng.platform.body_styles import STYLES, style_geometry
from autoeng.platform.scenarios import BUILTIN, compile_schedule
from autoeng.platform.simulate_vehicle import simulate_vehicle
from autoeng.platform.templates import VEHICLE_TEMPLATES, template_summaries
from autoeng.presets import preset_summaries


def test_preset_summaries_cover_every_layout():
    layouts = {p["summary"].split(" · ")[0].rstrip("0123456789") for p in preset_summaries()}
    assert {"I", "V", "W", "Flat-"} <= layouts
    assert len(preset_summaries()) >= 25


@pytest.mark.parametrize("tid", [t for t in VEHICLE_TEMPLATES if t != "blank"])
def test_every_vehicle_template_simulates_without_critical_limits(tid):
    r = simulate_vehicle(VEHICLE_TEMPLATES[tid][1](), LIBRARY, 30, 0)
    perf = r["performance"]
    assert 2.0 < perf["accel_0_100_s"]["nominal"] < 20
    assert 150 < perf["top_speed_kmh"]["nominal"] < 450
    assert not [lim["label"] for lim in r["limits"] if lim["status"] in ("critical", "failure")]


def test_template_summaries_name_engine_and_drive():
    s = {t["id"]: t for t in template_summaries()}
    assert "AWD" in s["generic_hypercar_w16"]["summary"] and "W16" in s["generic_hypercar_w16"]["summary"]


@pytest.mark.parametrize("style", list(STYLES))
def test_every_body_style_is_valid_and_lofts_watertight(style):
    g = BodyGeometry(**style_geometry(style))
    assert analyse(g, LIBRARY)["frontal_area_m2"] > 1.2
    tris = body_mesh.loft_triangles(g)
    dx = 0.05
    xs = np.arange(-0.1, g.length_mm / 1000 + 0.1, dx) + 0.0013
    ys = np.arange(-g.width_mm / 2000 - 0.1, g.width_mm / 2000 + 0.1, dx) + 0.0013
    zs = np.arange(0, g.height_mm / 1000 + 0.1, dx) + 0.0013
    c = [xs, ys, zs]
    z, x = body_mesh._parity(tris, (2, 0, 1), c), body_mesh._parity(tris, (0, 1, 2), c)
    assert z.sum() > 0 and (z != x).mean() < 2e-3


def test_material_library_is_well_formed():
    assert len(LIBRARY) >= 60
    for m in LIBRARY.values():
        assert m.uses and set(m.uses) <= set(SYSTEMS), m.id
        assert set(m.properties) <= set(PROPERTY_UNITS), m.id
        assert "density" in m.properties, m.id
        for key, p in m.properties.items():
            assert p.value > 0 and p.tol >= 0, (m.id, key)
        ys, uts = m.prop("yield_strength"), m.prop("ultimate_strength")
        if ys and uts:
            assert ys.value <= uts.value + 1e-9, m.id
    # Every system has materials to choose from.
    assert {u for m in LIBRARY.values() for u in m.uses} == set(SYSTEMS)


def test_brake_disc_materials_have_thermal_properties():
    for mid in ("grey_cast_iron", "grey_iron_high_carbon", "carbon_ceramic_csic", "al_mmc_sic"):
        assert LIBRARY[mid].prop("specific_heat") is not None, mid


def test_fuels_are_physical():
    for f in FUELS.values():
        assert 15 < f.lhv.value < 50 and 5 < f.afr_stoich.value < 18 and 0.4 < f.density.value < 0.9


@pytest.mark.parametrize("sid", list(BUILTIN))
def test_every_scenario_compiles(sid):
    s = compile_schedule(BUILTIN[sid])
    assert len(s["mode"]) > 0


def test_mass_factor_from_inertias():
    # A typical car in first gear: 1525 kg, r = 0.315 m, overall ratio 12, 2.0 L engine.
    g = longitudinal.mass_factor(12.0, 1525.0, 0.315, longitudinal.default_engine_inertia(2.0),
                                 longitudinal.default_wheel_inertia(0.315), 0.93)
    assert 1.15 < g < 1.35
    # Top gear barely adds to the mass.
    top = longitudinal.mass_factor(2.4, 1525.0, 0.315, longitudinal.default_engine_inertia(2.0),
                                   longitudinal.default_wheel_inertia(0.315), 0.93)
    assert 1.02 < top < 1.06
