"""Metadata, accounts, materials and stateless engineering computations."""

from __future__ import annotations

import re
import threading
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from autoeng import __version__, compute
from autoeng.analysis.advisor import advise
from autoeng.analysis.calibration import CALIBRATABLE, DynoRun, calibrate
from autoeng.analysis.limits import STATUS_RULES
from autoeng.analysis.propagation import graph_dict
from autoeng.analysis.sampling import SWEEPABLE
from autoeng.analysis.simulate import DEFAULT_SAMPLES, MAX_SAMPLES, simulate
from autoeng.analysis.whatif import compare
from autoeng.api.deps import CurrentUser, Db, user_materials
from autoeng.core.params import INPUT_SOURCES
from autoeng.db.models import CustomMaterial, Research, iso
from autoeng.domain.components import CHANNELS, COMPONENTS, EDGES
from autoeng.domain.engine_design import PARAM_SPECS, EngineDesign
from autoeng.domain.fuels import FUELS
from autoeng.domain.materials import LIBRARY, PROPERTY_UNITS, Material
from autoeng.platform.body import BodyGeometry, default_geometry
from autoeng.platform.body import analyse as analyse_body
from autoeng.platform.catalog import catalog_dict
from autoeng.platform.scenarios import BUILTIN, Scenario
from autoeng.platform.simulate_scenario import run_scenario
from autoeng.platform.simulate_vehicle import simulate_vehicle
from autoeng.platform.templates import VEHICLE_TEMPLATES
from autoeng.platform.vehicle import VehicleDesign
from autoeng.presets import PRESETS
from autoeng.services import auth, community, research
from autoeng.settings import get_settings

router = APIRouter()


# --- meta ------------------------------------------------------------------------------------

@router.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "compute": compute.status(),
            "research_available": research.available(), "auth_disabled": get_settings().auth_disabled}


@router.get("/api/v1/meta")
def meta() -> dict:
    return {
        "params": [s.as_dict() for s in PARAM_SPECS.values()],
        "channels": [c.__dict__ for c in CHANNELS.values()],
        "components": [{**c.__dict__, "channels": list(c.channels), "failure_modes": list(c.failure_modes),
                        "params": list(c.params)} for c in COMPONENTS.values()],
        "edges": [{"source": a, "target": b, "kind": k} for a, b, k in EDGES],
        "model_graph": graph_dict(),
        "fuels": [f.model_dump(mode="json") for f in FUELS.values()],
        "sources": [s.value for s in INPUT_SOURCES],
        "status_rules": STATUS_RULES,
        "calibratable": CALIBRATABLE,
        "material_properties": {k: {"label": v[0], "unit": v[1]} for k, v in PROPERTY_UNITS.items()},
        "catalog": catalog_dict(),
        "engine_presets": [{"id": k, "name": v[0]} for k, v in PRESETS.items()],
        "vehicle_templates": [{"id": k, "name": v[0]} for k, v in VEHICLE_TEMPLATES.items()],
        "limits": {"max_samples": MAX_SAMPLES, "default_samples": DEFAULT_SAMPLES},
        "sweepable": SWEEPABLE,
        "scenarios": [{"id": k, **sc.model_dump(), "duration_s": sc.duration_s} for k, sc in BUILTIN.items()],
    }


@router.get("/api/v1/presets/engine/{preset_id}")
def engine_preset(preset_id: str) -> dict:
    if preset_id not in PRESETS:
        raise HTTPException(404, "Unknown preset")
    return PRESETS[preset_id][1]().model_dump(mode="json")


@router.get("/api/v1/presets/vehicle/{template_id}")
def vehicle_template(template_id: str) -> dict:
    if template_id not in VEHICLE_TEMPLATES:
        raise HTTPException(404, "Unknown template")
    return VEHICLE_TEMPLATES[template_id][1]().model_dump(mode="json")


# --- accounts ----------------------------------------------------------------------------------

class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(default="", max_length=200)


class Login(BaseModel):
    email: EmailStr
    password: str


def _user_dict(u) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name}


