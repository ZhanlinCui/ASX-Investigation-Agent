from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets are environment-only and never reach the browser."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3-flash-preview"
    eodhd_api_key: str | None = None
    marketstack_api_key: str | None = None
    tavily_api_key: str | None = None
    database_url: str = "sqlite+aiosqlite:///./data/asx_investigator.db"
    artifact_dir: Path = Path("data/artifacts")
