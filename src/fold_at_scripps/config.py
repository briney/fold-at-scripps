"""Application configuration loaded from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings (prefix ``FOLD_``)."""

    model_config = SettingsConfigDict(env_prefix="FOLD_", env_file=".env", extra="ignore")

    app_name: str = "fold@Scripps"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps"
    secret_key: str = "dev-insecure-secret-change-me"
    session_https_only: bool = False
    storage_root: str = "./data"
    gpu_count: int = 8
    scheduler_poll_interval: float = 2.0
    log_level: str = "INFO"
    max_upload_bytes: int = 100 * 1024 * 1024  # 100 MB request-body cap
    frontend_dist: str = "frontend/dist"


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()
