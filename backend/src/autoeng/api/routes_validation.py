"""Model accuracy: the published benchmark report, live field evidence, and on-demand re-runs."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from autoeng.api.deps import CurrentUser, Db
from autoeng.services import jobs
from autoeng.validation.cases import CASES
from autoeng.validation.field import field_report

router = APIRouter()
PUBLISHED = Path(__file__).resolve().parents[1] / "validation" / "published.json"


class RunIn(BaseModel):
    include_heavy: bool = True
    target: str = "server"


@router.get("/api/v1/validation")
def validation(db: Db) -> dict:
    published = json.loads(PUBLISHED.read_text(encoding="utf-8")) if PUBLISHED.exists() else None
    return {
        "published": published,
        "field": field_report(db),
        "cases": [{"id": c.id, "kind": c.kind, "model": c.model, "title": c.title, "heavy": c.heavy} for c in CASES],
    }


@router.post("/api/v1/validation/run", status_code=202)
def run_validation(body: RunIn, db: Db, user: CurrentUser) -> dict:
    try:
        job = jobs.enqueue(db, user, "validation", {"include_heavy": body.include_heavy}, body.target)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return jobs.job_dict(job, include_result=False)
