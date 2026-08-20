from pathlib import Path

from asx_investigator.storage.artifacts import ArtifactStore


def test_artifact_store_deduplicates_content_and_reads_exact_bytes(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)

    first = store.put(b"issuer announcement", mime_type="text/plain")
    second = store.put(b"issuer announcement", mime_type="text/plain")

    assert first.artifact_id == second.artifact_id
    assert first.sha256 == second.sha256
    assert store.get(first.artifact_id) == b"issuer announcement"
    assert len(list(tmp_path.rglob("*.bin"))) == 1

