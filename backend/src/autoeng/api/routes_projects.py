"""Projects, design version control, measurements, jobs and compute workers."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from autoeng import vcs
from autoeng.analysis.calibration import DynoRun
from autoeng.api.deps import CurrentUser, CurrentWorker, Db, user_materials
from autoeng.db.models import Branch, Job, Measurement, Project, Worker, iso
from autoeng.services import jobs, projects
from autoeng.services.projects import Conflict, NotFound
from autoeng.settings import get_settings

router = APIRouter(prefix="/api/v1")


def _guard(fn):
    try:
        return fn()
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(409, {"message": str(exc), **exc.detail}) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _project_dict(db, p: Project) -> dict:
    branches = db.scalars(select(Branch).where(Branch.project_id == p.id).order_by(Branch.name)).all()
    return {
        "id": p.id, "name": p.name, "description": p.description, "kind": p.kind,
        "default_branch": p.default_branch, "created_at": iso(p.created_at),
        "updated_at": iso(p.updated_at),
        "branches": [{"name": b.name, "head_version_id": b.head_version_id} for b in branches],
    }


# --- projects -------------------------------------------------------------------------------------

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    kind: str = "engine"
    design: dict


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


@router.get("/projects")
def list_projects(db: Db, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc()))
    return [_project_dict(db, p) for p in rows]


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, db: Db, user: CurrentUser) -> dict:
    p = _guard(lambda: projects.create_project(db, user, body.name, body.description, body.design, body.kind))
    return _project_dict(db, p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Db, user: CurrentUser) -> dict:
    return _project_dict(db, _guard(lambda: projects.get_project(db, user, project_id)))


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatch, db: Db, user: CurrentUser) -> dict:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    if body.name is not None:
        p.name = body.name
    if body.description is not None:
        p.description = body.description
    db.commit()
    return _project_dict(db, p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: Db, user: CurrentUser) -> Response:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    for model in (Branch, Measurement):
        for row in db.scalars(select(model).where(model.project_id == p.id)):
            db.delete(row)
    db.flush()
    from autoeng.db.models import Version

    db.query(Version).filter(Version.project_id == p.id).update({"parent_id": None, "merge_parent_id": None})
    db.query(Version).filter(Version.project_id == p.id).delete()
    db.delete(p)
    db.commit()
    return Response(status_code=204)


# --- version control ----------------------------------------------------------------------------

class CommitIn(BaseModel):
    branch: str
    message: str = Field(min_length=1, max_length=2000)
    design: dict
    expected_head: str | None = None


class BranchIn(BaseModel):
    name: str
    from_version_id: str


class MergeIn(BaseModel):
    source: str
    target: str
    message: str | None = None
    resolutions: dict[str, str] | None = None


class RevertIn(BaseModel):
    branch: str
    version_id: str


@router.get("/projects/{project_id}/versions")
def list_versions(project_id: str, db: Db, user: CurrentUser) -> list[dict]:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    return [projects.version_dict(v) for v in projects.history(db, p)]


@router.get("/projects/{project_id}/versions/{version_id}")
def get_version(project_id: str, version_id: str, db: Db, user: CurrentUser) -> dict:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    return projects.version_dict(_guard(lambda: projects.get_version(db, p, version_id)), include_design=True)


@router.post("/projects/{project_id}/commits", status_code=201)
def commit(project_id: str, body: CommitIn, db: Db, user: CurrentUser) -> dict:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    v = _guard(lambda: projects.commit(db, user, p, body.branch, body.message, body.design, body.expected_head))
    return projects.version_dict(v, include_design=True)


@router.post("/projects/{project_id}/branches", status_code=201)
def create_branch(project_id: str, body: BranchIn, db: Db, user: CurrentUser) -> dict:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    b = _guard(lambda: projects.create_branch(db, p, body.name, body.from_version_id))
    return {"name": b.name, "head_version_id": b.head_version_id}


@router.delete("/projects/{project_id}/branches/{name}", status_code=204)
def delete_branch(project_id: str, name: str, db: Db, user: CurrentUser) -> Response:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    _guard(lambda: projects.delete_branch(db, p, name))
    return Response(status_code=204)


@router.get("/projects/{project_id}/diff")
def diff(project_id: str, a: str, b: str, db: Db, user: CurrentUser) -> dict:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    va = _guard(lambda: projects.get_version(db, p, a))
    vb = _guard(lambda: projects.get_version(db, p, b))
    return {"a": projects.version_dict(va), "b": projects.version_dict(vb), "changes": vcs.diff(va.design, vb.design)}


@router.post("/projects/{project_id}/merge", status_code=201)
def merge(project_id: str, body: MergeIn, db: Db, user: CurrentUser) -> dict:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    v = _guard(lambda: projects.merge(db, user, p, body.source, body.target, body.message, body.resolutions))
    return projects.version_dict(v, include_design=True)


@router.post("/projects/{project_id}/revert", status_code=201)
def revert(project_id: str, body: RevertIn, db: Db, user: CurrentUser) -> dict:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    v = _guard(lambda: projects.revert_to(db, user, p, body.branch, body.version_id))
    return projects.version_dict(v, include_design=True)


# --- measurements (real-world data) ------------------------------------------------------------

class MeasurementIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version_id: str | None = None
    rpm: list[float] | None = None
    torque: list[float] | None = None
    boost: list[float] | None = None
    csv: str | None = Field(default=None, description="CSV with header: rpm,torque[,boost]")
    meta: dict = Field(default_factory=dict, description="Dyno type, correction standard, conditions, notes")


def _parse_csv(text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text.strip()))
    cols: dict[str, list[float]] = {}
    for row in reader:
        for key, value in row.items():
            if key is None or value in (None, ""):
                continue
            cols.setdefault(key.strip().lower(), []).append(float(value))
    if "rpm" not in cols or "torque" not in cols:
        raise ValueError("CSV needs 'rpm' and 'torque' columns (torque in N·m at the crank)")
    return {"rpm": cols["rpm"], "torque": cols["torque"], "boost": cols.get("boost")}


def _measurement_dict(m: Measurement) -> dict:
    return {"id": m.id, "name": m.name, "kind": m.kind, "version_id": m.version_id, "data": m.data,
            "meta": m.meta, "created_at": iso(m.created_at)}


@router.get("/projects/{project_id}/measurements")
def list_measurements(project_id: str, db: Db, user: CurrentUser) -> list[dict]:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    rows = db.scalars(select(Measurement).where(Measurement.project_id == p.id).order_by(Measurement.created_at.desc()))
    return [_measurement_dict(m) for m in rows]


@router.post("/projects/{project_id}/measurements", status_code=201)
def add_measurement(project_id: str, body: MeasurementIn, db: Db, user: CurrentUser) -> dict:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    data = _guard(lambda: _parse_csv(body.csv)) if body.csv else {"rpm": body.rpm, "torque": body.torque, "boost": body.boost}
    run = _guard(lambda: DynoRun(name=body.name, rpm=data["rpm"] or [], torque=data["torque"] or [], boost=data["boost"]))
    if body.version_id:
        _guard(lambda: projects.get_version(db, p, body.version_id))
    m = Measurement(project_id=p.id, version_id=body.version_id, name=body.name, kind="dyno",
                    data=run.model_dump(mode="json"), meta=body.meta)
    db.add(m)
    db.commit()
    return _measurement_dict(m)


@router.delete("/projects/{project_id}/measurements/{measurement_id}", status_code=204)
def delete_measurement(project_id: str, measurement_id: str, db: Db, user: CurrentUser) -> Response:
    p = _guard(lambda: projects.get_project(db, user, project_id))
    m = db.get(Measurement, measurement_id)
    if m is None or m.project_id != p.id:
        raise HTTPException(404, "Measurement not found")
    db.delete(m)
    db.commit()
    return Response(status_code=204)


# --- jobs ----------------------------------------------------------------------------------------

class JobIn(BaseModel):
    kind: str
    payload: dict
    target: str = "server"
    project_id: str | None = None


def _referenced_materials(payload: dict, mats: dict) -> list[dict]:
    """Custom materials a payload's designs use, embedded so a remote worker has them."""
    ids = set(payload.get("material_ids", []))
    for key in ("design", "baseline", "variant", "engine", "vehicle"):
        d = payload.get(key)
        if isinstance(d, dict):
            if d.get("kind") == "vehicle":
                for comp in d.get("components", {}).values():
                    if comp.get("type") == "engine_turbo_si" and comp.get("params"):
                        ids.add(comp["params"]["conrod"]["material_id"])
                    if comp.get("type") == "brakes_front" and comp.get("params"):
                        ids.add(comp["params"]["disc_material_id"])
            elif "conrod" in d:
                ids.add(d["conrod"]["material_id"])
    return [mats[i].model_dump(mode="json") for i in ids if i in mats and mats[i].custom]