@router.post("/api/v1/auth/register", status_code=201)
def register(body: Register, db: Db) -> dict:
    try:
        user = auth.create_user(db, body.email, body.password, body.name)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"token": auth.issue_session(db, user), "user": _user_dict(user)}


@router.post("/api/v1/auth/login")
def login(body: Login, db: Db) -> dict:
    user = auth.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return {"token": auth.issue_session(db, user), "user": _user_dict(user)}


@router.post("/api/v1/auth/logout", status_code=204)
def logout(db: Db, user: CurrentUser, authorization: Annotated[str | None, Header()] = None) -> None:
    if authorization and authorization.lower().startswith("bearer "):
        auth.revoke(db, authorization[7:])


@router.get("/api/v1/auth/me")
def me(user: CurrentUser) -> dict:
    return _user_dict(user)


# --- materials ---------------------------------------------------------------------------------

@router.get("/api/v1/materials")
def list_materials(db: Db, user: CurrentUser) -> list[dict]:
    return [m.model_dump(mode="json") for m in user_materials(db, user).values()]


class MaterialIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    condition: str = ""
    properties: dict[str, dict]
    processes: list[str] = []
    notes: str = ""


@router.post("/api/v1/materials", status_code=201)
def create_material(body: MaterialIn, db: Db, user: CurrentUser) -> dict:
    slug = "custom_" + re.sub(r"[^a-z0-9]+", "_", f"{body.name} {body.condition}".lower()).strip("_")[:80]
    if slug in LIBRARY or db.scalar(select(CustomMaterial).where(CustomMaterial.owner_id == user.id,
                                                                  CustomMaterial.slug == slug)):
        raise HTTPException(409, "A material with this name and condition already exists")
    unknown = [k for k in body.properties if k not in PROPERTY_UNITS]
    if unknown:
        raise HTTPException(422, f"Unknown properties: {', '.join(unknown)}")
    try:
        mat = Material(id=slug, name=body.name, category=body.category, condition=body.condition,
                       properties=body.properties, processes=body.processes, notes=body.notes, custom=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if any(p.value <= 0 for k, p in mat.properties.items() if k != "cte"):
        raise HTTPException(422, "Property values must be positive")
    db.add(CustomMaterial(owner_id=user.id, slug=slug, data=mat.model_dump(mode="json")))
    db.commit()
    return mat.model_dump(mode="json")


@router.delete("/api/v1/materials/{slug}", status_code=204)
def delete_material(slug: str, db: Db, user: CurrentUser) -> None:
    row = db.scalar(select(CustomMaterial).where(CustomMaterial.owner_id == user.id, CustomMaterial.slug == slug))
    if row is None:
        raise HTTPException(404, "Custom material not found")
    db.delete(row)
    db.commit()


# --- stateless engineering compute -----------------------------------------------------------

class RunSettings(BaseModel):
    samples: int = Field(default=DEFAULT_SAMPLES, ge=1, le=MAX_SAMPLES)
    seed: int = 42


class SimulateIn(RunSettings):
    design: EngineDesign


class CompareIn(RunSettings):
    baseline: EngineDesign
    variant: EngineDesign


class AdviseIn(RunSettings):
    design: EngineDesign
    target_kw: float = Field(gt=0, le=3000)


class CalibrateIn(BaseModel):
    design: EngineDesign
    run: DynoRun
    parameters: list[str] | None = None


class VehicleIn(RunSettings):
    design: VehicleDesign


def _value_error(fn):
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/api/v1/engine/simulate")
def engine_simulate(body: SimulateIn, db: Db, user: CurrentUser) -> dict:
    mats = user_materials(db, user)
    return _value_error(lambda: simulate(body.design, mats, body.samples, body.seed))


@router.post("/api/v1/engine/compare")
def engine_compare(body: CompareIn, db: Db, user: CurrentUser) -> dict:
    mats = user_materials(db, user)
    return _value_error(lambda: compare(body.baseline, body.variant, mats, body.samples, body.seed))


@router.post("/api/v1/engine/advise")
def engine_advise(body: AdviseIn, db: Db, user: CurrentUser) -> dict:
    mats = user_materials(db, user)
    return _value_error(lambda: advise(body.design, mats, body.target_kw, body.samples, body.seed))


@router.post("/api/v1/engine/calibrate")
def engine_calibrate(body: CalibrateIn, db: Db, user: CurrentUser) -> dict:
    mats = user_materials(db, user)
    return _value_error(lambda: calibrate(body.design, mats, body.run, body.parameters))


@router.post("/api/v1/vehicle/validate")
def vehicle_validate(body: dict) -> dict:
    try:
        design = VehicleDesign.model_validate(body.get("design", body))
    except ValueError as exc:
        return {"valid": False, "errors": str(exc)}
    return {"valid": True, "architecture": design.architecture_report()}


@router.post("/api/v1/vehicle/simulate")
def vehicle_simulate(body: VehicleIn, db: Db, user: CurrentUser) -> dict:
    mats = user_materials(db, user)
    return _value_error(lambda: simulate_vehicle(body.design, mats, body.samples, body.seed))


class ScenarioIn(RunSettings):
    design: VehicleDesign
    scenario: Scenario


@router.post("/api/v1/vehicle/scenario")
def vehicle_scenario(body: ScenarioIn, db: Db, user: CurrentUser) -> dict:
    mats = user_materials(db, user)
    return _value_error(lambda: run_scenario(body.design, body.scenario, mats, min(body.samples, 400), body.seed))


# --- community learning -----------------------------------------------------------------------

class ShareIn(BaseModel):
    design: EngineDesign
    calibration: dict
    project_id: str | None = None
    consent: bool


class BodyIn(BaseModel):
    geometry: BodyGeometry


@router.get("/api/v1/body/default")
def body_default() -> dict:
    return default_geometry()


@router.post("/api/v1/body/analyze")
def body_analyze(body: BodyIn, db: Db, user: CurrentUser) -> dict:
    mats = user_materials(db, user)
    return _value_error(lambda: analyse_body(body.geometry, mats))


@router.post("/api/v1/community/share", status_code=201)
def community_share(body: ShareIn, db: Db, user: CurrentUser) -> dict:
    if not body.consent:
        raise HTTPException(422, "Sharing requires explicit consent")
    rec = community.share(db, user, body.project_id, body.design, body.calibration)
    return {"id": rec.id, "descriptors": rec.descriptors}


@router.post("/api/v1/community/suggest")
def community_suggest(body: SimulateIn, db: Db, user: CurrentUser) -> dict:
    return community.suggest(db, body.design)


# --- research assistant ----------------------------------------------------------------------------------

class ResearchIn(BaseModel):
    kind: str = Field(pattern="^(material|part)$")
    query: str = Field(min_length=3, max_length=500)


def _run_research(research_id: str) -> None:
    from autoeng.db.session import session_scope

    with session_scope() as db:
        row = db.get(Research, research_id)
        try:
            row.result = research.run(row.kind, row.query)
            row.status = "done"
        except Exception as exc:  # noqa: BLE001 - surface any failure to the user
            row.status = "failed"
            row.error = f"{type(exc).__name__}: {exc}"
        db.commit()


def _research_dict(r: Research) -> dict:
    return {"id": r.id, "kind": r.kind, "query": r.query, "status": r.status, "result": r.result,
            "error": r.error, "created_at": iso(r.created_at)}


@router.post("/api/v1/research", status_code=202)
def start_research(body: ResearchIn, db: Db, user: CurrentUser) -> dict:
    if not research.available():
        raise HTTPException(503, "The research assistant is not configured on this server (AUTOENG_RESEARCH_API_KEY)")
    row = Research(owner_id=user.id, kind=body.kind, query=body.query)
    db.add(row)
    db.commit()
    threading.Thread(target=_run_research, args=(row.id,), daemon=True).start()
    return _research_dict(row)


@router.get("/api/v1/research")
def list_research(db: Db, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(Research).where(Research.owner_id == user.id).order_by(Research.created_at.desc()).limit(50))
    return [_research_dict(r) for r in rows]


@router.get("/api/v1/research/{research_id}")
def get_research(research_id: str, db: Db, user: CurrentUser) -> dict:
    row = db.get(Research, research_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(404, "Not found")
    return _research_dict(row)

