from __future__ import annotations

import asyncio
import json
import re
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from asx_investigator.agent.gemini import GeminiInvestigationReasoner
from asx_investigator.domain.models import (
    InvestigationReport,
    InvestigationStatus,
    TraceReference,
)
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.live import LiveToolGateway
from asx_investigator.report.markdown import render_markdown
from asx_investigator.settings import Settings
from asx_investigator.storage.repository import CaseVersionRecord, SQLiteCaseRepository


class InvestigationRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    trade_date: date
    mode: str = "LIVE"
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        value = value.upper().strip()
        if not re.fullmatch(r"[A-Z]{2,6}", value):
            raise ValueError("ticker must be a 2–6 character ASX code")
        return value

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        value = value.upper().strip()
        if value not in {"LIVE", "RECORDED"}:
            raise ValueError("mode must be LIVE or RECORDED")
        return value


class RefinementRequest(BaseModel):
    primary_only: bool = False
    excluded_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class CaseAccepted(BaseModel):
    case_id: str
    version_id: str
    version_number: int
    parent_version_id: str | None = None
    status: str = "QUEUED"


class CaseManager:
    """Durable case runner with append-only public events."""

    def __init__(self, service: InvestigationService, repository: SQLiteCaseRepository) -> None:
        self.service = service
        self.repository = repository
        self.tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        await self.repository.initialize()
        for record in await self.repository.list_recoverable_versions():
            request = InvestigationRequest.model_validate(record.request_payload)
            self._launch(record, request)

    async def stop(self) -> None:
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    async def create(self, request: InvestigationRequest) -> CaseVersionRecord:
        record = await self.repository.create_case(
            ticker=request.ticker,
            trade_date=request.trade_date,
            mode=request.mode,
            request_payload=request.model_dump(mode="json"),
        )
        await self.repository.append_event(record.version_id, "status", "queued", "QUEUED")
        record = await self.repository.update_status(
            record.version_id, "RUNNING", active_stage="resolve_instrument"
        )
        await self.repository.append_event(
            record.version_id, "status", "resolve_instrument", "RUNNING"
        )
        self._launch(record, request)
        return record

    async def create_version(
        self, case_id: str, refinement: RefinementRequest
    ) -> CaseVersionRecord:
        parent = await self.repository.get_case(case_id)
        payload = dict(parent.request_payload)
        payload.update(refinement.model_dump(mode="json"))
        request = InvestigationRequest.model_validate(payload)
        child = await self.repository.create_version(
            case_id,
            parent_version_id=parent.version_id,
            request_payload=payload,
        )
        await self.repository.append_event(
            child.version_id,
            "status",
            "queued",
            "QUEUED",
            {"parent_version_id": parent.version_id},
        )
        child = await self.repository.update_status(
            child.version_id, "RUNNING", active_stage="resolve_instrument"
        )
        await self.repository.append_event(
            child.version_id, "status", "resolve_instrument", "RUNNING"
        )
        self._launch(child, request)
        return child

    async def retry(self, case_id: str) -> CaseVersionRecord:
        record = await self.repository.get_case(case_id)
        if record.status != "FAILED_RECOVERABLE":
            raise ValueError("Only FAILED_RECOVERABLE cases can be retried")
        record = await self.repository.update_status(
            record.version_id, "QUEUED", active_stage=record.active_stage
        )
        request = InvestigationRequest.model_validate(record.request_payload)
        await self.repository.append_event(
            record.version_id, "status", record.active_stage or "retry", "QUEUED"
        )
        self._launch(record, request)
        return record

    def _launch(self, record: CaseVersionRecord, request: InvestigationRequest) -> None:
        task = asyncio.create_task(
            self._run(record, request), name=f"investigation-{record.version_id}"
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, record: CaseVersionRecord, request: InvestigationRequest) -> None:
        stage = record.active_stage or "resolve_instrument"
        try:
            if record.status != "RUNNING":
                await self.repository.update_status(
                    record.version_id, "RUNNING", active_stage=stage
                )
                await self.repository.append_event(
                    record.version_id, "status", stage, "RUNNING"
                )

            async def persist_stage(
                current_stage: str,
                stage_status: str,
                payload: dict[str, object],
            ) -> None:
                nonlocal stage
                stage = current_stage
                await self.repository.update_status(
                    record.version_id, "RUNNING", active_stage=current_stage
                )
                await self.repository.append_event(
                    record.version_id,
                    "stage",
                    current_stage,
                    stage_status,
                    payload,
                )

            report = await self.service.investigate(
                request.ticker,
                request.trade_date,
                mode=request.mode,
                on_stage=persist_stage,
            )
            report.case_id = record.case_id
            report.run_id = record.version_id
            report.status = InvestigationStatus.COMPLETED
            report.parent_case_id = record.parent_version_id
            report.case_version = record.version_number
            await self.repository.update_status(
                record.version_id, "RUNNING", active_stage="persist_and_publish"
            )
            await self.repository.append_event(
                record.version_id, "stage", "persist_and_publish", "RUNNING"
            )
            persisted_events = await self.repository.list_events(record.version_id)
            report.trace_reference = TraceReference(
                event_count=len(persisted_events),
                last_sequence=persisted_events[-1].sequence,
            )
            completed = await self.repository.complete_version(
                record.version_id,
                report_payload=report.model_dump(mode="json"),
                outcome=str(report.outcome),
            )
            await self.repository.append_event(
                record.version_id,
                "completed",
                "publish",
                completed.status,
                {"outcome": completed.outcome or "INSUFFICIENT_EVIDENCE"},
            )
        except Exception:
            await self.repository.update_status(
                record.version_id,
                "FAILED_RECOVERABLE",
                active_stage=stage,
                error="The investigation could not complete. Retry from the recorded stage.",
            )
            await self.repository.append_event(
                record.version_id, "failed", stage, "FAILED_RECOVERABLE"
            )

    async def events(
        self, case_id: str, after_sequence: int = 0
    ) -> AsyncIterator[dict[str, object]]:
        record = await self.repository.get_case(case_id)
        sequence = after_sequence
        while True:
            events = await self.repository.list_events(record.version_id, sequence)
            for event in events:
                sequence = event.sequence
                yield event.model_dump(mode="json")
            record = await self.repository.get_version(record.version_id)
            if record.status in {"COMPLETED", "FAILED", "FAILED_RECOVERABLE"} and not events:
                break
            await asyncio.sleep(0.05)


