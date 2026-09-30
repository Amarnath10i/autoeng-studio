"""Job queue and compute workers.

Heavy analyses run as jobs. A job targets either the server (run by in-process
workers) or one of the user's own paired workers: a process on their PC, a
Kaggle or Colab notebook, or a cloud VM, typically with a GPU. Workers connect
outbound and poll, so they work behind NAT and firewalls without port forwarding.

The job payload is self-contained (design, settings and any custom materials it
references), so a remote worker needs nothing from the database.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from autoeng import compute
from autoeng.analysis.advisor import advise
from autoeng.analysis.calibration import DynoRun, calibrate
from autoeng.analysis.simulate import simulate
from autoeng.analysis.whatif import compare
from autoeng.db.models import Job, User, Worker, iso
from autoeng.db.session import session_scope
from autoeng.domain.engine_design import EngineDesign
from autoeng.domain.materials import LIBRARY, Material
from autoeng.services.auth import token_hash
from autoeng.settings import get_settings

log = logging.getLogger(__name__)

JOB_KINDS = ("simulate", "compare", "advise", "calibrate", "vehicle", "scenario", "weather_study", "sweep",
             "material_study", "wind_tunnel")
SERVER = "server"


# --- execution (shared by the server runner and remote workers) ---------------

def _materials(payload: dict) -> dict[str, Material]:
    mats = dict(LIBRARY)
    for m in payload.get("materials", []):
        mat = Material.model_validate(m)
        mats[mat.id] = mat
    return mats


def execute(kind: str, payload: dict) -> dict:
    """Run one job payload and return its JSON result."""
    materials = _materials(payload)
    samples = int(payload.get("samples", get_settings().default_samples))
    seed = int(payload.get("seed", 42))
    if kind == "simulate":
        return simulate(EngineDesign.model_validate(payload["design"]), materials, samples, seed)
    if kind == "compare":
        return compare(EngineDesign.model_validate(payload["baseline"]), EngineDesign.model_validate(payload["variant"]),
                       materials, samples, seed)
    if kind == "advise":
        return advise(EngineDesign.model_validate(payload["design"]), materials, float(payload["target_kw"]), samples, seed)
    if kind == "calibrate":
        return calibrate(EngineDesign.model_validate(payload["design"]), materials,
                         DynoRun.model_validate(payload["run"]), payload.get("parameters"))
    return _execute_platform(kind, payload, materials, samples, seed)


def _execute_platform(kind: str, payload: dict, materials: dict, samples: int, seed: int) -> dict:
    from autoeng.analysis.study import engine_sweep, material_study, weather_study
    from autoeng.platform.scenarios import Scenario
    from autoeng.platform.simulate_scenario import run_scenario
    from autoeng.platform.simulate_vehicle import simulate_vehicle
    from autoeng.platform.vehicle import VehicleDesign

    def vehicle() -> VehicleDesign:
        return VehicleDesign.model_validate(payload["vehicle"] if "vehicle" in payload else payload["design"])

    if kind == "vehicle":
        return simulate_vehicle(vehicle(), materials, samples, seed)
    if kind == "scenario":
        return run_scenario(vehicle(), Scenario.model_validate(payload["scenario"]), materials, samples, seed)
    if kind == "weather_study":
        return weather_study(vehicle(), Scenario.model_validate(payload["scenario"]), materials,
                             payload["temperatures_c"], payload.get("altitudes_m"), samples, seed, payload.get("surface"))
    if kind == "sweep":
        return engine_sweep(EngineDesign.model_validate(payload["design"]), materials, payload["x_path"],
                            payload["x_values"], payload.get("y_path"), payload.get("y_values"), samples, seed)
    if kind == "material_study":
        return material_study(
            payload["target"], materials, payload["material_ids"],
            engine=EngineDesign.model_validate(payload["engine"]) if payload.get("engine") else None,
            vehicle=VehicleDesign.model_validate(payload["vehicle"]) if payload.get("vehicle") else None,
            scenario=Scenario.model_validate(payload["scenario"]) if payload.get("scenario") else None,
            samples=samples, seed=seed)
    if kind == "wind_tunnel":
        return wind_tunnel(payload)
    raise ValueError(f"Unknown job kind '{kind}'")


def body_geometry(payload: dict):
    """The body sketch for an aero run: given directly, from the vehicle's body component, or the default."""
    from autoeng.platform.body import BodyGeometry, default_geometry
    from autoeng.platform.vehicle import VehicleDesign

    if payload.get("geometry"):
        return BodyGeometry.model_validate(payload["geometry"])
    if payload.get("vehicle"):
        bodies = VehicleDesign.model_validate(payload["vehicle"]).of_type("body")
        if bodies and bodies[0][1].params and bodies[0][1].params.get("geometry"):
            return BodyGeometry.model_validate(bodies[0][1].params["geometry"])
    return BodyGeometry.model_validate(default_geometry())


def wind_tunnel(payload: dict) -> dict:
    from autoeng.physics import aero_lbm3d

    return aero_lbm3d.run(body_geometry(payload), payload.get("resolution", "standard"))


# --- queue ---------------------------------------------------------------------

