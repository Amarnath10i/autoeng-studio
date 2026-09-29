import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from autoeng.analysis.simulate import run_raw
from autoeng.domain.materials import LIBRARY
from autoeng.presets import generic_2l_turbo

SAMPLES = 40


@pytest.fixture(scope="module")
def client(tmp_path_factory, monkeypatch_module):
    db = tmp_path_factory.mktemp("db") / "test.db"
    monkeypatch_module.setenv("AUTOENG_DATABASE_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch_module.setenv("AUTOENG_SERVER_WORKERS", "1")
    monkeypatch_module.setenv("AUTOENG_AUTH_DISABLED", "false")
    from autoeng.db import session
    from autoeng.settings import get_settings

    get_settings.cache_clear()
    session.get_engine.cache_clear()
    session._factory.cache_clear()
    from autoeng.api.app import create_app

    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()
    session.get_engine.cache_clear()
    session._factory.cache_clear()


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/v1/auth/register", json={"email": "eng@example.com", "password": "correct-horse", "name": "Eng"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def design():
    return client_preset()


def client_preset():
    return generic_2l_turbo().model_dump(mode="json")


def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/v1/meta").json()
    assert any(p["path"] == "turbo.boost_target" for p in meta["params"])
    assert any(c["id"] == "gearbox" for c in meta["catalog"])


def test_auth_required_and_login(client, auth):
    assert client.post("/api/v1/engine/simulate", json={"design": design()}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "eng@example.com", "password": "wrong-password"})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "ENG@example.com", "password": "correct-horse"})
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth).json()["email"] == "eng@example.com"


