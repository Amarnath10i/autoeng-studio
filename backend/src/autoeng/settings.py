from __future__ import annotations

from functools import cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTOENG_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./autoeng.db"
    # Local single-user mode: every request acts as one built-in user. Never enable on a shared server.
    auth_disabled: bool = False
    session_days: int = 30
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    auto_migrate: bool = True
    # In-process workers that run jobs targeted at the server itself.
    server_workers: int = 2
    # Public base URL workers use to reach this API (shown in the pairing instructions).
    public_url: str = "http://localhost:8000"
    worker_pairing_minutes: int = 15
    worker_offline_seconds: int = 60
    # Research assistant (web search + extraction). Disabled when no key is configured.
    research_api_key: str | None = None
    research_model: str = "claude-opus-5-5"
    default_samples: int = 200


@cache
def get_settings() -> Settings:
    return Settings()
