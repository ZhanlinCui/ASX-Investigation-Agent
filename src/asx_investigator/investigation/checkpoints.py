from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class CheckpointEnvelope(BaseModel):
    """Durable, typed state from a completed investigation stage."""

    version_id: str
    stage: str
    input_artifact_hashes: list[str]
    output_artifact_hashes: list[str]
    typed_state_json: dict[str, object]
    schema_version: str = "checkpoint-v1"
    policy_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model_config = ConfigDict(frozen=True)