@router.post("/jobs", status_code=202)
def create_job(body: JobIn, db: Db, user: CurrentUser) -> dict:
    payload = dict(body.payload)
    payload["materials"] = _referenced_materials(payload, user_materials(db, user))
    if body.project_id:
        _guard(lambda: projects.get_project(db, user, body.project_id))
    job = _guard(lambda: jobs.enqueue(db, user, body.kind, payload, body.target, body.project_id))
    return jobs.job_dict(job, include_result=False)


@router.get("/jobs")
def list_jobs(db: Db, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(Job).where(Job.owner_id == user.id).order_by(Job.created_at.desc()).limit(50))
    return [jobs.job_dict(j, include_result=False) for j in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Db, user: CurrentUser) -> dict:
    job = db.get(Job, job_id)
    if job is None or job.owner_id != user.id:
        raise HTTPException(404, "Job not found")
    return jobs.job_dict(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Db, user: CurrentUser) -> dict:
    job = db.get(Job, job_id)
    if job is None or job.owner_id != user.id:
        raise HTTPException(404, "Job not found")
    jobs.cancel(db, job)
    return jobs.job_dict(job, include_result=False)


# --- compute workers (user-owned) ----------------------------------------------------------------

class WorkerIn(BaseModel):
    name: str = Field(default="My worker", max_length=200)


