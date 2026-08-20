from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite
from pydantic import BaseModel, Field

from asx_investigator.domain.models import CheckpointSummary, EvidenceItem, EvidenceRole
from asx_investigator.investigation.checkpoints import (
    CHECKPOINT_SCHEMA_VERSION,
    CheckpointEnvelope,
)


class CaseVersionImmutableError(RuntimeError):
    """Raised when code attempts to rewrite a terminal case version."""


class CaseVersionRecord(BaseModel):
    case_id: str
    version_id: str
    version_number: int
    parent_version_id: str | None = None
    ticker: str
    trade_date: date
    mode: str
    status: str
    outcome: str | None = None
    active_stage: str | None = None
    request_payload: dict[str, object] = Field(default_factory=dict)
    report_payload: dict[str, object] | None = None
    request_schema_version: str = "phase2-v1"
    report_schema_version: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class RunEvent(BaseModel):
    version_id: str
    sequence: int
    event_type: str
    stage: str
    status: str
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    current_version_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_versions (
    version_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    version_number INTEGER NOT NULL,
    parent_version_id TEXT REFERENCES case_versions(version_id),
    status TEXT NOT NULL,
    outcome TEXT,
    active_stage TEXT,
    request_json TEXT NOT NULL,
    report_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(case_id, version_number)
);
CREATE TABLE IF NOT EXISTS run_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id TEXT NOT NULL REFERENCES case_versions(version_id),
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(version_id, sequence)
);
CREATE TABLE IF NOT EXISTS provider_calls (
    provider_call_id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id TEXT NOT NULL REFERENCES case_versions(version_id),
    provider TEXT NOT NULL,
    operation TEXT NOT NULL,
    status TEXT NOT NULL,
    coverage TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    error_code TEXT,
    source_version TEXT,
    artifact_id TEXT
);
CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT NOT NULL,
    version_id TEXT NOT NULL REFERENCES case_versions(version_id),
    artifact_id TEXT,
    content_hash TEXT NOT NULL,
    origin_hash TEXT NOT NULL,
    source_name TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    role TEXT NOT NULL,
    authority TEXT NOT NULL,
    title TEXT NOT NULL,
    passage TEXT NOT NULL,
    locator TEXT,
    page INTEGER,
    PRIMARY KEY(version_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS source_documents (
    source_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    authority TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_passages (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_documents(source_id),
    passage TEXT NOT NULL,
    locator TEXT NOT NULL,
    page INTEGER,
    passage_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
    version_id TEXT NOT NULL REFERENCES case_versions(version_id),
    stage TEXT NOT NULL,
    input_artifact_hashes_json TEXT NOT NULL,
    output_artifact_hashes_json TEXT NOT NULL,
    typed_state_json TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(version_id, stage, created_at)
);
CREATE INDEX IF NOT EXISTS idx_case_versions_case ON case_versions(case_id, version_number);
CREATE INDEX IF NOT EXISTS idx_run_events_version ON run_events(version_id, sequence);
CREATE INDEX IF NOT EXISTS idx_provider_calls_version ON provider_calls(version_id);
CREATE INDEX IF NOT EXISTS idx_evidence_records_version ON evidence_records(version_id);
CREATE INDEX IF NOT EXISTS idx_evidence_records_hash ON evidence_records(content_hash, origin_hash);
CREATE INDEX IF NOT EXISTS idx_checkpoints_compatible
    ON checkpoints(version_id, policy_version, schema_version, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_records_version_hash
    ON evidence_records(version_id, content_hash);
"""


class SQLiteCaseRepository:
    TERMINAL_STATUSES = {"COMPLETED", "FAILED"}

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.executescript(SCHEMA)
            columns = await (
                await connection.execute("PRAGMA table_info(evidence_records)")
            ).fetchall()
            if "source_name" not in {str(row[1]) for row in columns}:
                await connection.execute(
                    "ALTER TABLE evidence_records ADD COLUMN source_name TEXT NOT NULL DEFAULT ''"
                )
            version_columns = await (
                await connection.execute("PRAGMA table_info(case_versions)")
            ).fetchall()
            existing_version_columns = {str(row[1]) for row in version_columns}
            if "request_schema_version" not in existing_version_columns:
                await connection.execute(
                    "ALTER TABLE case_versions ADD COLUMN request_schema_version TEXT"
                )
            if "report_schema_version" not in existing_version_columns:
                await connection.execute(
                    "ALTER TABLE case_versions ADD COLUMN report_schema_version TEXT"
                )
            provider_call_columns = await (
                await connection.execute("PRAGMA table_info(provider_calls)")
            ).fetchall()
            if "artifact_id" not in {str(row[1]) for row in provider_call_columns}:
                await connection.execute(
                    "ALTER TABLE provider_calls ADD COLUMN artifact_id TEXT"
                )
            await connection.commit()

    async def journal_mode(self) -> str:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            assert row is not None
            return str(row[0]).lower()

    async def create_source(
        self,
        *,
        artifact_id: str,
        source_url: str,
        mime_type: str,
        title: str,
        published_at: datetime,
        content_hash: str,
        authority: str,
        passages: list[dict[str, object]],
    ) -> dict[str, object]:
        source_id = str(uuid4())
        retrieved_at = datetime.now(UTC)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute(
                """INSERT INTO source_documents
                (source_id, artifact_id, source_url, mime_type, title, published_at,
                 retrieved_at, content_hash, authority)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id,
                    artifact_id,
                    source_url,
                    mime_type,
                    title,
                    published_at.isoformat(),
                    retrieved_at.isoformat(),
                    content_hash,
                    authority,
                ),
            )
            for index, passage in enumerate(passages, start=1):
                text = str(passage["text"])
                await connection.execute(
                    """INSERT INTO source_passages
                    (evidence_id, source_id, passage, locator, page, passage_hash)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        f"{source_id}:P{index}",
                        source_id,
                        text,
                        str(passage["locator"]),
                        passage.get("page"),
                        hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    ),
                )
            await connection.commit()
        return {
            "source_id": source_id,
            "title": title,
            "artifact_id": artifact_id,
            "content_hash": content_hash,
            "passage_count": len(passages),
            "published_at": published_at.isoformat(),
            "retrieved_at": retrieved_at.isoformat(),
        }

    async def get_source_evidence(self, source_ids: list[str]) -> list[EvidenceItem]:
        if not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        sql = f"""SELECT d.*, p.evidence_id, p.passage, p.locator, p.page, p.passage_hash
            FROM source_documents d JOIN source_passages p ON p.source_id = d.source_id
            WHERE d.source_id IN ({placeholders}) ORDER BY d.source_id, p.evidence_id"""
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (await connection.execute(sql, source_ids)).fetchall()
        found = {str(row["source_id"]) for row in rows}
        missing = set(source_ids) - found
        if missing:
            raise KeyError(sorted(missing)[0])
        return [
            EvidenceItem(
                evidence_id=str(row["evidence_id"]),
                source_name="User supplied source",
                source_url=str(row["source_url"]),
                published_at=datetime.fromisoformat(str(row["published_at"])),
                retrieved_at=datetime.fromisoformat(str(row["retrieved_at"])),
                role=EvidenceRole.CAUSAL_INPUT,
                authority=str(row["authority"]),
                title=str(row["title"]),
                passage=str(row["passage"]),
                content_hash=str(row["passage_hash"]),
                locator=str(row["locator"]),
                page=int(row["page"]) if row["page"] is not None else None,
            )
            for row in rows
        ]

    async def get_source_artifact_hashes(self, source_ids: list[str]) -> list[str]:
        if not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        async with aiosqlite.connect(self.database_path) as connection:
            rows = await (
                await connection.execute(
                    f"""SELECT source_id, artifact_id FROM source_documents
                    WHERE source_id IN ({placeholders}) ORDER BY source_id""",
                    source_ids,
                )
            ).fetchall()
        found = {str(row[0]) for row in rows}
        missing = set(source_ids) - found
        if missing:
            raise KeyError(sorted(missing)[0])
        return sorted({str(row[1]) for row in rows})

    async def find_evidence_content(
        self, evidence_id: str, *, version_id: str | None = None
    ) -> dict[str, object]:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            if version_id is not None:
                row = await (
                    await connection.execute(
                        """SELECT passage, locator, page FROM evidence_records
                        WHERE version_id = ? AND evidence_id = ?""",
                        (version_id, evidence_id),
                    )
                ).fetchone()
            else:
                row = await (
                    await connection.execute(
                        """SELECT passage, locator, page FROM source_passages
                        WHERE evidence_id = ?""",
                        (evidence_id,),
                    )
                ).fetchone()
                if row is None:
                    rows = await (
                        await connection.execute(
                            """SELECT passage, locator, page FROM evidence_records
                            WHERE evidence_id = ? ORDER BY version_id""",
                            (evidence_id,),
                        )
                    ).fetchall()
                    if len(rows) > 1:
                        raise ValueError(
                            "Evidence ID is version-scoped; provide version_id"
                        )
                    row = rows[0] if rows else None
        if row is None:
            raise KeyError(evidence_id)
        return {
            "evidence_id": evidence_id,
            "version_id": version_id,
            "passage": str(row["passage"]),
            "locator": str(row["locator"]) if row["locator"] is not None else None,
            "page": int(row["page"]) if row["page"] is not None else None,
        }

    async def record_provider_call(
        self,
        version_id: str,
        *,
        provider: str,
        operation: str,
        status: str,
        coverage: str,
        retrieved_at: datetime,
        provenance: dict[str, str],
        error_code: str | None = None,
        source_version: str | None = None,
        artifact_id: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute(
                """INSERT INTO provider_calls
                (version_id, provider, operation, status, coverage, retrieved_at,
                 provenance_json, error_code, source_version, artifact_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    provider,
                    operation,
                    status,
                    coverage,
                    retrieved_at.isoformat(),
                    json.dumps(provenance, sort_keys=True),
                    error_code,
                    source_version,
                    artifact_id,
                ),
            )
            await connection.commit()

    async def list_provider_calls(self, version_id: str) -> list[dict[str, object]]:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (
                await connection.execute(
                    """SELECT * FROM provider_calls WHERE version_id = ?
                    ORDER BY provider_call_id""",
                    (version_id,),
                )
            ).fetchall()
        return [
            {
                "provider": str(row["provider"]),
                "operation": str(row["operation"]),
                "status": str(row["status"]),
                "coverage": str(row["coverage"]),
                "retrieved_at": str(row["retrieved_at"]),
                "provenance": json.loads(str(row["provenance_json"])),
                "error_code": row["error_code"],
                "source_version": row["source_version"],
                "artifact_id": row["artifact_id"],
            }
            for row in rows
        ]

    async def create_case(
        self,
        *,
        ticker: str,
        trade_date: date,
        mode: str,
        request_payload: dict[str, object],
    ) -> CaseVersionRecord:
        case_id = str(uuid4())
        version_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute(
                "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?)",
                (case_id, ticker, trade_date.isoformat(), mode, version_id, now, now),
            )
            await connection.execute(
                """INSERT INTO case_versions
                (version_id, case_id, version_number, parent_version_id, status, outcome,
                 active_stage, request_json, report_json, error, created_at, updated_at)
                VALUES (?, ?, 1, NULL, 'QUEUED', NULL, NULL, ?, NULL, NULL, ?, ?)""",
                (
                    version_id,
                    case_id,
                    self._serialize_case_payload(request_payload),
                    now,
                    now,
                ),
            )
            await connection.execute(
                "UPDATE case_versions SET request_schema_version = ? WHERE version_id = ?",
                ("case-payload-v1", version_id),
            )
            await connection.commit()
        return await self.get_version(version_id)

    async def create_version(
        self,
        case_id: str,
        *,
        parent_version_id: str,
        request_payload: dict[str, object],
    ) -> CaseVersionRecord:
        version_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute("BEGIN IMMEDIATE")
            try:
                parent_row = await (
                    await connection.execute(
                        """SELECT v.case_id, v.status, c.current_version_id
                        FROM case_versions v JOIN cases c ON c.case_id = v.case_id
                        WHERE v.version_id = ?""",
                        (parent_version_id,),
                    )
                ).fetchone()
                if parent_row is None or str(parent_row[0]) != case_id:
                    raise KeyError(parent_version_id)
                if str(parent_row[2]) != parent_version_id:
                    raise ValueError("Only the current case version can be refined")
                if str(parent_row[1]) not in self.TERMINAL_STATUSES:
                    await connection.execute(
                        """UPDATE case_versions SET status = 'FAILED',
                        error = 'SUPERSEDED_BY_REFINEMENT', updated_at = ?
                        WHERE version_id = ?""",
                        (now, parent_version_id),
                    )
                row = await (
                    await connection.execute(
                        """SELECT COALESCE(MAX(version_number), 0) + 1
                        FROM case_versions WHERE case_id = ?""",
                        (case_id,),
                    )
                ).fetchone()
                assert row is not None
                version_number = int(row[0])
                await connection.execute(
                    """INSERT INTO case_versions
                    (version_id, case_id, version_number, parent_version_id, status, outcome,
                     active_stage, request_json, report_json, error, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'QUEUED', NULL, NULL, ?, NULL, NULL, ?, ?)""",
                    (
                        version_id,
                        case_id,
                        version_number,
                        parent_version_id,
                        self._serialize_case_payload(request_payload),
                        now,
                        now,
                    ),
                )
                await connection.execute(
                    "UPDATE case_versions SET request_schema_version = ? WHERE version_id = ?",
                    ("case-payload-v1", version_id),
                )
                await connection.execute(
                    "UPDATE cases SET current_version_id = ?, updated_at = ? WHERE case_id = ?",
                    (version_id, now, case_id),
                )
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise
        return await self.get_version(version_id)

    async def create_checkpoint_recovery_child(
        self,
        parent_version_id: str,
        *,
        request_payload: dict[str, object],
        reason: str,
    ) -> CaseVersionRecord:
        """Atomically retire an incompatible current version and queue its child."""

        version_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute("BEGIN IMMEDIATE")
            try:
                parent_row = await (
                    await connection.execute(
                        """SELECT v.case_id, v.status, v.active_stage, c.current_version_id
                        FROM case_versions v JOIN cases c ON c.case_id = v.case_id
                        WHERE v.version_id = ?""",
                        (parent_version_id,),
                    )
                ).fetchone()
                if parent_row is None:
                    raise KeyError(parent_version_id)
                case_id = str(parent_row[0])
                if str(parent_row[3]) != parent_version_id:
                    raise ValueError("Only the current case version can create a recovery child")
                if str(parent_row[1]) not in {
                    "QUEUED",
                    "RUNNING",
                    "FAILED_RECOVERABLE",
                }:
                    raise CaseVersionImmutableError(parent_version_id)
                version_row = await (
                    await connection.execute(
                        """SELECT COALESCE(MAX(version_number), 0) + 1
                        FROM case_versions WHERE case_id = ?""",
                        (case_id,),
                    )
                ).fetchone()
                assert version_row is not None
                version_number = int(version_row[0])
                await connection.execute(
                    """UPDATE case_versions SET status = 'FAILED', error = ?, updated_at = ?
                    WHERE version_id = ?""",
                    (
                        f"CHECKPOINT_INCOMPATIBLE: {reason}",
                        now,
                        parent_version_id,
                    ),
                )
                await connection.execute(
                    """INSERT INTO case_versions
                    (version_id, case_id, version_number, parent_version_id, status, outcome,
                     active_stage, request_json, report_json, error, created_at, updated_at,
                     request_schema_version)
                    VALUES (?, ?, ?, ?, 'QUEUED', NULL, NULL, ?, NULL, NULL, ?, ?, ?)""",
                    (
                        version_id,
                        case_id,
                        version_number,
                        parent_version_id,
                        self._serialize_case_payload(request_payload),
                        now,
                        now,
                        "case-payload-v1",
                    ),
                )
                await connection.execute(
                    "UPDATE cases SET current_version_id = ?, updated_at = ? WHERE case_id = ?",
                    (version_id, now, case_id),
                )
                sequence_row = await (
                    await connection.execute(
                        """SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events
                        WHERE version_id = ?""",
                        (parent_version_id,),
                    )
                ).fetchone()
                assert sequence_row is not None
                await connection.execute(
                    """INSERT INTO run_events
                    (version_id, sequence, event_type, stage, status, payload_json, created_at)
                    VALUES (?, ?, 'recovery', ?, 'CHECKPOINT_INCOMPATIBLE', ?, ?)""",
                    (
                        parent_version_id,
                        int(sequence_row[0]),
                        str(parent_row[2] or "recovery"),
                        json.dumps({"reason": reason}),
                        now,
                    ),
                )
                await connection.execute(
                    """INSERT INTO run_events
                    (version_id, sequence, event_type, stage, status, payload_json, created_at)
                    VALUES (?, 1, 'recovery', 'resolve_instrument',
                    'CHECKPOINT_INCOMPATIBLE', ?, ?)""",
                    (
                        version_id,
                        json.dumps(
                            {
                                "parent_version_id": parent_version_id,
                                "reason": reason,
                            }
                        ),
                        now,
                    ),
                )
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise
        return await self.get_version(version_id)

    async def queue_current_checkpoint_resume(
        self,
        version_id: str,
        stage: str,
        *,
        allowed_statuses: tuple[str, ...] = ("FAILED_RECOVERABLE",),
    ) -> CaseVersionRecord:
        """Atomically queue a resumable checkpoint only for the current case version."""

        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute("BEGIN IMMEDIATE")
            try:
                row = await (
                    await connection.execute(
                        """SELECT v.status, c.current_version_id
                        FROM case_versions v JOIN cases c ON c.case_id = v.case_id
                        WHERE v.version_id = ?""",
                        (version_id,),
                    )
                ).fetchone()
                if row is None:
                    raise KeyError(version_id)
                if str(row[1]) != version_id:
                    raise ValueError("Only the current case version can be resumed")
                if str(row[0]) not in allowed_statuses:
                    raise ValueError("Case version cannot be resumed from its current status")
                await connection.execute(
                    """UPDATE case_versions SET status = 'QUEUED', active_stage = ?,
                    error = NULL, updated_at = ? WHERE version_id = ?""",
                    (stage, now, version_id),
                )
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise
        return await self.get_version(version_id)

    async def get_version(self, version_id: str) -> CaseVersionRecord:
        query = """SELECT v.version_id, v.case_id, v.version_number, v.parent_version_id,
                   c.ticker, c.trade_date, c.mode, v.status, v.outcome, v.active_stage,
                   v.request_json, v.report_json, v.error, v.created_at, v.updated_at
                   FROM case_versions v JOIN cases c ON c.case_id = v.case_id
                   WHERE v.version_id = ?"""
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(query, (version_id,))
            row = await cursor.fetchone()
        if row is None:
            raise KeyError(version_id)
        return self._version_from_row(row)

    async def get_case(self, case_id: str) -> CaseVersionRecord:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                "SELECT current_version_id FROM cases WHERE case_id = ?", (case_id,)
            )
            row = await cursor.fetchone()
        if row is None:
            raise KeyError(case_id)
        return await self.get_version(str(row[0]))

    async def list_versions(self, case_id: str) -> list[CaseVersionRecord]:
        async with aiosqlite.connect(self.database_path) as connection:
            rows = await (
                await connection.execute(
                    """SELECT version_id FROM case_versions WHERE case_id = ?
                    ORDER BY version_number DESC""",
                    (case_id,),
                )
            ).fetchall()
        if not rows:
            raise KeyError(case_id)
        return [await self.get_version(str(row[0])) for row in rows]

    async def list_cases(self) -> list[CaseVersionRecord]:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                "SELECT current_version_id FROM cases ORDER BY updated_at DESC"
            )
            rows = await cursor.fetchall()
        return [await self.get_version(str(row[0])) for row in rows]

    async def update_status(
        self,
        version_id: str,
        status: str,
        *,
        active_stage: str | None = None,
        error: str | None = None,
    ) -> CaseVersionRecord:
        existing = await self.get_version(version_id)
        if existing.status in self.TERMINAL_STATUSES:
            raise CaseVersionImmutableError(version_id)
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                """UPDATE case_versions SET status = ?, active_stage = ?, error = ?, updated_at = ?
                WHERE version_id = ?""",
                (status, active_stage, error, now, version_id),
            )
            await connection.commit()
        return await self.get_version(version_id)

    async def complete_version(
        self,
        version_id: str,
        *,
        report_payload: dict[str, object],
        outcome: str,
    ) -> CaseVersionRecord:
        existing = await self.get_version(version_id)
        if existing.status in self.TERMINAL_STATUSES:
            raise CaseVersionImmutableError(version_id)
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                """UPDATE case_versions SET status = 'COMPLETED', outcome = ?,
                active_stage = NULL, report_json = ?, updated_at = ? WHERE version_id = ?""",
                (
                    outcome,
                    self._serialize_case_payload(report_payload),
                    now,
                    version_id,
                ),
            )
            await connection.execute(
                "UPDATE case_versions SET report_schema_version = ? WHERE version_id = ?",
                ("case-payload-v1", version_id),
            )
            await connection.commit()
        return await self.get_version(version_id)

    async def append_event(
        self,
        version_id: str,
        event_type: str,
        stage: str,
        status: str,
        payload: dict[str, object] | None = None,
    ) -> RunEvent:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE version_id = ?",
                (version_id,),
            )
            row = await cursor.fetchone()
            assert row is not None
            sequence = int(row[0])
            await connection.execute(
                """INSERT INTO run_events
                (version_id, sequence, event_type, stage, status, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    sequence,
                    event_type,
                    stage,
                    status,
                    json.dumps(payload or {}),
                    now,
                ),
            )
            await connection.commit()
        return RunEvent(
            version_id=version_id,
            sequence=sequence,
            event_type=event_type,
            stage=stage,
            status=status,
            payload=payload or {},
            created_at=datetime.fromisoformat(now),
        )

    async def list_events(self, version_id: str, after_sequence: int = 0) -> list[RunEvent]:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """SELECT version_id, sequence, event_type, stage, status, payload_json, created_at
                FROM run_events WHERE version_id = ? AND sequence > ? ORDER BY sequence""",
                (version_id, after_sequence),
            )
            rows = await cursor.fetchall()
        return [
            RunEvent(
                version_id=row[0],
                sequence=row[1],
                event_type=row[2],
                stage=row[3],
                status=row[4],
                payload=json.loads(row[5]),
                created_at=datetime.fromisoformat(row[6]),
            )
            for row in rows
        ]

    async def list_recoverable_versions(self) -> list[CaseVersionRecord]:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """SELECT v.version_id FROM case_versions v
                JOIN cases c ON c.current_version_id = v.version_id
                WHERE v.status IN ('QUEUED', 'RUNNING', 'FAILED_RECOVERABLE')
                ORDER BY v.created_at"""
            )
            rows = await cursor.fetchall()
        return [await self.get_version(row[0]) for row in rows]

    async def save_checkpoint(self, checkpoint: CheckpointEnvelope) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT status FROM case_versions WHERE version_id = ?",
                (checkpoint.version_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise KeyError(checkpoint.version_id)
            if str(row[0]) in self.TERMINAL_STATUSES:
                raise CaseVersionImmutableError(checkpoint.version_id)
            await connection.execute(
                """INSERT INTO checkpoints
                (version_id, stage, input_artifact_hashes_json, output_artifact_hashes_json,
                 typed_state_json, schema_version, policy_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint.version_id,
                    checkpoint.stage,
                    json.dumps(checkpoint.input_artifact_hashes, sort_keys=True),
                    json.dumps(checkpoint.output_artifact_hashes, sort_keys=True),
                    json.dumps(checkpoint.typed_state_json, sort_keys=True),
                    checkpoint.schema_version,
                    checkpoint.policy_version,
                    checkpoint.created_at.isoformat(),
                ),
            )
            await connection.commit()

    async def latest_compatible_checkpoint(
        self,
        version_id: str,
        *,
        policy_version: str,
        input_artifact_hashes: list[str],
        schema_version: str = CHECKPOINT_SCHEMA_VERSION,
    ) -> CheckpointEnvelope | None:
        normalized_inputs = sorted(input_artifact_hashes)
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """SELECT version_id, stage, input_artifact_hashes_json,
                output_artifact_hashes_json, typed_state_json, schema_version,
                policy_version, created_at FROM checkpoints
                WHERE version_id = ? AND policy_version = ? AND schema_version = ?
                ORDER BY created_at DESC""",
                (version_id, policy_version, schema_version),
            )
            rows = await cursor.fetchall()
        for row in rows:
            if sorted(json.loads(str(row[2]))) != normalized_inputs:
                continue
            return CheckpointEnvelope(
                version_id=str(row[0]),
                stage=str(row[1]),
                input_artifact_hashes=json.loads(str(row[2])),
                output_artifact_hashes=json.loads(str(row[3])),
                typed_state_json=json.loads(str(row[4])),
                schema_version=str(row[5]),
                policy_version=str(row[6]),
                created_at=datetime.fromisoformat(str(row[7])),
            )
        return None

    async def latest_checkpoint(self, version_id: str) -> CheckpointEnvelope | None:
        async with aiosqlite.connect(self.database_path) as connection:
            row = await (
                await connection.execute(
                    """SELECT version_id, stage, input_artifact_hashes_json,
                    output_artifact_hashes_json, typed_state_json, schema_version,
                    policy_version, created_at FROM checkpoints
                    WHERE version_id = ? ORDER BY created_at DESC LIMIT 1""",
                    (version_id,),
                )
            ).fetchone()
        if row is None:
            return None
        return CheckpointEnvelope(
            version_id=str(row[0]),
            stage=str(row[1]),
            input_artifact_hashes=json.loads(str(row[2])),
            output_artifact_hashes=json.loads(str(row[3])),
            typed_state_json=json.loads(str(row[4])),
            schema_version=str(row[5]),
            policy_version=str(row[6]),
            created_at=datetime.fromisoformat(str(row[7])),
        )

    async def list_checkpoint_summaries(self, version_id: str) -> list[CheckpointSummary]:
        async with aiosqlite.connect(self.database_path) as connection:
            rows = await (
                await connection.execute(
                    """SELECT stage, input_artifact_hashes_json, output_artifact_hashes_json,
                    schema_version, policy_version, created_at FROM checkpoints
                    WHERE version_id = ? ORDER BY created_at, rowid""",
                    (version_id,),
                )
            ).fetchall()
        return [
            CheckpointSummary(
                stage=str(row[0]),
                input_artifact_hashes=json.loads(str(row[1])),
                output_artifact_hashes=json.loads(str(row[2])),
                schema_version=str(row[3]),
                policy_version=str(row[4]),
                created_at=datetime.fromisoformat(str(row[5])),
            )
            for row in rows
        ]

    @staticmethod
    def _serialize_case_payload(payload: dict[str, object]) -> str:
        return json.dumps(
            {"schema_version": "case-payload-v1", "payload": payload}, sort_keys=True
        )

    @staticmethod
    def _deserialize_case_payload(raw_payload: object) -> tuple[dict[str, object], str]:
        parsed = json.loads(str(raw_payload))
        if (
            isinstance(parsed, dict)
            and isinstance(parsed.get("schema_version"), str)
            and isinstance(parsed.get("payload"), dict)
        ):
            return parsed["payload"], parsed["schema_version"]
        if not isinstance(parsed, dict):
            raise ValueError("Case payload must be a JSON object")
        return parsed, "phase2-v1"

    @staticmethod
    def _version_from_row(row: tuple[object, ...]) -> CaseVersionRecord:
        request_payload, request_schema_version = SQLiteCaseRepository._deserialize_case_payload(
            row[10]
        )
        report_payload = None
        report_schema_version = None
        if row[11] is not None:
            report_payload, report_schema_version = SQLiteCaseRepository._deserialize_case_payload(
                row[11]
            )
        return CaseVersionRecord(
            version_id=str(row[0]),
            case_id=str(row[1]),
            version_number=int(row[2]),
            parent_version_id=None if row[3] is None else str(row[3]),
            ticker=str(row[4]),
            trade_date=date.fromisoformat(str(row[5])),
            mode=str(row[6]),
            status=str(row[7]),
            outcome=None if row[8] is None else str(row[8]),
            active_stage=None if row[9] is None else str(row[9]),
            request_payload=request_payload,
            report_payload=report_payload,
            request_schema_version=request_schema_version,
            report_schema_version=report_schema_version,
            error=None if row[12] is None else str(row[12]),
            created_at=datetime.fromisoformat(str(row[13])),
            updated_at=datetime.fromisoformat(str(row[14])),
        )
