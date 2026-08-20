"""Admission-controlled shared product memory.

Only issuer reference facts leave this repository, and they leave as typed
``CONTEXT_ONLY`` values rather than case evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiosqlite
from pydantic import ValidationError

from asx_investigator.confidence.calibration import (
    ReviewedCalibrationArtifact,
    revalidate_reviewed_calibration_artifact,
)
from asx_investigator.domain.models import IssuerReferenceFact, SharedMemoryEntry

ALLOWED_MEMORY_TYPES = {
    "ISSUER_REFERENCE",
    "PROVIDER_HEALTH",
    "CALIBRATION_ARTIFACT",
}
MEMORY_POLICY_VERSION = "shared-memory-v1"

_ALLOWED_ISSUER_REFERENCE_FIELDS = {
    "business_description",
    "commodity_exposure",
    "currency",
    "currency_exposure",
    "exchange",
    "industry",
    "sector",
}
_PROHIBITED_ISSUER_REFERENCE_CONTENT = re.compile(
    r"\b(?:"
    r"case[\s_-]*(?:claim|conclusion)|"
    r"prior[\s_-]*(?:case[\s_-]*)?(?:claim|conclusion|hypothesis)|"
    r"model[\s_-]*(?:summary|hypothesis)|"
    r"holdout[\s_-]*(?:label|case)|"
    r"sealed[\s_-]*(?:holdout|label)"
    r")\b",
    re.IGNORECASE,
)

_PROVIDER_HEALTH_STATUSES = {
    "SUCCESS",
    "EMPTY",
    "PARTIAL",
    "RETRYABLE_FAILURE",
    "PERMANENT_FAILURE",
}
_PAYLOAD_FIELDS = {
    "ISSUER_REFERENCE": {
        "ticker",
        "field",
        "value",
        "source_hash",
        "source_url",
        "valid_from",
        "valid_until",
    },
    "PROVIDER_HEALTH": {
        "provider",
        "status",
        "source_hash",
        "source_url",
        "source_version",
        "observed_at",
        "valid_until",
    },
    "CALIBRATION_ARTIFACT": {
        "calibration_version",
        "rule_version",
        "artifact_hash",
        "rule_hash",
        "source_url",
        "valid_from",
        "valid_until",
    },
}
_REQUIRED_PAYLOAD_FIELDS = {
    "ISSUER_REFERENCE": _PAYLOAD_FIELDS["ISSUER_REFERENCE"],
    "PROVIDER_HEALTH": {
        "provider",
        "status",
        "source_hash",
        "source_url",
        "observed_at",
        "valid_until",
    },
    "CALIBRATION_ARTIFACT": {
        "calibration_version",
        "rule_version",
        "artifact_hash",
        "rule_hash",
        "valid_from",
        "valid_until",
    },
}

SHARED_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS shared_memory_entries (
    entry_id TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL,
    ticker TEXT,
    payload_json TEXT NOT NULL,
    source_hash TEXT,
    source_url TEXT,
    scope TEXT NOT NULL,
    valid_from TEXT,
    valid_until TEXT,
    policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_shared_memory_active_ticker_type
    ON shared_memory_entries(ticker, memory_type)
    WHERE revoked_at IS NULL;
"""


class MemoryAdmissionError(ValueError):
    """Raised when a value is not safe for cross-case shared memory."""


