"""Engine layouts, balance and induction types against textbook results."""

import numpy as np
import pytest

from autoeng.analysis.sampling import sample_design
from autoeng.domain.engine_design import EngineDesign
from autoeng.domain.materials import LIBRARY
from autoeng.physics import balance, engine_mvem
from autoeng.presets import PRESETS, generic_2l_turbo

BORE, STROKE, ROD = 0.086, 0.086, 0.145
LAM = (STROKE / 2) / ROD


def unit(layout, n, angle=90.0, crank="standard"):
    cyls = balance.arrangement(layout, n, angle, crank, BORE)
    return balance.shaking(cyls, LAM), balance.firing_intervals(cyls)


def test_inline_four_has_only_a_secondary_force():
    s, gaps = unit("inline", 4)
    assert s[1]["force"] < 1e-9 and s[1]["couple"] < 1e-9
    assert s[2]["force"] == pytest.approx(4 * LAM, rel=1e-6)  # classic 4·m·r·ω²·(r/L)
    assert s[2]["couple"] < 1e-9
    assert gaps == pytest.approx([180] * 4)


@pytest.mark.parametrize("layout,n", [("inline", 6), ("flat", 12)])
def test_inherently_balanced_layouts(layout, n):
    s, gaps = unit(layout, n)
    assert s[1]["force"] < 1e-9 and s[2]["force"] < 1e-9
    assert s[1]["couple"] < 1e-9 and s[2]["couple"] < 1e-9
    assert gaps == pytest.approx([720 / n] * n)


def test_flat_six_forces_cancel_with_small_staggered_couples():
    s, gaps = unit("flat", 6)
    assert s[1]["force"] < 1e-9 and s[2]["force"] < 1e-9
    assert gaps == pytest.approx([120] * 6)


def test_boxer_four_cancels_primary_force():
    s, _ = unit("flat", 4)
    assert s[1]["force"] < 1e-9
    assert s[2]["force"] < 1e-9  # opposed pistons cancel the secondary force too
    assert s[1]["couple"] > 0  # the bank stagger leaves a rocking couple


def test_cross_plane_v8_versus_flat_plane_v8():
    cross, gaps = unit("v", 8, 90, "cross_plane")
    flat, _ = unit("v", 8, 90, "flat_plane")
    assert cross[1]["force"] < 1e-9 and cross[2]["force"] < 1e-9
    assert cross[1]["couple"] > 0 and cross[1]["couple_rotating"]  # balanced with counterweights
    assert gaps == pytest.approx([90] * 8)
    # A 90° flat-plane V8 behaves like two inline-fours: a large horizontal secondary force.
    assert flat[2]["force"] == pytest.approx(4 * LAM * np.sqrt(2), rel=1e-3)


@pytest.mark.parametrize("layout,n,angle", [("v", 6, 60), ("v", 6, 90), ("v", 10, 90), ("v", 12, 60), ("w", 12, 72),
                                             ("w", 16, 90), ("inline", 3, 0), ("inline", 5, 0)])
def test_production_layouts_fire_evenly(layout, n, angle):
    _, gaps = unit(layout, n, angle)
    assert gaps == pytest.approx([720 / n] * n)


def test_v_twin_fires_270_450_and_its_primary_is_counterweightable():
    s, gaps = unit("v", 2, 90)
    assert sorted(gaps) == pytest.approx([270, 450])
    assert s[1]["force_rotating"]


def test_layout_validation():
    assert balance.validate_layout("v", 7)
    assert balance.validate_layout("w", 10)
    assert balance.validate_layout("inline", 4) is None
    d = generic_2l_turbo().model_dump()
    d["architecture"] = {"layout": "v", "bank_angle": d["architecture"]["bank_angle"], "crank": "standard",
                         "induction": "turbo", "supercharger_drive_efficiency": d["architecture"]["supercharger_drive_efficiency"]}
    d["engine"]["cylinders"] = 5
    with pytest.raises(ValueError, match="even count"):
        EngineDesign.model_validate(d)


def _run(design: EngineDesign):
    s = sample_design(design, LIBRARY, 1, 0)
    rpm = np.arange(design.operating.rpm_min, design.operating.rpm_max + 1, 250.0)
    return engine_mvem.run(s.engine, rpm), rpm


def _with_induction(kind: str, boost: float = 0.6) -> EngineDesign:
    d = generic_2l_turbo().model_dump()
    d["architecture"]["induction"] = kind
    d["turbo"]["boost_target"]["value"] = boost
    return EngineDesign.model_validate(d)


def test_naturally_aspirated_has_no_boost_or_turbine():
    out, _ = _run(_with_induction("naturally_aspirated"))
    np.testing.assert_allclose(out["boost"], 0.0)
    np.testing.assert_allclose(out["turbine_power"], 0.0)
    np.testing.assert_allclose(out["drive_power"], 0.0)
    np.testing.assert_allclose(out["pressure_ratio"], 1.0)


def test_positive_displacement_supercharger_holds_boost_and_costs_crank_power():
    out, _ = _run(_with_induction("supercharger_pd", 0.6))
    np.testing.assert_allclose(out["boost"], 0.6e5)
    assert np.all(out["drive_power"] > 0)
    np.testing.assert_allclose(out["drive_power"], out["compressor_power"] / 0.9, rtol=1e-9)
    na, _ = _run(_with_induction("naturally_aspirated"))
    assert np.all(out["torque"] > na["torque"])  # boost wins despite the drive loss


def test_centrifugal_supercharger_boost_rises_with_rpm_squared():
    out, rpm = _run(_with_induction("supercharger_centrifugal", 0.8))
    expected = 0.8e5 * np.clip((rpm / rpm.max()) ** 2, 0, 1)
    np.testing.assert_allclose(out["boost"][0], expected, rtol=1e-9)


@pytest.mark.parametrize("preset", list(PRESETS))
def test_every_preset_simulates(preset):
    design = PRESETS[preset][1]()
    out, _ = _run(design)
    assert np.all(np.isfinite(out["torque"])) and out["power"].max() > 50e3
