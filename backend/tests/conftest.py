"""Shared fixtures: an API client on a fresh SQLite database, and a signed-in user."""

import pytest
from fastapi.testclient import TestClient


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