def test_simulate_and_validation_error(client, auth):
    r = client.post("/api/v1/engine/simulate", json={"design": design(), "samples": SAMPLES}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["peak_power"]["nominal"] > 100
    assert body["trust"]["uncertainty"]["samples"] == SAMPLES
    bad = design()
    bad["turbo"]["boost_target"]["value"] = 9.0
    assert client.post("/api/v1/engine/simulate", json={"design": bad}, headers=auth).status_code == 422


def test_version_control_flow(client, auth):
    r = client.post("/api/v1/projects", json={"name": "Stage 2 build", "design": design()}, headers=auth)
    assert r.status_code == 201
    pid = r.json()["id"]
    v1 = r.json()["branches"][0]["head_version_id"]

    exp = design()
    exp["turbo"]["boost_target"]["value"] = 1.4
    r = client.post(f"/api/v1/projects/{pid}/branches", json={"name": "high-boost", "from_version_id": v1}, headers=auth)
    assert r.status_code == 201
    r = client.post(f"/api/v1/projects/{pid}/commits",
                    json={"branch": "high-boost", "message": "More boost", "design": exp}, headers=auth)
    assert r.status_code == 201
    v2 = r.json()["id"]

    main = design()
    main["intercooler"]["effectiveness"]["value"] = 0.85
    r = client.post(f"/api/v1/projects/{pid}/commits",
                    json={"branch": "main", "message": "Bigger intercooler", "design": main, "expected_head": v1},
                    headers=auth)
    assert r.status_code == 201
    # Stale head is rejected.
    r = client.post(f"/api/v1/projects/{pid}/commits",
                    json={"branch": "main", "message": "x", "design": design(), "expected_head": v1}, headers=auth)
    assert r.status_code == 409

    # Non-conflicting merge combines both changes.
    r = client.post(f"/api/v1/projects/{pid}/merge", json={"source": "high-boost", "target": "main"}, headers=auth)
    assert r.status_code == 201, r.text
    merged = r.json()["design"]
    assert merged["turbo"]["boost_target"]["value"] == 1.4
    assert merged["intercooler"]["effectiveness"]["value"] == 0.85

    changes = client.get(f"/api/v1/projects/{pid}/diff", params={"a": v1, "b": v2}, headers=auth).json()["changes"]
    assert [c["path"] for c in changes] == ["turbo.boost_target"]

    r = client.post(f"/api/v1/projects/{pid}/revert", json={"branch": "main", "version_id": v1}, headers=auth)
    assert r.status_code == 201
    assert r.json()["design"]["turbo"]["boost_target"]["value"] == 1.0
    assert len(client.get(f"/api/v1/projects/{pid}/versions", headers=auth).json()) == 5


def test_merge_conflict_reported_and_resolved(client, auth):
    pid = client.post("/api/v1/projects", json={"name": "Conflict", "design": design()}, headers=auth).json()["id"]
    v1 = client.get(f"/api/v1/projects/{pid}/versions", headers=auth).json()[0]["id"]
    client.post(f"/api/v1/projects/{pid}/branches", json={"name": "b", "from_version_id": v1}, headers=auth)
    for branch, boost in (("main", 1.2), ("b", 1.3)):
        d = design()
        d["turbo"]["boost_target"]["value"] = boost
        client.post(f"/api/v1/projects/{pid}/commits", json={"branch": branch, "message": "boost", "design": d},
                    headers=auth)
    r = client.post(f"/api/v1/projects/{pid}/merge", json={"source": "b", "target": "main"}, headers=auth)
    assert r.status_code == 409
    assert r.json()["detail"]["conflicts"][0]["path"] == "turbo.boost_target"
    r = client.post(f"/api/v1/projects/{pid}/merge",
                    json={"source": "b", "target": "main", "resolutions": {"turbo.boost_target": "theirs"}}, headers=auth)
    assert r.status_code == 201
    assert r.json()["design"]["turbo"]["boost_target"]["value"] == 1.3


def test_measurement_and_calibration(client, auth):
    pid = client.post("/api/v1/projects", json={"name": "Dyno", "design": design()}, headers=auth).json()["id"]
    rpm = np.arange(2500, 6501, 500.0)
    truth = run_raw(generic_2l_turbo(), LIBRARY, 1, 0, rpm=rpm, overrides={"combustion.efficiency_ratio": 0.70})
    csv = "rpm,torque\n" + "\n".join(f"{r},{t:.1f}" for r, t in zip(rpm, truth.channels["torque"][0], strict=True))
    r = client.post(f"/api/v1/projects/{pid}/measurements", json={"name": "Run 1", "csv": csv}, headers=auth)
    assert r.status_code == 201, r.text
    run = r.json()["data"]
    r = client.post("/api/v1/engine/calibrate",
                    json={"design": design(), "run": run, "parameters": ["combustion.efficiency_ratio"]}, headers=auth)
    assert r.status_code == 200, r.text
    fitted = r.json()["parameters"][0]
    assert fitted["after"] == pytest.approx(0.70, abs=0.005)
    assert r.json()["calibrated_design"]["combustion"]["efficiency_ratio"]["source"] == "calibrated"


def test_worker_pairing_and_jobs(client, auth):
    r = client.post("/api/v1/workers", json={"name": "Test GPU box"}, headers=auth)
    assert r.status_code == 201
    code, wid = r.json()["pairing_code"], r.json()["worker"]["id"]
    assert client.post("/api/v1/worker/pair", json={"code": "WRONG-CODE"}).status_code == 422
    r = client.post("/api/v1/worker/pair", json={"code": code.lower(), "device": {"gpu": "Test GPU"}})
    assert r.status_code == 200
    wtoken = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.post("/api/v1/worker/pair", json={"code": code}).status_code == 422  # one-time code

    payload = {"design": design(), "samples": SAMPLES}
    job = client.post("/api/v1/jobs", json={"kind": "simulate", "payload": payload, "target": wid}, headers=auth).json()
    assert job["status"] == "queued"
    claimed = client.post("/api/v1/worker/claim", json={"device": {}}, headers=wtoken)
    assert claimed.status_code == 200 and claimed.json()["id"] == job["id"]
    assert client.post("/api/v1/worker/claim", json={}, headers=wtoken).status_code == 204
    r = client.post(f"/api/v1/worker/jobs/{job['id']}/complete",
                    json={"result": {"ok": True}, "device": {"gpu": "Test GPU"}}, headers=wtoken)
    assert r.json()["status"] == "done"
    done = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert done["result"] == {"ok": True} and done["device"]["runner"] == "worker"
    assert client.get("/api/v1/workers", headers=auth).json()[0]["online"] is True

    # Server-targeted jobs are run by the in-process runner.
    job = client.post("/api/v1/jobs", json={"kind": "simulate", "payload": payload}, headers=auth).json()
    for _ in range(100):
        status = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
        if status["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert status["status"] == "done", status
    assert status["result"]["summary"]["peak_power"]["nominal"] > 100


def test_vehicle_project_and_simulation(client, auth):
    template = client.get("/api/v1/presets/vehicle/generic_hatch").json()
    r = client.post("/api/v1/projects", json={"name": "Hatch", "kind": "vehicle", "design": template}, headers=auth)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/vehicle/simulate", json={"design": template, "samples": 20}, headers=auth)
    assert r.status_code == 200, r.text
    perf = r.json()["performance"]
    assert 4 < perf["accel_0_100_s"]["nominal"] < 15
    assert 150 < perf["top_speed_kmh"]["nominal"] < 350
    broken = dict(template, connections=template["connections"] + [{"source": "engine.crank", "target": "wheels.road"}])
    assert client.post("/api/v1/vehicle/validate", json={"design": broken}).json()["valid"] is False


def test_custom_material_in_simulation(client, auth):
    body = {"name": "Test steel", "category": "Steel", "condition": "Q&T",
            "properties": {k: {"value": v, "source": "user", "tol": 0} for k, v in
                           {"density": 7800, "youngs_modulus": 200, "yield_strength": 1100,
                            "ultimate_strength": 1250, "fatigue_strength": 550}.items()}}
    r = client.post("/api/v1/materials", json=body, headers=auth)
    assert r.status_code == 201, r.text
    d = design()
    d["conrod"]["material_id"] = r.json()["id"]
    r = client.post("/api/v1/engine/simulate", json={"design": d, "samples": SAMPLES}, headers=auth)
    fatigue = next(x for x in r.json()["limits"] if x["id"] == "conrod.fatigue")
    assert fatigue["status"] != "no_data"


def test_community_learning(client, auth):
    for eff in (0.72, 0.74, 0.76, 0.75):
        cal = {"parameters": [{"path": "combustion.efficiency_ratio", "after": eff, "ci95": 0.01}],
               "torque_rmse_after": 3.0, "curves": {"rpm": [1, 2, 3]}}
        r = client.post("/api/v1/community/share", json={"design": design(), "calibration": cal, "consent": True},
                        headers=auth)
        assert r.status_code == 201
    s = client.post("/api/v1/community/suggest", json={"design": design()}, headers=auth).json()
    sug = next(x for x in s["suggestions"] if x["path"] == "combustion.efficiency_ratio")
    assert sug["value"] == pytest.approx(0.7425, abs=1e-6)
    assert sug["source"] == "community" and sug["n_effective"] >= 3


def test_scenario_and_studies(client, auth):
    template = client.get("/api/v1/presets/vehicle/generic_hatch").json()
    meta = client.get("/api/v1/meta").json()
    track = next(s for s in meta["scenarios"] if s["id"] == "track_day")
    scenario = {k: track[k] for k in ("name", "description", "weather", "segments", "repeats", "initial_speed_kmh",
                                      "cold_start", "dt_s")}
    scenario["repeats"] = 2
    r = client.post("/api/v1/vehicle/scenario", json={"design": template, "scenario": scenario, "samples": 20},
                    headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["points"][0]["max_disc_c"]["nominal"] > 200
    assert len(body["trace"]["t"]) == len(body["trace"]["nominal"]["v"][0])

    payload = {"design": generic_2l_turbo().model_dump(mode="json"), "x_path": "turbo.boost_target",
               "x_values": [0.8, 1.2, 1.6], "samples": 10}
    job = client.post("/api/v1/jobs", json={"kind": "sweep", "payload": payload}, headers=auth).json()
    for _ in range(200):
        status = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
        if status["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert status["status"] == "done", status
    power = status["result"]["metrics"]["peak_power"]["p50"][0]
    assert power[0] < power[1] < power[2]


def test_body_designer_analysis(client, auth):
    g = client.get("/api/v1/body/default").json()
    steel = client.post("/api/v1/body/analyze", json={"geometry": g}, headers=auth).json()
    assert 1.8 < steel["frontal_area_m2"] < 2.6
    g["panel_material_id"] = "al_6016_t4"
    alu = client.post("/api/v1/body/analyze", json={"geometry": g}, headers=auth).json()
    # Same shape: area identical, mass scales with density.
    assert alu["panel_area_m2"] == pytest.approx(steel["panel_area_m2"])
    assert alu["panel_mass_kg"] == pytest.approx(steel["panel_mass_kg"] * 2700 / 7850, rel=1e-6)
    # The sketch can be stored on the vehicle's body component.
    v = client.get("/api/v1/presets/vehicle/generic_hatch").json()
    v["components"]["body"]["params"]["geometry"] = g
    assert client.post("/api/v1/vehicle/validate", json={"design": v}).json()["valid"] is True
    g["side_profile"] = [[0, 0], [1, 1]]
    assert client.post("/api/v1/body/analyze", json={"geometry": g}, headers=auth).status_code == 422
