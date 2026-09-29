import math

import numpy as np
import pytest

from autoeng import compute
from autoeng.analysis import limits as lim
from autoeng.analysis.sampling import sample_design
from autoeng.analysis.simulate import run_raw, simulate
from autoeng.domain.engine_design import EngineDesign
from autoeng.domain.materials import LIBRARY
from autoeng.physics import conrod, engine_mvem, gas
from autoeng.presets import generic_2l_turbo, stage2_variant


def _modify(design: EngineDesign, path: str, value) -> EngineDesign:
    d = design.model_dump()
    node = d
    *parents, leaf = path.split(".")
    for p in parents:
        node = node[p]
    if isinstance(node[leaf], dict):
        node[leaf]["value"] = value
    else:
        node[leaf] = value
    return EngineDesign.model_validate(d)


def _nominal(design: EngineDesign):
    s = sample_design(design, LIBRARY, 1, 0)
    rpm = np.arange(design.operating.rpm_min, design.operating.rpm_max + 1, 250.0)
    return s, engine_mvem.run(s.engine, rpm), rpm


# --- gas dynamics -----------------------------------------------------------

def test_compressor_isentropic_limit():
    t2 = gas.compressor_outlet_temp(np.array(300.0), np.array(2.0), 1.0)
    assert t2 == pytest.approx(300.0 * 2.0 ** (0.4 / 1.4))


def test_flow_function_peaks_at_critical_ratio():
    g = np.array(1.33)
    xc = gas.critical_pressure_ratio(g)
    x = np.linspace(0.3, 1.0, 200)
    psi = gas.flow_function(x, g)
    assert psi.max() == pytest.approx(gas.flow_function(xc, g))
    assert gas.flow_function(np.array(1.0), g) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("p_up", [1.2e5, 1.5e5, 3.0e5])  # unchoked and choked
def test_nozzle_inversion_roundtrip(p_up):
    area, t, p_down, g = 4e-4, 1100.0, 1.1e5, np.array(1.33)
    m = gas.nozzle_mass_flow(area, np.array(p_up), np.array(t), p_down, g)
    recovered = gas.upstream_pressure_for_flow(np.atleast_1d(m), area, np.array(t), p_down, g)
    assert recovered[0] == pytest.approx(p_up, rel=1e-6)


# --- engine model -----------------------------------------------------------

def test_displacement():
    s, _, _ = _nominal(generic_2l_turbo())
    assert s.engine.displacement.item() == pytest.approx(4 * math.pi / 4 * 0.086**2 * 0.086)


def test_energy_balance_closes():
    s, out, rpm = _nominal(generic_2l_turbo())
    c = engine_mvem._Charge(s.engine, rpm[None, :], out["ve"], out["boost"])
    np.testing.assert_allclose(c.heat_released, c.indicated_power + c.heat_to_coolant + c.exhaust_heat, rtol=1e-12)
    np.testing.assert_allclose(out["heat_released"], c.heat_released, rtol=1e-12)


def test_power_equals_torque_times_speed():
    _, out, rpm = _nominal(generic_2l_turbo())
    np.testing.assert_allclose(out["power"], out["torque"] * 2 * math.pi * rpm / 60, rtol=1e-12)


def test_turbo_power_balance_and_boost_bounds():
    s, out, _ = _nominal(generic_2l_turbo())
    target = s.engine.boost_target.item()
    assert np.all(out["boost"] <= target + 1e-6)
    open_wg = out["boost_limited"] < 0.5
    assert open_wg.any() and (~open_wg).any(), "preset should spool: limited at low rpm, wastegating above"
    balance = out["turbine_power"] * s.engine.eta_mechanical - out["compressor_power"]
    # Where the wastegate controls boost the shaft power must balance.
    np.testing.assert_allclose(balance[open_wg], 0.0, atol=5.0)  # W
    # Where boost is turbine-limited the wastegate is shut.
    np.testing.assert_allclose(out["wastegate_fraction"][~open_wg], 0.0, atol=1e-9)


def test_more_boost_more_torque_at_high_rpm():
    _, base, _ = _nominal(generic_2l_turbo())
    _, more, _ = _nominal(_modify(generic_2l_turbo(), "turbo.boost_target", 1.4))
    assert np.all(more["torque"][0, -5:] > base["torque"][0, -5:])
    assert np.all(more["peak_pressure"] >= base["peak_pressure"] * (1 - 1e-6))


def test_smaller_turbine_spools_earlier():
    _, big, _ = _nominal(_modify(generic_2l_turbo(), "turbo.turbine_flow_area", 6.0))
    _, small, _ = _nominal(_modify(generic_2l_turbo(), "turbo.turbine_flow_area", 3.0))
    assert small["boost"][0, 2] > big["boost"][0, 2]
    # ...at the cost of higher exhaust back-pressure at high rpm.
    assert small["exhaust_manifold_pressure"][0, -1] > big["exhaust_manifold_pressure"][0, -1]


