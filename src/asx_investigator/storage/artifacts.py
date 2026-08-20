from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel


class ArtifactRecord(BaseModel):
    artifact_id: str
    sha256: str
    size_bytes: int
    mime_type: str
    relative_path: str


class ArtifactStore:
    """Content-addressed byte storage with deterministic identifiers."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, mime_type: str) -> ArtifactRecord:
        digest = hashlib.sha256(content).hexdigest()
        relative = Path(digest[:2]) / f"{digest}.bin"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(content)
        return ArtifactRecord(
            artifact_id=digest,
            sha256=digest,
            size_bytes=len(content),
            mime_type=mime_type,
            relative_path=str(relative),
        )

    def get(self, artifact_id: str) -> bytes:
        valid_characters = all(
            character in "0123456789abcdef" for character in artifact_id
        )
        if len(artifact_id) != 64 or not valid_characters:
            raise ValueError("artifact_id must be a lowercase SHA-256 digest")
        return (self.root / artifact_id[:2] / f"{artifact_id}.bin").read_bytes()
