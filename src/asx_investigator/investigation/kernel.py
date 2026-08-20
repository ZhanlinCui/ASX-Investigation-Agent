from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime

from asx_investigator.agent.reasoning import InvestigationReasoner
from asx_investigator.domain.models import EvidenceItem, InvestigationReport
from asx_investigator.investigation.checkpoints import CheckpointEnvelope
from asx_investigator.investigation.service import _InvestigationPipeline
from asx_investigator.providers.protocols import InvestigationTools

StageObserver = Callable[[str, str, dict[str, object]], Awaitable[None]]


class InvestigationKernel:
    """Own the typed investigation run while preserving the public service contract."""

    def __init__(
        self,
        tools: InvestigationTools,
        reasoner: InvestigationReasoner | None = None,
    ) -> None:
        self._pipeline = _InvestigationPipeline(tools, reasoner)

    @property
    def tools(self) -> InvestigationTools:
        return self._pipeline.tools

    @property
    def reasoner(self) -> InvestigationReasoner | None:
        return self._pipeline.reasoner

    async def run(
        self,
        ticker: str,
        trade_date: str | date,
        mode: str = "LIVE",
        on_stage: StageObserver | None = None,
        supplied_evidence: list[EvidenceItem] | None = None,
        primary_only: bool = False,
        excluded_evidence_ids: list[str] | None = None,
        evidence_cutoff: datetime | None = None,
        version_id: str | None = None,
        request_artifact_hash: str | None = None,
        input_artifact_hashes: list[str] | None = None,
        resume_checkpoint: CheckpointEnvelope | None = None,
    ) -> InvestigationReport:
        return await self._pipeline.run(
            ticker,
            trade_date,
            mode,
            on_stage,
            supplied_evidence,
            primary_only,
            excluded_evidence_ids,
            evidence_cutoff,
            version_id,
            request_artifact_hash,
            input_artifact_hashes,
            resume_checkpoint,
        )
