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


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()
