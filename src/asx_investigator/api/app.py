from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from asx_investigator.agent.gemini import GeminiNarrativeGenerator
from asx_investigator.domain.models import InvestigationReport
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.live import LiveToolGateway
from asx_investigator.report.markdown import render_markdown
from asx_investigator.settings import Settings


class InvestigationRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    trade_date: date
    mode: str = "LIVE"

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


class CaseAccepted(BaseModel):
    case_id: str
    status: str = "QUEUED"


@dataclass
class CaseState:
    case_id: str
    status: str = "QUEUED"
    report: InvestigationReport | None = None
    error: str | None = None
    subscribers: set[asyncio.Queue[dict[str, str]]] = field(default_factory=set)


class CaseManager:
    """In-process case runner. The interface is intentionally ready for a durable store."""

    def __init__(self, service: InvestigationService) -> None:
        self.service = service
        self.cases: dict[str, CaseState] = {}

    async def create(self, request: InvestigationRequest) -> CaseState:
        case = CaseState(case_id=str(uuid4()))
        self.cases[case.case_id] = case
        asyncio.create_task(self._run(case, request), name=f"investigation-{case.case_id}")
        return case

    async def _run(self, case: CaseState, request: InvestigationRequest) -> None:
        case.status = "RUNNING"
        await self._publish(case, {"type": "status", "status": case.status})
        try:
            report = await self.service.investigate(
                request.ticker, request.trade_date, mode=request.mode
            )
            report.case_id = case.case_id
            case.report = report
            case.status = str(report.status)
            await self._publish(case, {"type": "completed", "status": case.status})
        except Exception:  # Deliberately do not send provider details to the browser.
            case.status = "FAILED_RECOVERABLE"
            case.error = (
                "The investigation could not complete. Please retry or use a recorded case."
            )
            await self._publish(case, {"type": "failed", "status": case.status})

    async def _publish(self, case: CaseState, event: dict[str, str]) -> None:
        for subscriber in list(case.subscribers):
            await subscriber.put(event)

    def get(self, case_id: str) -> CaseState:
        case = self.cases.get(case_id)
        if case is None:
            raise KeyError(case_id)
        return case

    async def events(self, case_id: str) -> AsyncIterator[dict[str, str]]:
        case = self.get(case_id)
        queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        case.subscribers.add(queue)
        try:
            yield {"type": "status", "status": case.status}
            while case.status in {"QUEUED", "RUNNING"}:
                yield await queue.get()
        finally:
            case.subscribers.discard(queue)


def create_app(service: InvestigationService | None = None) -> FastAPI:
    app = FastAPI(title="ASX Investigation Agent", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    if service is None:
        settings = Settings()
        service = InvestigationService(
            LiveToolGateway(settings), narrator=GeminiNarrativeGenerator(settings)
        )
    manager = CaseManager(service)
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
        case = await manager.create(request)
        return CaseAccepted(case_id=case.case_id)

    @app.get("/api/v1/investigations/{case_id}", response_model=None)
    async def get_investigation(
        case_id: str, format: Literal["json", "markdown"] = "json"
    ) -> dict[str, object] | Response:
        try:
            case = manager.get(case_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error
        if case.report is not None:
            if format == "markdown":
                return Response(render_markdown(case.report), media_type="text/markdown")
            return case.report.model_dump(mode="json")
        return {"case_id": case.case_id, "status": case.status, "error": case.error}

    @app.get("/api/v1/investigations/{case_id}/events")
    async def stream_events(case_id: str) -> StreamingResponse:
        try:
            manager.get(case_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error

        async def encode_events() -> AsyncIterator[str]:
            async for event in manager.events(case_id):
                yield f"event: {event['type']}\\ndata: {json.dumps(event)}\\n\\n"

        return StreamingResponse(encode_events(), media_type="text/event-stream")

    return app


app = create_app()