@router.get("/workers")
def list_workers(db: Db, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(Worker).where(Worker.owner_id == user.id).order_by(Worker.created_at))
    return [jobs.worker_dict(w) for w in rows]


@router.post("/workers", status_code=201)
def create_worker(body: WorkerIn, db: Db, user: CurrentUser) -> dict:
    worker, code = jobs.create_worker(db, user, body.name)
    url = get_settings().public_url
    return {
        "worker": jobs.worker_dict(worker),
        "pairing_code": code,
        "expires_minutes": get_settings().worker_pairing_minutes,
        "instructions": {
            "local": f"cd backend && uv sync --extra gpu && uv run autoeng-worker --server {url} --code {code}",
            "pip": ("pip install 'autoeng[gpu] @ git+<your-repo-url>#subdirectory=backend'\n"
                    f"autoeng-worker --server {url} --code {code}"),
            "notebook": (
                "# Kaggle/Colab: enable a GPU accelerator and internet access first\n"
                "!pip install -q 'autoeng[gpu] @ git+<your-repo-url>#subdirectory=backend'\n"
                f"!autoeng-worker --server {url} --code {code}"
            ),
            "note": "The server URL must be reachable from the worker. For a notebook, expose a local server "
                    "through a tunnel or deploy it publicly.",
        },
    }


@router.delete("/workers/{worker_id}", status_code=204)
def delete_worker(worker_id: str, db: Db, user: CurrentUser) -> Response:
    w = db.get(Worker, worker_id)
    if w is None or w.owner_id != user.id:
        raise HTTPException(404, "Worker not found")
    db.delete(w)
    db.commit()
    return Response(status_code=204)


# --- worker protocol (called by the worker process) -------------------------------------------------

class PairIn(BaseModel):
    code: str
    device: dict = Field(default_factory=dict)


class ClaimIn(BaseModel):
    device: dict = Field(default_factory=dict)


class CompleteIn(BaseModel):
    result: dict | None = None
    error: str | None = None
    device: dict = Field(default_factory=dict)


@router.post("/worker/pair")
def worker_pair(body: PairIn, db: Db) -> dict:
    worker, token = _guard(lambda: jobs.pair(db, body.code, body.device))
    return {"worker_id": worker.id, "name": worker.name, "token": token}


@router.post("/worker/claim", response_model=None)
def worker_claim(body: ClaimIn, db: Db, worker: CurrentWorker) -> Response | dict:
    jobs.heartbeat(db, worker, body.device or None)
    job = jobs.claim(db, worker.id, worker.id)
    if job is None:
        return Response(status_code=204)
    return {"id": job.id, "kind": job.kind, "payload": job.payload}


@router.post("/worker/jobs/{job_id}/complete")
def worker_complete(job_id: str, body: CompleteIn, db: Db, worker: CurrentWorker) -> dict:
    job = db.get(Job, job_id)
    if job is None or job.claimed_by != worker.id:
        raise HTTPException(404, "Job not found")
    if job.status != "running":
        return {"status": job.status}
    jobs.finish(db, job, body.result, body.error, {**body.device, "runner": "worker", "worker": worker.name})
    return {"status": job.status}

