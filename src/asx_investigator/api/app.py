from __future__ import annotations

import asyncio
import hashlib
import json
import re
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

from asx_investigator.agent.gemini import GeminiInvestigationReasoner
from asx_investigator.domain.models import (
    EvidenceItem,
    EvidenceRole,
    InvestigationReport,
    InvestigationStatus,
    IssuerReferenceFact,
    TraceReference,
)
from asx_investigator.evidence.ingestion import (
    MAX_SOURCE_BYTES,
    HttpxPublicAddressConnector,
    SourceIngestor,
    SourceRejected,
)
from asx_investigator.evidence.parsing import parse_source
from asx_investigator.evidence.registry import SQLiteEvidenceRegistry
from asx_investigator.investigation.checkpoints import (
    CHECKPOINT_POLICY_VERSION,
    CHECKPOINT_SCHEMA_VERSION,
    CheckpointEnvelope,
    InvestigationState,
)
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.market.sessions import resolve_case_context_as_of
from asx_investigator.providers.capture import canonical_json_bytes
from asx_investigator.providers.live import LiveToolGateway
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.report.markdown import render_markdown
from asx_investigator.settings import Settings
from asx_investigator.storage.artifacts import ArtifactStore
from asx_investigator.storage.memory import SharedMemoryRepository
from asx_investigator.storage.repository import CaseVersionRecord, SQLiteCaseRepository


class InvestigationRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    trade_date: date
    mode: str = "LIVE"
    source_ids: list[str] = Field(default_factory=list)
    primary_only: bool = False
    excluded_evidence_ids: list[str] = Field(default_factory=list)
    evidence_cutoff: datetime | None = None

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

    @field_validator("evidence_cutoff")
    @classmethod
    def validate_cutoff(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("evidence_cutoff must include a timezone")
        return value


class RefinementRequest(BaseModel):
    primary_only: bool | None = None
    excluded_evidence_ids: list[str] | None = None
    source_ids: list[str] | None = None
    evidence_cutoff: datetime | None = None


class CaseAccepted(BaseModel):
    case_id: str
    version_id: str
    version_number: int
    parent_version_id: str | None = None
    status: str = "QUEUED"


class SourceFetchRequest(BaseModel):
    url: str
    title: str = Field(min_length=1, max_length=240)
    published_at: datetime
    is_official: bool = False


class SourceAccepted(BaseModel):
    source_id: str
    title: str
    artifact_id: str
    content_hash: str
    passage_count: int
    published_at: datetime
    retrieved_at: datetime


def public_report_payload(report: InvestigationReport) -> dict[str, object]:
    """Return the stable public report view without expanding audit exposure.

    The persisted report is the internal validated record. Phase 3 adds a
    narrower public projection for its assertion, mechanism, ledger and
    calibration fields so a future internal field cannot accidentally expose
    provider payloads, model traces, private memory or calibration
    probabilities through the case endpoint.
    """

    payload: dict[str, object] = report.model_dump(mode="json")
    payload["assertions"] = [
        item.model_dump(
            mode="json",
            include={
                "assertion_id",
                "evidence_id",
                "exact_text",
                "span_hash",
                "artifact_hash",
                "published_at",
                "retrieved_at",
                "source_authority",
                "locator",
                "role",
                "causal_eligible",
                "mechanism_hint",
                "normalized_entities",
                "normalized_values",
                "contradicting_assertion_ids",
            },
        )
        for item in report.assertions
    ]
    payload["mechanism_tests"] = [
        item.model_dump(
            mode="json",
            include={
                "test_id",
                "mechanism",
                "status",
                "summary",
                "taxonomy_version",
                "policy_version",
                "created_at",
                "supporting_assertion_ids",
                "contradicting_assertion_ids",
            },
        )
        for item in report.mechanism_tests
    ]
    payload["ledger"] = [
        item.model_dump(
            mode="json",
            include={
                "sequence",
                "stage",
                "status",
                "input_hashes",
                "output_hashes",
                "schema_version",
                "policy_version",
                "validation_status",
                "created_at",
            },
        )
        for item in report.ledger
    ]
    calibration = report.calibration_metadata
    payload["calibration_metadata"] = {
        **calibration.model_dump(mode="json", exclude={"bands"}),
        "bands": {
            band: sample.model_dump(
                mode="json",
                include={
                    "eligible_cases",
                    "correct_cases",
                    "acceptable_alternative_cases",
                    "abstained_cases",
                    "material_errors",
                    "status",
                },
            )
            for band, sample in calibration.bands.items()
        },
    }
    return payload


class CaseManager:
    """Durable case runner with append-only public events."""

    _STARTUP_RECLAIMABLE_STATUSES = ("QUEUED", "RUNNING", "FAILED_RECOVERABLE")

    def __init__(
        self,
        service: InvestigationService,
        repository: SQLiteCaseRepository,
        evidence_registry: SQLiteEvidenceRegistry,
        recorded_service: InvestigationService | None = None,
        shared_memory: SharedMemoryRepository | None = None,
    ) -> None:
        self.service = service
        self.recorded_service = recorded_service or service
        self.repository = repository
        self.evidence_registry = evidence_registry
        self.shared_memory = shared_memory or SharedMemoryRepository(
            repository.database_path
        )
        self.tasks: set[asyncio.Task[None]] = set()
        self._tasks_by_version: dict[str, asyncio.Task[None]] = {}
        self._case_locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        await self.repository.initialize()
        await self.shared_memory.initialize()
        for record in await self.repository.list_recoverable_versions():
            request = InvestigationRequest.model_validate(record.request_payload)
            try:
                await self._recover_or_branch(record, request)
            except ValueError:
                # A concurrent request has already superseded this startup record.
                continue

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
        async with self._case_lock(case_id):
            parent = await self.repository.get_case(case_id)
            await self._cancel_run(parent.version_id)
            payload = dict(parent.request_payload)
            payload.update(refinement.model_dump(mode="json", exclude_none=True))
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
        try:
            record = await self.repository.get_case(case_id)
        except KeyError:
            record = await self.repository.get_version(case_id)
        current = await self.repository.get_case(record.case_id)
        if current.version_id != record.version_id:
            raise ValueError("Only the current case version can be retried")
        if record.status != "FAILED_RECOVERABLE":
            raise ValueError("Only FAILED_RECOVERABLE cases can be retried")
        request = InvestigationRequest.model_validate(record.request_payload)
        return await self._recover_or_branch(
            record,
            request,
            allowed_statuses=("FAILED_RECOVERABLE",),
        )

    def _launch(
        self,
        record: CaseVersionRecord,
        request: InvestigationRequest,
        resume_checkpoint: CheckpointEnvelope | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._run(record, request, resume_checkpoint),
            name=f"investigation-{record.version_id}",
        )
        self.tasks.add(task)

        def discard(completed: asyncio.Task[None]) -> None:
            self.tasks.discard(completed)
            if self._tasks_by_version.get(record.version_id) is completed:
                self._tasks_by_version.pop(record.version_id, None)

        self._tasks_by_version[record.version_id] = task
        task.add_done_callback(discard)

    async def _cancel_run(self, version_id: str) -> None:
        task = self._tasks_by_version.get(version_id)
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    def _case_lock(self, case_id: str) -> asyncio.Lock:
        return self._case_locks.setdefault(case_id, asyncio.Lock())

    @staticmethod
    def _request_artifact_hash(request: InvestigationRequest) -> str:
        return hashlib.sha256(
            canonical_json_bytes(request.model_dump(mode="json"))
        ).hexdigest()

    async def _initial_input_hashes(
        self,
        request: InvestigationRequest,
        *,
        context_facts: list[IssuerReferenceFact] | None = None,
    ) -> list[str]:
        request_hash = self._request_artifact_hash(request)
        source_hashes = await self.repository.get_source_artifact_hashes(request.source_ids)
        memory_hashes = [fact.ledger_hash for fact in context_facts or []]
        return sorted(set([request_hash, *source_hashes, *memory_hashes]))

    async def _case_context_facts(
        self, request: InvestigationRequest
    ) -> tuple[list[IssuerReferenceFact], datetime]:
        """Resolve immutable non-causal reference context at the sealed case cutoff."""

        context_as_of = resolve_case_context_as_of(
            request.trade_date, request.evidence_cutoff
        )
        facts = await self.shared_memory.list_context_facts(
            request.ticker, as_of=context_as_of
        )
        return facts, context_as_of

    async def _compatible_checkpoint(
        self,
        record: CaseVersionRecord,
        request: InvestigationRequest,
    ) -> tuple[CheckpointEnvelope | None, str | None]:
        try:
            candidate = await self.repository.latest_checkpoint(record.version_id)
        except (TypeError, ValidationError, ValueError):
            return None, "CHECKPOINT_CONTENT_MISMATCH"
        if candidate is None:
            return None, "NO_CHECKPOINT"
        if candidate.policy_version != CHECKPOINT_POLICY_VERSION:
            return None, "POLICY_MISMATCH"
        if candidate.schema_version != CHECKPOINT_SCHEMA_VERSION:
            return None, "SCHEMA_MISMATCH"
        try:
            state = InvestigationState.model_validate(candidate.typed_state_json)
            context_facts, _ = await self._case_context_facts(request)
            expected_initial_inputs = await self._initial_input_hashes(
                request,
                context_facts=context_facts,
            )
            if state.version_id != record.version_id:
                return None, "VERSION_MISMATCH"
            if state.request_artifact_hash != self._request_artifact_hash(request):
                return None, "REQUEST_MISMATCH"
            if sorted(state.initial_input_artifact_hashes) != expected_initial_inputs:
                return None, "INPUT_ARTIFACT_MISMATCH"
            if state.completed_stage != candidate.stage:
                return None, "STAGE_MISMATCH"
            if state.input_hashes() != sorted(candidate.input_artifact_hashes):
                return None, "CHECKPOINT_INPUT_MISMATCH"
            if state.output_hashes() != sorted(candidate.output_artifact_hashes):
                return None, "CHECKPOINT_OUTPUT_MISMATCH"
        except (KeyError, TypeError, ValidationError, ValueError):
            return None, "CHECKPOINT_CONTENT_MISMATCH"
        compatible = await self.repository.latest_compatible_checkpoint(
            record.version_id,
            policy_version=CHECKPOINT_POLICY_VERSION,
            input_artifact_hashes=state.input_hashes(),
        )
        if compatible is None or compatible.created_at != candidate.created_at:
            return None, "CHECKPOINT_COMPATIBILITY_MISMATCH"
        return candidate, None

    async def _recover_or_branch(
        self,
        record: CaseVersionRecord,
        request: InvestigationRequest,
        *,
        allowed_statuses: tuple[str, ...] = _STARTUP_RECLAIMABLE_STATUSES,
    ) -> CaseVersionRecord:
        async with self._case_lock(record.case_id):
            current = await self.repository.get_case(record.case_id)
            if current.version_id != record.version_id:
                raise ValueError("Only the current case version can be recovered")
            record = await self.repository.get_version(record.version_id)
            if record.status not in allowed_statuses:
                raise ValueError("Case version cannot be recovered from its current status")
            checkpoint, incompatibility = await self._compatible_checkpoint(record, request)
            if checkpoint is not None:
                resumed = await self.repository.queue_current_checkpoint_resume(
                    record.version_id,
                    checkpoint.stage,
                    allowed_statuses=allowed_statuses,
                )
                await self.repository.append_event(
                    record.version_id,
                    "recovery",
                    checkpoint.stage,
                    "RESUMED",
                    {"checkpoint_created_at": checkpoint.created_at.isoformat()},
                )
                self._launch(resumed, request, checkpoint)
                return resumed

            child = await self.repository.create_checkpoint_recovery_child(
                record.version_id,
                request_payload=request.model_dump(mode="json"),
                reason=incompatibility or "UNKNOWN",
            )
            self._launch(child, request)
            return child

    async def _run(
        self,
        record: CaseVersionRecord,
        request: InvestigationRequest,
        resume_checkpoint: CheckpointEnvelope | None = None,
    ) -> None:
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
                checkpoint_payload = payload.get("checkpoint")
                event_payload = dict(payload)
                if checkpoint_payload is not None:
                    checkpoint = CheckpointEnvelope.model_validate(checkpoint_payload)
                    if checkpoint.version_id != record.version_id:
                        raise ValueError("Stage checkpoint belongs to another version")
                    await self.repository.save_checkpoint(checkpoint)
                    event_payload["checkpoint"] = checkpoint.model_dump(
                        mode="json",
                        exclude={"typed_state_json"},
                    )
                await self.repository.update_status(
                    record.version_id, "RUNNING", active_stage=current_stage
                )
                await self.repository.append_event(
                    record.version_id,
                    "stage",
                    current_stage,
                    stage_status,
                    event_payload,
                )

            context_facts, context_as_of = await self._case_context_facts(request)
            supplied_evidence = await self.repository.get_source_evidence(request.source_ids)
            for item in supplied_evidence:
                await self.evidence_registry.register(record.version_id, item)
            if supplied_evidence:
                ranked: list[EvidenceItem] = []
                seen: set[str] = set()
                for query in (
                    request.ticker,
                    "guidance",
                    "results",
                    "production",
                    "acquisition",
                    "dividend",
                    "earnings",
                ):
                    matches = await self.evidence_registry.search(
                        record.version_id,
                        query,
                        limit=12,
                        role=EvidenceRole.CAUSAL_INPUT,
                        published_before=request.evidence_cutoff,
                    )
                    for match in matches:
                        if match.evidence_id not in seen:
                            ranked.append(match)
                            seen.add(match.evidence_id)
                    if len(ranked) >= 12:
                        break
                supplied_evidence = (ranked or supplied_evidence)[:12]
            active_service = (
                self.recorded_service if request.mode == "RECORDED" else self.service
            )
            report = await active_service.investigate(
                request.ticker,
                request.trade_date,
                mode=request.mode,
                on_stage=persist_stage,
                supplied_evidence=supplied_evidence,
                primary_only=request.primary_only,
                excluded_evidence_ids=request.excluded_evidence_ids,
                evidence_cutoff=request.evidence_cutoff,
                version_id=record.version_id,
                request_artifact_hash=self._request_artifact_hash(request),
                input_artifact_hashes=await self._initial_input_hashes(
                    request,
                    context_facts=context_facts,
                ),
                resume_checkpoint=resume_checkpoint,
                context_facts=context_facts,
                context_as_of=context_as_of,
            )
            report.case_id = record.case_id
            report.run_id = record.version_id
            report.status = InvestigationStatus.COMPLETED
            report.parent_case_id = record.case_id if record.parent_version_id else None
            report.parent_version_id = record.parent_version_id
            report.case_version = record.version_number
            report.checkpoint_lineage = await self.repository.list_checkpoint_summaries(
                record.version_id
            )
            report.artifact_hashes = sorted(
                {
                    diagnostic.artifact_id
                    for diagnostic in report.provider_diagnostics
                    if diagnostic.artifact_id is not None
                }
            )
            for diagnostic in report.provider_diagnostics:
                await self.repository.record_provider_call(
                    record.version_id,
                    **diagnostic.model_dump(),
                )
            for item in report.evidence:
                if not await self.evidence_registry.register(record.version_id, item):
                    raise ValueError(
                        "Evidence content was not uniquely identified after deduplication"
                    )
            await self.repository.update_status(
                record.version_id, "RUNNING", active_stage="persist_and_publish"
            )
            await self.repository.append_event(
                record.version_id, "stage", "persist_and_publish", "RUNNING"
            )
            persisted_events = await self.repository.list_events(record.version_id)
            report.trace_reference = TraceReference(
                event_count=len(persisted_events) + 1,
                last_sequence=persisted_events[-1].sequence + 1,
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
        except (KeyError, LookupError, ValueError):
            await self.repository.update_status(
                record.version_id,
                "FAILED",
                active_stage=stage,
                error="The case input or referenced source is invalid and cannot be retried.",
            )
            await self.repository.append_event(
                record.version_id, "failed", stage, "FAILED"
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
    injected_repository = repository is not None
    recorded_service = service
    if repository is None:
        path = (
            Path(tempfile.mkdtemp(prefix="asx-investigator-test-")) / "cases.db"
            if injected_service
            else _database_path(settings)
        )
        repository = SQLiteCaseRepository(path)
    evidence_registry = SQLiteEvidenceRegistry(repository.database_path)
    artifact_root = (
        repository.database_path.parent / "artifacts"
        if injected_service or injected_repository
        else settings.artifact_dir
    )
    artifact_store = ArtifactStore(artifact_root)
    if service is None:
        service = InvestigationService(
            LiveToolGateway(settings, artifacts=artifact_store),
            reasoner=GeminiInvestigationReasoner(settings),
        )
        recorded_service = InvestigationService(RecordedToolGateway.default())
    source_connector = HttpxPublicAddressConnector(timeout=20)
    source_ingestor = SourceIngestor(artifact_store, source_connector)
    manager = CaseManager(
        service,
        repository,
        evidence_registry,
        recorded_service=recorded_service,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await repository.initialize()
        await evidence_registry.initialize()
        await manager.start()
        yield
        await manager.stop()
        await source_connector.aclose()
        close_tools = getattr(service.tools, "close", None)
        if close_tools is not None:
            await close_tools()

    app = FastAPI(title="ASX Investigation Agent", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    app.state.case_manager = manager
    app.state.shared_memory = manager.shared_memory
    app.state.artifact_store = artifact_store
    app.state.source_ingestor = source_ingestor

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

    @app.get("/api/v1/investigations/{case_id}/versions")
    async def list_versions(case_id: str) -> dict[str, object]:
        try:
            records = await repository.list_versions(case_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error
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
            return public_report_payload(report)
        return {
            "case_id": record.case_id,
            "version_id": record.version_id,
            "version_number": record.version_number,
            "status": record.status,
            "active_stage": record.active_stage,
            "error": record.error,
        }

    @app.get("/api/v1/investigations/{case_id}/events")
    async def stream_events(
        case_id: str,
        after_sequence: int = 0,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        try:
            await repository.get_case(case_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error

        replay_after = after_sequence
        if last_event_id is not None:
            try:
                replay_after = max(replay_after, int(last_event_id))
            except ValueError as error:
                raise HTTPException(
                    status_code=400, detail="Last-Event-ID must be an integer"
                ) from error

        async def encode_events() -> AsyncIterator[str]:
            async for event in manager.events(case_id, replay_after):
                yield (
                    f"id: {event['sequence']}\n"
                    f"event: {event['event_type']}\n"
                    f"data: {json.dumps(event)}\n\n"
                )

        return StreamingResponse(encode_events(), media_type="text/event-stream")

    async def persist_source(
        *,
        frozen,
        title: str,
        published_at: datetime,
        is_official: bool,
        source_url: str,
    ) -> SourceAccepted:
        if published_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="published_at must include a timezone")
        passages = parse_source(
            source_ingestor.artifacts.get(frozen.artifact_id), frozen.mime_type
        )
        if not passages:
            raise HTTPException(status_code=422, detail="No readable passages were found")
        record = await repository.create_source(
            artifact_id=frozen.artifact_id,
            source_url=source_url,
            mime_type=frozen.mime_type,
            title=title,
            published_at=published_at,
            content_hash=frozen.sha256,
            authority="USER_SUPPLIED_OFFICIAL" if is_official else "USER_SUPPLIED",
            passages=[item.model_dump() for item in passages],
        )
        return SourceAccepted.model_validate(record)

    @app.post(
        "/api/v1/sources/upload",
        response_model=SourceAccepted,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_source(
        file: UploadFile = File(...),
        title: str = Form(...),
        published_at: datetime = Form(...),
        is_official: bool = Form(False),
    ) -> SourceAccepted:
        content = await file.read(MAX_SOURCE_BYTES + 1)
        try:
            frozen = source_ingestor.upload(
                content, file.content_type or "application/octet-stream"
            )
        except SourceRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return await persist_source(
            frozen=frozen,
            title=title,
            published_at=published_at,
            is_official=is_official,
            source_url=f"upload://{file.filename or 'source'}",
        )

    @app.post(
        "/api/v1/sources/fetch",
        response_model=SourceAccepted,
        status_code=status.HTTP_201_CREATED,
    )
    async def fetch_source(request: SourceFetchRequest) -> SourceAccepted:
        try:
            frozen = await source_ingestor.fetch(request.url)
        except (SourceRejected, httpx.HTTPError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return await persist_source(
            frozen=frozen,
            title=request.title,
            published_at=request.published_at,
            is_official=request.is_official,
            source_url=frozen.source_url or request.url,
        )

    @app.get("/api/v1/evidence/{evidence_id}/content")
    async def evidence_content(
        evidence_id: str, version_id: str | None = None
    ) -> dict[str, object]:
        try:
            return await repository.find_evidence_content(
                evidence_id, version_id=version_id
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Evidence not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return app


app = create_app()
