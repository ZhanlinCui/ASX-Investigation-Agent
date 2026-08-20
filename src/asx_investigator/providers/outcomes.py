from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ProviderStatus(StrEnum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    PARTIAL = "PARTIAL"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"


class ProviderOutcome[T](BaseModel):
    status: ProviderStatus
    provider: str
    retrieved_at: datetime
    coverage: str
    data: T | None = None
    provenance: dict[str, str] = Field(default_factory=dict)
    error_code: str | None = None
    source_version: str | None = None

    @model_validator(mode="after")
    def validate_data_for_success(self) -> ProviderOutcome[T]:
        if self.status in {ProviderStatus.SUCCESS, ProviderStatus.PARTIAL} and self.data is None:
            raise ValueError(f"{self.status} outcomes require data")
        return self

    @property
    def succeeded(self) -> bool:
        return self.status in {
            ProviderStatus.SUCCESS,
            ProviderStatus.EMPTY,
            ProviderStatus.PARTIAL,
        }
