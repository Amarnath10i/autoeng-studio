"""FastAPI application: `uvicorn autoeng.api.app:app`."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from autoeng import __version__
from autoeng.api import routes_body, routes_core, routes_projects, routes_validation
from autoeng.db.session import migrate
from autoeng.services.jobs import ServerRunner
from autoeng.settings import get_settings

log = logging.getLogger("autoeng")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auto_migrate:
        migrate()
    if settings.auth_disabled:
        log.warning("AUTOENG_AUTH_DISABLED is set: every request acts as one local user. Do not expose this server.")
    runner = ServerRunner(settings.server_workers)
    if settings.server_workers > 0:
        runner.start()
    yield
    runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Automotive Engineering Platform API",
        version=__version__,
        description="Design, simulate, analyse and validate automobiles and their components.",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_core.router)
    app.include_router(routes_projects.router)
    app.include_router(routes_body.router)
    app.include_router(routes_validation.router)
    return app


app = create_app()
