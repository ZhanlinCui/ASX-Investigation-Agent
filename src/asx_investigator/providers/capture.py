from __future__ import annotations

import json

from asx_investigator.storage.artifacts import ArtifactReference, ArtifactStore


def canonical_json_bytes(payload: object) -> bytes:
    """Serialize a provider payload deterministically before parsing or use."""

    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


freeze_json_payload = canonical_json_bytes


def capture_provider_payload(
    store: ArtifactStore, payload: object, mime_type: str
) -> ArtifactReference:
    record = store.put(canonical_json_bytes(payload), mime_type)
    return ArtifactReference.model_validate(record.model_dump())
