from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets are environment-only and never reach the browser."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3-flash-preview"
    gemini_pricing_schedule_version: str | None = None
    gemini_input_aud_per_million_tokens: Decimal | None = None
    gemini_output_aud_per_million_tokens: Decimal | None = None
    eodhd_api_key: str | None = None
    marketstack_api_key: str | None = None
    tavily_api_key: str | None = None
    issuer_source_domains: str | None = None
    database_url: str = "sqlite+aiosqlite:///./data/asx_investigator.db"
    artifact_dir: Path = Path("data/artifacts")