def enqueue(db: Session, user: User, kind: str, payload: dict, target: str = SERVER, project_id: str | None = None) -> Job:
    if kind not in JOB_KINDS:
        raise ValueError(f"Unknown job kind '{kind}'")
    if target != SERVER:
        worker = db.get(Worker, target)
        if worker is None or worker.owner_id != user.id or worker.token_hash is None:
            raise ValueError("Unknown or unpaired worker")
    job = Job(owner_id=user.id, project_id=project_id, kind=kind, payload=payload, target=target)
    db.add(job)
    db.commit()
    return job


def claim(db: Session, target: str, claimant: str) -> Job | None:
    """Atomically take the oldest queued job for `target` (safe with concurrent claimants)."""
    for _ in range(5):
        job_id = db.scalar(
            select(Job.id).where(Job.status == "queued", Job.target == target).order_by(Job.created_at).limit(1)
        )
        if job_id is None:
            return None
        taken = db.execute(
            update(Job).where(Job.id == job_id, Job.status == "queued")
            .values(status="running", claimed_by=claimant, started_at=datetime.now(UTC))
        ).rowcount
        db.commit()
        if taken:
            return db.get(Job, job_id)
    return None


def finish(db: Session, job: Job, result: dict | None, error: str | None, device: dict | None = None) -> None:
    job.status = "failed" if error else "done"
    job.result = result
    job.error = error
    job.device = device or {}
    job.finished_at = datetime.now(UTC)
    db.commit()


def cancel(db: Session, job: Job) -> None:
    if job.status in ("queued", "running"):
        job.status = "cancelled"
        job.finished_at = datetime.now(UTC)
        db.commit()


def job_dict(job: Job, include_result: bool = True) -> dict:
    d = {
        "id": job.id, "kind": job.kind, "status": job.status, "target": job.target, "project_id": job.project_id,
        "error": job.error, "device": job.device, "created_at": iso(job.created_at),
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
    }
    if include_result:
        d["result"] = job.result
    return d


# --- workers ---------------------------------------------------------------------

def _format_code(raw: str) -> str:
    return f"{raw[:4]}-{raw[4:]}"


def create_worker(db: Session, user: User, name: str) -> tuple[Worker, str]:
    """Register a worker slot and return its one-time pairing code."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion
    code = _format_code("".join(secrets.choice(alphabet) for _ in range(8)))
    worker = Worker(
        owner_id=user.id, name=name.strip() or "My worker", pairing_code_hash=token_hash(code),
        pairing_expires_at=datetime.now(UTC) + timedelta(minutes=get_settings().worker_pairing_minutes),
    )
    db.add(worker)
    db.commit()
    return worker, code


def pair(db: Session, code: str, device: dict) -> tuple[Worker, str]:
    worker = db.scalar(select(Worker).where(Worker.pairing_code_hash == token_hash(code.strip().upper())))
    if worker is None:
        raise ValueError("Invalid pairing code")
    expires = worker.pairing_expires_at
    if expires is None or (expires if expires.tzinfo else expires.replace(tzinfo=UTC)) < datetime.now(UTC):
        raise ValueError("Pairing code expired; create a new one")
    token = secrets.token_urlsafe(32)
    worker.token_hash = token_hash(token)
    worker.pairing_code_hash = None
    worker.pairing_expires_at = None
    worker.device = device
    worker.last_seen_at = datetime.now(UTC)
    db.commit()
    return worker, token


def worker_for_token(db: Session, token: str) -> Worker | None:
    return db.scalar(select(Worker).where(Worker.token_hash == token_hash(token)))


def heartbeat(db: Session, worker: Worker, device: dict | None = None) -> None:
    worker.last_seen_at = datetime.now(UTC)
    if device:
        worker.device = device
    db.commit()


def worker_dict(w: Worker) -> dict:
    seen = w.last_seen_at
    if seen is not None and seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    online = seen is not None and (datetime.now(UTC) - seen).total_seconds() < get_settings().worker_offline_seconds
    return {
        "id": w.id, "name": w.name, "paired": w.token_hash is not None, "online": online,
        "device": w.device, "last_seen_at": iso(seen), "created_at": iso(w.created_at),
    }


# --- in-process server runner --------------------------------------------------------

class ServerRunner:
    """Background threads that run jobs targeted at the server."""

    def __init__(self, threads: int):
        self.threads = threads
        self._stop = threading.Event()
        self._pool: list[threading.Thread] = []

    def start(self) -> None:
        for i in range(self.threads):
            t = threading.Thread(target=self._loop, name=f"autoeng-runner-{i}", daemon=True)
            t.start()
            self._pool.append(t)

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        name = threading.current_thread().name
        while not self._stop.is_set():
            try:
                with session_scope() as db:
                    job = claim(db, SERVER, name)
                    if job is None:
                        pass
                    else:
                        self._run(db, job)
                        continue
            except Exception:  # noqa: BLE001 - keep the runner alive
                log.exception("server runner error")
            self._stop.wait(0.5)

    @staticmethod
    def _run(db: Session, job: Job) -> None:
        started = time.perf_counter()
        try:
            result = execute(job.kind, job.payload)
            device = result.get("compute") if isinstance(result, dict) else None
            finish(db, job, result, None, {**(device or compute.describe(compute.for_size(0))),
                                           "seconds": round(time.perf_counter() - started, 3), "runner": "server"})
        except Exception as exc:  # noqa: BLE001 - report any failure on the job
            log.exception("job %s failed", job.id)
            finish(db, job, None, f"{type(exc).__name__}: {exc}")
