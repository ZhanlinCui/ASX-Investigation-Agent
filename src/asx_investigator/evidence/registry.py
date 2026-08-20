from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

import aiosqlite

from asx_investigator.domain.models import EvidenceItem, EvidenceRole

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
    version_id UNINDEXED,
    evidence_id UNINDEXED,
    title,
    passage,
    tokenize = 'porter unicode61'
);
"""


class SQLiteEvidenceRegistry:
    """Version-scoped exact passages with deterministic FTS5 retrieval."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.executescript(FTS_SCHEMA)
            await connection.commit()

    async def register(
        self,
        version_id: str,
        evidence: EvidenceItem,
        *,
        artifact_id: str | None = None,
    ) -> bool:
        origin_hash = hashlib.sha256(evidence.source_url.encode("utf-8")).hexdigest()
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute("BEGIN IMMEDIATE")
            duplicate = await (
                await connection.execute(
                    """SELECT evidence_id FROM evidence_records
                    WHERE version_id = ? AND content_hash = ? LIMIT 1""",
                    (version_id, evidence.content_hash),
                )
            ).fetchone()
            if duplicate:
                await connection.rollback()
                return str(duplicate[0]) == evidence.evidence_id
            await connection.execute(
                """INSERT INTO evidence_records
                (evidence_id, version_id, artifact_id, content_hash, origin_hash,
                 source_name, source_url, published_at, retrieved_at, role, authority,
                 title, passage, locator, page)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    evidence.evidence_id,
                    version_id,
                    artifact_id,
                    evidence.content_hash,
                    origin_hash,
                    evidence.source_name,
                    evidence.source_url,
                    evidence.published_at.isoformat(),
                    evidence.retrieved_at.isoformat(),
                    str(evidence.role),
                    evidence.authority,
                    evidence.title,
                    evidence.passage,
                    evidence.locator,
                    evidence.page,
                ),
            )
            await connection.execute(
                """INSERT INTO evidence_fts
                (version_id, evidence_id, title, passage) VALUES (?, ?, ?, ?)""",
                (version_id, evidence.evidence_id, evidence.title, evidence.passage),
            )
            await connection.commit()
        return True

    async def get(self, version_id: str, evidence_id: str) -> EvidenceItem:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            row = await (
                await connection.execute(
                    """SELECT * FROM evidence_records
                    WHERE version_id = ? AND evidence_id = ?""",
                    (version_id, evidence_id),
                )
            ).fetchone()
        if row is None:
            raise KeyError(evidence_id)
        return self._restore(row)

    async def search(
        self,
        version_id: str,
        query: str,
        *,
        limit: int = 12,
        role: EvidenceRole | None = None,
        authority: str | None = None,
        published_before: datetime | None = None,
    ) -> list[EvidenceItem]:
        match_query = self._safe_match_query(query)
        predicates = ["f.version_id = ?", "e.version_id = ?"]
        parameters: list[object] = [match_query, version_id, version_id]
        if role is not None:
            predicates.append("e.role = ?")
            parameters.append(str(role))
        if authority is not None:
            predicates.append("e.authority = ?")
            parameters.append(authority)
        if published_before is not None:
            predicates.append("e.published_at <= ?")
            parameters.append(published_before.isoformat())
        parameters.append(max(1, min(limit, 50)))
        sql = f"""SELECT e.*, bm25(evidence_fts) AS rank
            FROM evidence_fts AS f
            JOIN evidence_records AS e ON e.version_id = f.version_id
                AND e.evidence_id = f.evidence_id
            WHERE evidence_fts MATCH ? AND {' AND '.join(predicates)}
            ORDER BY rank, e.published_at, e.evidence_id
            LIMIT ?"""
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (await connection.execute(sql, parameters)).fetchall()
        return [self._restore(row) for row in rows]

    @staticmethod
    def _safe_match_query(query: str) -> str:
        tokens = re.findall(r"[\w-]+", query, flags=re.UNICODE)
        if not tokens:
            raise ValueError("Evidence search requires at least one searchable token")
        return " AND ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:20])

    @staticmethod
    def _restore(row: aiosqlite.Row) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=str(row["evidence_id"]),
            source_name=str(row["source_name"]),
            source_url=str(row["source_url"]),
            published_at=datetime.fromisoformat(str(row["published_at"])),
            retrieved_at=datetime.fromisoformat(str(row["retrieved_at"])),
            role=EvidenceRole(str(row["role"])),
            authority=str(row["authority"]),
            title=str(row["title"]),
            passage=str(row["passage"]),
            content_hash=str(row["content_hash"]),
            page=int(row["page"]) if row["page"] is not None else None,
            locator=str(row["locator"]) if row["locator"] is not None else None,
        )