class MemoryAdmissionPolicy:
    """Admit only narrow, non-case payloads with known scalar fields."""

    def validate(self, memory_type: str, payload: dict[str, object]) -> None:
        if memory_type not in ALLOWED_MEMORY_TYPES:
            raise MemoryAdmissionError(f"{memory_type} is prohibited shared memory")
        unknown = set(payload) - _PAYLOAD_FIELDS[memory_type]
        if unknown:
            raise MemoryAdmissionError(
                f"{memory_type} payload contains unknown fields: {sorted(unknown)}"
            )
        missing = _REQUIRED_PAYLOAD_FIELDS[memory_type] - set(payload)
        if missing:
            raise MemoryAdmissionError(
                f"{memory_type} payload is missing required fields: {sorted(missing)}"
            )
        if any(isinstance(value, (dict, list, tuple, set)) for value in payload.values()):
            raise MemoryAdmissionError("Shared-memory payloads cannot contain nested values")
        if memory_type == "ISSUER_REFERENCE":
            self._validate_issuer_reference(payload)
        elif memory_type == "PROVIDER_HEALTH":
            self._validate_provider_health(payload)
        else:
            self._validate_calibration_artifact(payload)

    @staticmethod
    def _require_string(payload: dict[str, object], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise MemoryAdmissionError(f"{field} must be a non-empty string")
        return value

    @staticmethod
    def _require_timestamp(payload: dict[str, object], field: str) -> datetime:
        value = payload.get(field)
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise MemoryAdmissionError(f"{field} must be a timezone-aware datetime")
        return value

    @classmethod
    def _require_hash(cls, payload: dict[str, object], field: str) -> str:
        value = cls._require_string(payload, field)
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise MemoryAdmissionError(f"{field} must be a SHA-256 hash")
        return value

    @classmethod
    def _validate_issuer_reference(cls, payload: dict[str, object]) -> None:
        for field in ("ticker", "field", "value", "source_url"):
            cls._require_string(payload, field)
        reference_field = str(payload["field"]).strip().lower()
        if reference_field not in _ALLOWED_ISSUER_REFERENCE_FIELDS:
            raise MemoryAdmissionError(
                "Issuer reference field is not in the approved allowlist"
            )
        if _PROHIBITED_ISSUER_REFERENCE_CONTENT.search(str(payload["value"])):
            raise MemoryAdmissionError(
                "Issuer reference value cannot contain case reasoning or holdout content"
            )
        cls._require_hash(payload, "source_hash")
        valid_from = cls._require_timestamp(payload, "valid_from")
        valid_until = cls._require_timestamp(payload, "valid_until")
        if valid_from >= valid_until:
            raise MemoryAdmissionError("Issuer reference validity range is invalid")

    @classmethod
    def _validate_provider_health(cls, payload: dict[str, object]) -> None:
        cls._require_string(payload, "provider")
        status = cls._require_string(payload, "status")
        if status not in _PROVIDER_HEALTH_STATUSES:
            raise MemoryAdmissionError("provider health status is not recognized")
        cls._require_hash(payload, "source_hash")
        cls._require_string(payload, "source_url")
        if "source_version" in payload:
            cls._require_string(payload, "source_version")
        observed_at = cls._require_timestamp(payload, "observed_at")
        valid_until = cls._require_timestamp(payload, "valid_until")
        if observed_at > valid_until:
            raise MemoryAdmissionError("provider health validity range is invalid")

    @classmethod
    def _validate_calibration_artifact(cls, payload: dict[str, object]) -> None:
        for field in ("calibration_version", "rule_version"):
            cls._require_string(payload, field)
        for field in ("artifact_hash", "rule_hash"):
            cls._require_hash(payload, field)
        if "source_url" in payload:
            cls._require_string(payload, "source_url")
        valid_from = cls._require_timestamp(payload, "valid_from")
        valid_until = cls._require_timestamp(payload, "valid_until")
        if valid_from >= valid_until:
            raise MemoryAdmissionError("calibration artifact validity range is invalid")


class SharedMemoryRepository:
    """Persist approved shared entries without accessing case-scoped tables."""

    def __init__(
        self,
        database_path: Path,
        policy: MemoryAdmissionPolicy | None = None,
    ) -> None:
        self.database_path = database_path
        self.policy = policy or MemoryAdmissionPolicy()

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.executescript(SHARED_MEMORY_SCHEMA)
            await connection.commit()

    async def put_reference_fact(
        self,
        *,
        ticker: str,
        field: str,
        value: str,
        source_url: str,
        source_hash: str,
        valid_until: datetime,
        valid_from: datetime | None = None,
    ) -> IssuerReferenceFact:
        if valid_from is None:
            raise MemoryAdmissionError(
                "Issuer reference facts require point-in-time availability (valid_from)"
            )
        normalized_field = field.strip().lower()
        payload: dict[str, object] = {
            "ticker": ticker,
            "field": normalized_field,
            "value": value,
            "source_hash": source_hash,
            "source_url": source_url,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }
        self.policy.validate("ISSUER_REFERENCE", payload)
        created_at = datetime.now(UTC)
        try:
            fact = IssuerReferenceFact(
                entry_id=str(uuid4()),
                ticker=ticker,
                field=normalized_field,
                value=value,
                source_hash=source_hash,
                source_url=source_url,
                valid_from=valid_from,
                valid_until=valid_until,
                policy_version=MEMORY_POLICY_VERSION,
                created_at=created_at,
            )
        except (TypeError, ValidationError, ValueError) as error:
            raise MemoryAdmissionError(
                "Issuer reference facts require valid provenance and expiry"
            ) from error
        await self._insert(
            SharedMemoryEntry(
                entry_id=fact.entry_id,
                memory_type="ISSUER_REFERENCE",
                ticker=fact.ticker,
                payload={"field": fact.field, "value": fact.value},
                source_hash=fact.source_hash,
                source_url=fact.source_url,
                scope=fact.scope,
                valid_from=fact.valid_from,
                valid_until=fact.valid_until,
                policy_version=fact.policy_version,
                created_at=fact.created_at,
            )
        )
        return fact

    async def put(
        self, memory_type: str, payload: dict[str, object]
    ) -> SharedMemoryEntry | IssuerReferenceFact:
        """Store a field-allowlisted non-case record for controlled callers."""

        if memory_type == "CALIBRATION_ARTIFACT":
            raise MemoryAdmissionError(
                "Calibration artifacts require a reviewed artifact admission"
            )
        self.policy.validate(memory_type, payload)
        if memory_type == "ISSUER_REFERENCE":
            try:
                ticker = str(payload["ticker"])
                field = str(payload["field"])
                value = str(payload["value"])
                source_url = str(payload["source_url"])
                source_hash = str(payload["source_hash"])
                valid_until = payload["valid_until"]
                valid_from = payload.get("valid_from")
                if not isinstance(valid_until, datetime) or not isinstance(valid_from, datetime):
                    raise TypeError("issuer reference validity must be datetime")
            except (KeyError, TypeError) as error:
                raise MemoryAdmissionError(
                    "Issuer reference facts require valid provenance and expiry"
                ) from error
            return await self.put_reference_fact(
                ticker=ticker,
                field=field,
                value=value,
                source_url=source_url,
                source_hash=source_hash,
                valid_until=valid_until,
                valid_from=valid_from,
            )

        created_at = datetime.now(UTC)
        try:
            entry = self._internal_entry(memory_type, payload, created_at)
        except (TypeError, ValidationError, ValueError) as error:
            raise MemoryAdmissionError("Shared memory entry is not valid") from error
        await self._insert(entry)
        return entry

    @staticmethod
    def _internal_entry(
        memory_type: str, payload: dict[str, object], created_at: datetime
    ) -> SharedMemoryEntry:
        if memory_type == "PROVIDER_HEALTH":
            return SharedMemoryEntry(
                entry_id=str(uuid4()),
                memory_type=memory_type,
                payload={
                    key: str(payload[key])
                    for key in ("provider", "status", "source_version")
                    if key in payload
                },
                source_hash=str(payload["source_hash"]),
                source_url=str(payload["source_url"]),
                scope="INTERNAL_ONLY",
                valid_from=payload["observed_at"],
                valid_until=payload["valid_until"],
                policy_version=MEMORY_POLICY_VERSION,
                created_at=created_at,
            )
        if memory_type == "CALIBRATION_ARTIFACT":
            return SharedMemoryEntry(
                entry_id=str(uuid4()),
                memory_type=memory_type,
                payload={
                    key: str(payload[key])
                    for key in ("calibration_version", "rule_version", "rule_hash")
                },
                source_hash=str(payload["artifact_hash"]),
                source_url=(
                    str(payload["source_url"])
                    if "source_url" in payload
                    else f"artifact://{payload['artifact_hash']}"
                ),
                scope="INTERNAL_ONLY",
                valid_from=payload["valid_from"],
                valid_until=payload["valid_until"],
                policy_version=MEMORY_POLICY_VERSION,
                created_at=created_at,
            )
        raise MemoryAdmissionError(f"{memory_type} has no internal entry builder")

    async def record_provider_health(
        self,
        *,
        provider: str,
        status: str,
        source_hash: str | None = None,
        source_url: str | None = None,
        observed_at: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> SharedMemoryEntry:
        """Record routing metadata that never enters a reasoning packet."""

        now = observed_at or datetime.now(UTC)
        resolved_hash = source_hash or hashlib.sha256(
            f"{provider}:{status}:{now.isoformat()}".encode()
        ).hexdigest()
        entry = await self.put(
            "PROVIDER_HEALTH",
            {
                "provider": provider,
                "status": status,
                "source_hash": resolved_hash,
                "source_url": source_url or f"provider://{provider}",
                "observed_at": now,
                "valid_until": valid_until or now + timedelta(minutes=5),
            },
        )
        assert isinstance(entry, SharedMemoryEntry)
        return entry

    async def record_calibration_artifact(
        self,
        *,
        artifact: ReviewedCalibrationArtifact,
        rule_hash: str,
        valid_from: datetime,
        valid_until: datetime,
    ) -> SharedMemoryEntry:
        """Store reviewed immutable provenance, never labels or calibration outcomes."""

        try:
            reviewed_artifact = revalidate_reviewed_calibration_artifact(artifact)
        except (TypeError, ValidationError, ValueError) as error:
            raise MemoryAdmissionError(
                "Reviewed calibration artifact failed immutable admission validation"
            ) from error

        payload: dict[str, object] = {
            "calibration_version": reviewed_artifact.artifact.artifact_version,
            "rule_version": reviewed_artifact.artifact.confidence_rule_version,
            "artifact_hash": reviewed_artifact.artifact.artifact_hash,
            "rule_hash": rule_hash,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }
        self.policy.validate("CALIBRATION_ARTIFACT", payload)
        try:
            entry = self._internal_entry("CALIBRATION_ARTIFACT", payload, datetime.now(UTC))
        except (TypeError, ValidationError, ValueError) as error:
            raise MemoryAdmissionError("Reviewed calibration artifact is not valid") from error
        await self._insert(entry)
        return entry

    async def revoke(self, entry_id: str) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """UPDATE shared_memory_entries SET revoked_at = ?
                WHERE entry_id = ? AND revoked_at IS NULL""",
                (datetime.now(UTC).isoformat(), entry_id),
            )
            await connection.commit()
        if cursor.rowcount != 1:
            raise KeyError(entry_id)

    async def list_context_facts(
        self, ticker: str, *, as_of: datetime
    ) -> list[IssuerReferenceFact]:
        """Return issuer context that was valid at the sealed case cutoff only."""

        if as_of.tzinfo is None:
            raise MemoryAdmissionError("Context selection as_of must include a timezone")

        normalized_ticker = ticker.upper().strip()
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (
                await connection.execute(
                    """SELECT entry_id, ticker, payload_json, source_hash, source_url,
                    scope, valid_from, valid_until, policy_version, created_at, revoked_at
                    FROM shared_memory_entries
                    WHERE ticker = ? AND memory_type = 'ISSUER_REFERENCE'
                    AND scope = 'CONTEXT_ONLY'
                    ORDER BY valid_from DESC, created_at DESC, entry_id""",
                    (normalized_ticker,),
                )
            ).fetchall()
        facts: list[IssuerReferenceFact] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
                fact = IssuerReferenceFact(
                    entry_id=str(row["entry_id"]),
                    ticker=str(row["ticker"]),
                    field=str(payload["field"]),
                    value=str(payload["value"]),
                    source_hash=str(row["source_hash"]),
                    source_url=str(row["source_url"]),
                    scope=str(row["scope"]),
                    valid_from=datetime.fromisoformat(str(row["valid_from"])),
                    valid_until=datetime.fromisoformat(str(row["valid_until"])),
                    policy_version=str(row["policy_version"]),
                    created_at=datetime.fromisoformat(str(row["created_at"])),
                )
            except (KeyError, TypeError, ValidationError, ValueError, json.JSONDecodeError):
                continue
            revoked_at = row["revoked_at"]
            revoked_at_value = (
                datetime.fromisoformat(str(revoked_at)) if revoked_at is not None else None
            )
            if fact.valid_until <= as_of:
                continue
            if fact.valid_from > as_of:
                continue
            if revoked_at_value is not None and revoked_at_value <= as_of:
                continue
            facts.append(fact)
        return facts

    async def _insert(self, entry: SharedMemoryEntry) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                """INSERT INTO shared_memory_entries
                (entry_id, memory_type, ticker, payload_json, source_hash, source_url, scope,
                 valid_from, valid_until, policy_version, created_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.entry_id,
                    entry.memory_type,
                    entry.ticker,
                    json.dumps(entry.payload, sort_keys=True),
                    entry.source_hash,
                    entry.source_url,
                    entry.scope,
                    (
                        entry.valid_from.astimezone(UTC).isoformat()
                        if entry.valid_from is not None
                        else None
                    ),
                    (
                        entry.valid_until.astimezone(UTC).isoformat()
                        if entry.valid_until is not None
                        else None
                    ),
                    entry.policy_version,
                    entry.created_at.astimezone(UTC).isoformat(),
                    (
                        entry.revoked_at.astimezone(UTC).isoformat()
                        if entry.revoked_at is not None
                        else None
                    ),
                ),
            )
            await connection.commit()
