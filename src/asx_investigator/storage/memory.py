"""Admission-controlled shared product memory.

Only issuer reference facts leave this repository, and they leave as typed
``CONTEXT_ONLY`` values rather than case evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite
from pydantic import ValidationError

from asx_investigator.domain.models import IssuerReferenceFact, SharedMemoryEntry

ALLOWED_MEMORY_TYPES = {
    "ISSUER_REFERENCE",
    "PROVIDER_HEALTH",
    "CALIBRATION_ARTIFACT",
}
MEMORY_POLICY_VERSION = "shared-memory-v1"

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
    """Allowlist shared-memory types and issuer-fact provenance requirements."""

    def validate(self, memory_type: str, payload: dict[str, object]) -> None:
        if memory_type not in ALLOWED_MEMORY_TYPES:
            raise MemoryAdmissionError(f"{memory_type} is prohibited shared memory")
        if memory_type == "ISSUER_REFERENCE":
            required = {
                "ticker",
                "field",
                "value",
                "source_hash",
                "source_url",
                "valid_until",
            }
            if not required.issubset(payload):
                raise MemoryAdmissionError(
                    "Issuer reference facts require provenance and expiry"
                )


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
        payload: dict[str, object] = {
            "ticker": ticker,
            "field": field,
            "value": value,
            "source_hash": source_hash,
            "source_url": source_url,
            "valid_until": valid_until,
        }
        if valid_from is not None:
            payload["valid_from"] = valid_from
        self.policy.validate("ISSUER_REFERENCE", payload)
        created_at = datetime.now(UTC)
        try:
            fact = IssuerReferenceFact(
                entry_id=str(uuid4()),
                ticker=ticker,
                field=field,
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
        """Store a policy-approved non-case entry for controlled internal callers."""

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
                if not isinstance(valid_until, datetime) or (
                    valid_from is not None and not isinstance(valid_from, datetime)
                ):
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
        source_hash = payload.get("source_hash")
        source_url = payload.get("source_url")
        valid_from = payload.get("valid_from")
        valid_until = payload.get("valid_until")
        try:
            entry = SharedMemoryEntry(
                entry_id=str(uuid4()),
                memory_type=memory_type,
                ticker=(str(payload["ticker"]).upper().strip() if "ticker" in payload else None),
                payload=dict(payload),
                source_hash=str(source_hash) if source_hash is not None else None,
                source_url=str(source_url) if source_url is not None else None,
                scope="INTERNAL_ONLY",
                valid_from=valid_from if isinstance(valid_from, datetime) else None,
                valid_until=valid_until if isinstance(valid_until, datetime) else None,
                policy_version=MEMORY_POLICY_VERSION,
                created_at=created_at,
            )
        except (TypeError, ValidationError, ValueError) as error:
            raise MemoryAdmissionError("Shared memory entry is not valid") from error
        await self._insert(entry)
        return entry

    async def record_provider_health(
        self,
        *,
        provider: str,
        status: str,
        source_hash: str | None = None,
        source_url: str | None = None,
        valid_until: datetime | None = None,
    ) -> SharedMemoryEntry:
        """Record routing metadata that never enters a reasoning packet."""

        now = datetime.now(UTC)
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
                "valid_until": valid_until or now,
            },
        )
        assert isinstance(entry, SharedMemoryEntry)
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

    async def list_context_facts(self, ticker: str) -> list[IssuerReferenceFact]:
        """Return only active issuer facts eligible for non-causal packet context."""

        normalized_ticker = ticker.upper().strip()
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (
                await connection.execute(
                    """SELECT entry_id, ticker, payload_json, source_hash, source_url,
                    scope, valid_from, valid_until, policy_version, created_at
                    FROM shared_memory_entries
                    WHERE ticker = ? AND memory_type = 'ISSUER_REFERENCE'
                    AND scope = 'CONTEXT_ONLY' AND revoked_at IS NULL
                    ORDER BY created_at, entry_id""",
                    (normalized_ticker,),
                )
            ).fetchall()
        now = datetime.now(UTC)
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
                    valid_from=(
                        datetime.fromisoformat(str(row["valid_from"]))
                        if row["valid_from"] is not None
                        else None
                    ),
                    valid_until=datetime.fromisoformat(str(row["valid_until"])),
                    policy_version=str(row["policy_version"]),
                    created_at=datetime.fromisoformat(str(row["created_at"])),
                )
            except (KeyError, TypeError, ValidationError, ValueError, json.JSONDecodeError):
                continue
            if fact.valid_until <= now:
                continue
            if fact.valid_from is not None and fact.valid_from > now:
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
                    json.dumps(entry.payload, sort_keys=True, default=str),
                    entry.source_hash,
                    entry.source_url,
                    entry.scope,
                    entry.valid_from.isoformat() if entry.valid_from is not None else None,
                    entry.valid_until.isoformat() if entry.valid_until is not None else None,
                    entry.policy_version,
                    entry.created_at.isoformat(),
                    entry.revoked_at.isoformat() if entry.revoked_at is not None else None,
                ),
            )
            await connection.commit()
