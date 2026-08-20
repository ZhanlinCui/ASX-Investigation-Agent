from __future__ import annotations

from datetime import UTC, datetime

from asx_investigator.domain.models import LedgerEntry, ValidationStatus

LEDGER_SCHEMA_VERSION = "ledger-v1"


class LedgerIntegrityError(ValueError):
    """The persisted audit record is not append-only or hash-bound."""


def _canonical_hashes(values: list[str]) -> list[str]:
    invalid = [
        value
        for value in values
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
    ]
    if invalid:
        raise LedgerIntegrityError("ledger input and output values must be SHA-256 hashes")
    return sorted(set(values))


class LedgerBuilder:
    """Build a case-version-scoped, append-only audit ledger."""

    def __init__(self, entries: list[LedgerEntry] | None = None) -> None:
        self._entries = [entry.model_copy(deep=True) for entry in entries or []]
        sequences = [entry.sequence for entry in self._entries]
        expected = list(range(1, len(self._entries) + 1))
        if sequences != expected:
            raise LedgerIntegrityError("ledger entry sequences must be contiguous and immutable")
        for entry in self._entries:
            if entry.schema_version != LEDGER_SCHEMA_VERSION:
                raise LedgerIntegrityError("ledger entry schema version is not supported")
            if entry.input_hashes != _canonical_hashes(entry.input_hashes):
                raise LedgerIntegrityError("ledger input hashes are not canonical")
            if entry.output_hashes != _canonical_hashes(entry.output_hashes):
                raise LedgerIntegrityError("ledger output hashes are not canonical")

    def append(
        self,
        *,
        stage: str,
        status: str,
        input_hashes: list[str],
        output_hashes: list[str],
        policy_version: str,
        model_configuration: dict[str, str],
        validation_status: ValidationStatus | None = None,
        validation_summary: str | None = None,
        created_at: datetime | None = None,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            sequence=len(self._entries) + 1,
            stage=stage,
            status=status,
            input_hashes=_canonical_hashes(input_hashes),
            output_hashes=_canonical_hashes(output_hashes),
            schema_version=LEDGER_SCHEMA_VERSION,
            policy_version=policy_version,
            model_configuration=dict(model_configuration),
            validation_status=validation_status,
            validation_summary=validation_summary,
            created_at=created_at or datetime.now(UTC),
        )
        self._entries.append(entry)
        return entry.model_copy(deep=True)

    def entries(self) -> list[LedgerEntry]:
        return [entry.model_copy(deep=True) for entry in self._entries]
