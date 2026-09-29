from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from autoeng.db.models import CustomMaterial, User, Worker
from autoeng.db.session import get_db
from autoeng.domain.materials import LIBRARY, Material
from autoeng.services import auth, jobs
from autoeng.settings import get_settings

Db = Annotated[Session, Depends(get_db)]


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(db: Db, authorization: Annotated[str | None, Header()] = None) -> User:
    if get_settings().auth_disabled:
        return auth.local_user(db)
    token = _bearer(authorization)
    user = auth.user_for_token(db, token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def current_worker(db: Db, authorization: Annotated[str | None, Header()] = None) -> Worker:
    token = _bearer(authorization)
    worker = jobs.worker_for_token(db, token) if token else None
    if worker is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown worker token")
    return worker


CurrentWorker = Annotated[Worker, Depends(current_worker)]


def user_materials(db: Session, user: User) -> dict[str, Material]:
    mats = dict(LIBRARY)
    for row in db.scalars(select(CustomMaterial).where(CustomMaterial.owner_id == user.id)):
        m = Material.model_validate(row.data)
        mats[m.id] = m
    return mats