def test_rich_mixture_does_not_release_more_heat():
    _, stoich, _ = _nominal(_modify(generic_2l_turbo(), "combustion.lambda_ratio", 1.0))
    _, rich, _ = _nominal(_modify(generic_2l_turbo(), "combustion.lambda_ratio", 0.8))
    # Same air, more fuel: fuel flow rises but heat release per unit air cannot.
    assert np.all(rich["fuel_flow"] / rich["air_flow"] > stoich["fuel_flow"] / stoich["air_flow"])
    np.testing.assert_allclose(rich["heat_released"] / rich["air_flow"], stoich["heat_released"] / stoich["air_flow"], rtol=1e-9)


# --- connecting rod -----------------------------------------------------------

def test_i_section_properties():
    sec = conrod.i_section(0.020, 0.016, 0.004, 0.005)
    assert sec.area == pytest.approx(2 * 0.016 * 0.004 + 0.012 * 0.005)
    assert sec.inertia_in_plane == pytest.approx((0.016 * 0.020**3 - 0.011 * 0.012**3) / 12)


def test_euler_and_johnson_meet_at_transition():
    e, sy = 205e9, 710e6
    transition = math.sqrt(2 * math.pi**2 * e / sy)
    below = conrod.critical_stress(e, sy, np.array(transition * (1 - 1e-9)))
    above = conrod.critical_stress(e, sy, np.array(transition * (1 + 1e-9)))
    assert below == pytest.approx(above, rel=1e-6)
    assert below == pytest.approx(sy / 2, rel=1e-6)


def test_titanium_rod_reduces_reciprocating_mass():
    steel = run_raw(generic_2l_turbo(), LIBRARY, 1, 0)
    ti = run_raw(_modify(generic_2l_turbo(), "conrod.material_id", "ti_6al_4v_annealed"), LIBRARY, 1, 0)
    assert ti.rod["rod_mass"].item() == pytest.approx(steel.rod["rod_mass"].item() * 4430 / 7850)
    assert ti.rod["recip_mass"].item() < steel.rod["recip_mass"].item()
    assert np.all(ti.channels["rod_tensile_stress"] < steel.channels["rod_tensile_stress"])


# --- analysis ------------------------------------------------------------------

def test_status_bands():
    assert lim.status_from_sf(0.9, 0.8) == "failure"
    assert lim.status_from_sf(1.05, 1.02) == "critical"
    assert lim.status_from_sf(1.5, 0.95) == "critical"
    assert lim.status_from_sf(1.4, 1.2) == "warning"
    assert lim.status_from_sf(2.0, 1.6) == "ok"


def test_simulation_is_reproducible_and_bands_bracket_nominal():
    a = simulate(generic_2l_turbo(), LIBRARY, 100, 7)
    b = simulate(generic_2l_turbo(), LIBRARY, 100, 7)
    assert a["summary"] == b["summary"]
    pk = a["summary"]["peak_power"]
    assert pk["p05"] < pk["nominal"] < pk["p95"]


def test_stage2_flags_more_problems_than_stock():
    rank = lim.STATUS_ORDER.index
    stock = {r["id"]: r for r in simulate(generic_2l_turbo(), LIBRARY, 100, 1)["limits"]}
    stage2 = {r["id"]: r for r in simulate(stage2_variant(), LIBRARY, 100, 1)["limits"]}
    assert stage2["pcp"]["actual_nominal"] > stock["pcp"]["actual_nominal"]
    assert rank(stage2["gearbox"]["status"]) >= rank(stock["gearbox"]["status"])
    assert stock["conrod.fatigue"]["status"] == "no_data"  # 4340 normalized has no fatigue data in the library


def test_design_validation_rejects_bad_geometry():
    d = generic_2l_turbo().model_dump()
    d["conrod"]["flange_thickness"]["value"] = 12.0
    with pytest.raises(ValueError, match="flange thickness"):
        EngineDesign.model_validate(d)


@pytest.mark.skipif(not compute.gpu_available(), reason="no CUDA GPU")
def test_gpu_matches_cpu(monkeypatch):
    cpu = simulate(generic_2l_turbo(), LIBRARY, 1500, 3)
    monkeypatch.setattr(compute, "GPU_MIN_ELEMENTS", 1)
    gpu = simulate(generic_2l_turbo(), LIBRARY, 1500, 3)
    assert gpu["compute"]["backend"] == "cupy"
    assert gpu["summary"]["peak_power"]["p95"] == pytest.approx(cpu["summary"]["peak_power"]["p95"], rel=1e-9)
