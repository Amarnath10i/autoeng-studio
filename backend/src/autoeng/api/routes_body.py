"""Body surface endpoints: the detailed loft, imported meshes and wind-tunnel runs."""

from __future__ import annotations

import base64
from typing import Annotated

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from autoeng.api.deps import CurrentUser, Db
from autoeng.db.models import BodyMesh, iso
from autoeng.platform import body_mesh
from autoeng.platform.body import BodyGeometry
from autoeng.services import jobs

router = APIRouter()

MAX_UPLOAD_BYTES = 40 * 1024 * 1024


class GeometryIn(BaseModel):
    geometry: BodyGeometry


class TunnelIn(BaseModel):
    geometry: BodyGeometry
    resolution: str = "standard"
    target: str = "server"
    project_id: str | None = None


def _mesh_meta(m: BodyMesh) -> dict:
    return {"id": m.id, "name": m.name, **m.info, "created_at": iso(m.created_at)}


def _own_mesh(db, user, mesh_id: str) -> BodyMesh:
    m = db.get(BodyMesh, mesh_id)
    if m is None or m.owner_id != user.id:
        raise HTTPException(404, "Mesh not found")
    return m


@router.post("/api/v1/body/mesh")
def body_loft(body: GeometryIn) -> dict:
    """The detailed lofted surface of a sketch, for rendering and export."""
    try:
        return body_mesh.loft_dict(body.geometry)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/api/v1/body/meshes", status_code=201)
async def upload_mesh(
    request: Request,
    db: Db,
    user: CurrentUser,
    filename: Annotated[str, Query(max_length=200)],
    units: str = "mm",
    up: str = "z",
    nose: str = "auto",
    ground_offset_mm: float = 0.0,
) -> dict:
    """Import an STL or OBJ (raw file bytes in the request body)."""
    data = await request.body()
    if not data:
        raise HTTPException(422, "Empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Files up to 40 MB are supported; decimate the mesh first")
    try:
        tris, info = body_mesh.normalise_mesh(body_mesh.parse_mesh(data, filename), units, up, nose, ground_offset_mm)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    info.update(units=units, up=up, nose=nose, ground_offset_mm=ground_offset_mm, filename=filename)
    name = filename.rsplit(".", 1)[0][:200] or "Imported body"
    m = BodyMesh(owner_id=user.id, name=name, info=info, triangles=tris.astype(np.float32).tobytes())
    db.add(m)
    db.commit()
    return _mesh_meta(m)


@router.get("/api/v1/body/meshes")
def list_meshes(db: Db, user: CurrentUser) -> list[dict]:
    rows = db.query(BodyMesh).filter(BodyMesh.owner_id == user.id).order_by(BodyMesh.created_at.desc()).all()
    return [_mesh_meta(m) for m in rows]


@router.get("/api/v1/body/meshes/{mesh_id}")
def get_mesh(mesh_id: str, db: Db, user: CurrentUser) -> dict:
    m = _own_mesh(db, user, mesh_id)
    return {**_mesh_meta(m), "triangles_b64": base64.b64encode(m.triangles).decode()}


@router.delete("/api/v1/body/meshes/{mesh_id}", status_code=204)
def delete_mesh(mesh_id: str, db: Db, user: CurrentUser) -> None:
    db.delete(_own_mesh(db, user, mesh_id))
    db.commit()


@router.post("/api/v1/aero/run", status_code=202)
def run_tunnel(body: TunnelIn, db: Db, user: CurrentUser) -> dict:
    """Queue a wind-tunnel job. An imported mesh is embedded so a remote worker needs nothing else."""
    payload: dict = {"geometry": body.geometry.model_dump(), "resolution": body.resolution}
    if body.geometry.mesh_id:
        m = _own_mesh(db, user, body.geometry.mesh_id)
        payload["mesh"] = {"info": m.info, "triangles_b64": base64.b64encode(m.triangles).decode()}
    try:
        job = jobs.enqueue(db, user, "wind_tunnel", payload, body.target, body.project_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return jobs.job_dict(job, include_result=False)