def _database_path(settings: Settings) -> Path:
    prefix = "sqlite+aiosqlite:///"
    if settings.database_url.startswith(prefix):
        return Path(settings.database_url.removeprefix(prefix))
    raise ValueError("Phase 2 supports sqlite+aiosqlite database URLs")


def create_app(
    service: InvestigationService | None = None,
    *,
    repository: SQLiteCaseRepository | None = None,
) -> FastAPI:
    settings = Settings()
    injected_service = service is not None
    if service is None:
        service = InvestigationService(
            LiveToolGateway(settings), reasoner=GeminiInvestigationReasoner(settings)
        )
    if repository is None:
        path = (
            Path(tempfile.mkdtemp(prefix="asx-investigator-test-")) / "cases.db"
            if injected_service
            else _database_path(settings)
        )
        repository = SQLiteCaseRepository(path)
    manager = CaseManager(service, repository)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await manager.start()
        yield
        await manager.stop()

    app = FastAPI(title="ASX Investigation Agent", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    app.state.case_manager = manager

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/v1/investigations",
        response_model=CaseAccepted,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_investigation(request: InvestigationRequest) -> CaseAccepted:
        record = await manager.create(request)
        return CaseAccepted(**record.model_dump())

    @app.get("/api/v1/investigations")
    async def list_investigations() -> dict[str, object]:
        records = await repository.list_cases()
        return {"items": [record.model_dump(mode="json") for record in records]}

    @app.post(
        "/api/v1/investigations/{case_id}/versions",
        response_model=CaseAccepted,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_version(case_id: str, request: RefinementRequest) -> CaseAccepted:
        try:
            record = await manager.create_version(case_id, request)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error
        return CaseAccepted(**record.model_dump())

    @app.post(
        "/api/v1/investigations/{case_id}/retry",
        response_model=CaseAccepted,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def retry_investigation(case_id: str) -> CaseAccepted:
        try:
            record = await manager.retry(case_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return CaseAccepted(**record.model_dump())

    @app.get("/api/v1/investigations/{case_id}", response_model=None)
    async def get_investigation(
        case_id: str, format: Literal["json", "markdown"] = "json"
    ) -> dict[str, object] | Response:
        try:
            record = await repository.get_case(case_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error
        if record.report_payload is not None:
            report = InvestigationReport.model_validate(record.report_payload)
            if format == "markdown":
                return Response(render_markdown(report), media_type="text/markdown")
            return report.model_dump(mode="json")
        return {
            "case_id": record.case_id,
            "version_id": record.version_id,
            "version_number": record.version_number,
            "status": record.status,
            "active_stage": record.active_stage,
            "error": record.error,
        }

    @app.get("/api/v1/investigations/{case_id}/events")
    async def stream_events(case_id: str, after_sequence: int = 0) -> StreamingResponse:
        try:
            await repository.get_case(case_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error

        async def encode_events() -> AsyncIterator[str]:
            async for event in manager.events(case_id, after_sequence):
                yield (
                    f"id: {event['sequence']}\n"
                    f"event: {event['event_type']}\n"
                    f"data: {json.dumps(event)}\n\n"
                )

        return StreamingResponse(encode_events(), media_type="text/event-stream")

    return app


app = create_app()
