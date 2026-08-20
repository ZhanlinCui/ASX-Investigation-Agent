"""Backward-compatible facade for the investigation kernel."""

from __future__ import annotations

from datetime import date, datetime

from asx_investigator.agent.reasoning import InvestigationReasoner
from asx_investigator.domain.models import EvidenceItem, InvestigationReport
from asx_investigator.investigation.checkpoints import CheckpointEnvelope
from asx_investigator.investigation.kernel import InvestigationKernel, StageObserver
from asx_investigator.providers.protocols import InvestigationTools


class InvestigationService:
    """Preserve the established service API while delegating all work to the kernel."""

    def __init__(
        self,
        tools: InvestigationTools,
        reasoner: InvestigationReasoner | None = None,
    ) -> None:
        self.kernel = InvestigationKernel(tools, reasoner)

    @property
    def tools(self) -> InvestigationTools:
        return self.kernel.tools

    @property
    def reasoner(self) -> InvestigationReasoner | None:
        return self.kernel.reasoner

    async def investigate(
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
        return await self.kernel.run(
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
