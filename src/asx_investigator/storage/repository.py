from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite
from pydantic import BaseModel, Field


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
CREATE INDEX IF NOT EXISTS idx_case_versions_case ON case_versions(case_id, version_number);
CREATE INDEX IF NOT EXISTS idx_run_events_version ON run_events(version_id, sequence);
CREATE INDEX IF NOT EXISTS idx_provider_calls_version ON provider_calls(version_id);
CREATE INDEX IF NOT EXISTS idx_evidence_records_version ON evidence_records(version_id);
CREATE INDEX IF NOT EXISTS idx_evidence_records_hash ON evidence_records(content_hash, origin_hash);
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
            await connection.commit()

    async def journal_mode(self) -> str:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            assert row is not None
            return str(row[0]).lower()

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
                (version_id, case_id, json.dumps(request_payload), now, now),
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
        parent = await self.get_version(parent_version_id)
        if parent.case_id != case_id:
            raise KeyError(parent_version_id)
        version_id = str(uuid4())
        version_number = parent.version_number + 1
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
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
                    json.dumps(request_payload),
                    now,
                    now,
                ),
            )
            await connection.execute(
                "UPDATE cases SET current_version_id = ?, updated_at = ? WHERE case_id = ?",
                (version_id, now, case_id),
            )
            await connection.commit()
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
                (outcome, json.dumps(report_payload), now, version_id),
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
                """SELECT version_id FROM case_versions
                WHERE status IN ('QUEUED', 'RUNNING', 'FAILED_RECOVERABLE')
                ORDER BY created_at"""
            )
            rows = await cursor.fetchall()
        return [await self.get_version(row[0]) for row in rows]

    @staticmethod
    def _version_from_row(row: tuple[object, ...]) -> CaseVersionRecord:
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
            request_payload=json.loads(str(row[10])),
            report_payload=None if row[11] is None else json.loads(str(row[11])),
            error=None if row[12] is None else str(row[12]),
            created_at=datetime.fromisoformat(str(row[13])),
            updated_at=datetime.fromisoformat(str(row[14])),
        )
