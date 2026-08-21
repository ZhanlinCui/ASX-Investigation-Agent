"""Operational use of admitted shared memory without causal leakage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from asx_investigator.domain.models import EvidenceItem, IssuerReferenceFact
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus
from asx_investigator.storage.memory import SharedMemoryRepository

_REFERENCE_PATTERNS = {
    "sector": re.compile(r"(?:^|\n)\s*sector\s*:\s*([^\n]{1,120})", re.IGNORECASE),
    "industry": re.compile(r"(?:^|\n)\s*industry\s*:\s*([^\n]{1,120})", re.IGNORECASE),
    "commodity_exposure": re.compile(
        r"(?:^|\n)\s*commodity exposure\s*:\s*([^\n]{1,120})", re.IGNORECASE
    ),
    "currency_exposure": re.compile(
        r"(?:^|\n)\s*currency exposure\s*:\s*([^\n]{1,120})", re.IGNORECASE
    ),
}


@dataclass(frozen=True)
class RetrievalContext:
    facts: list[IssuerReferenceFact]
    unavailable_providers: set[str]


class OperationalMemoryService:
    """Turns frozen facts/outcomes into routing state, never causal content."""

    def __init__(self, repository: SharedMemoryRepository) -> None:
        self.repository = repository

    async def admit_issuer_reference(
        self,
        ticker: str,
        evidence: EvidenceItem,
        *,
        valid_until: datetime,
    ) -> list[IssuerReferenceFact]:
        if evidence.authority not in {"PRIMARY_ISSUER", "APPROVED_OFFICIAL"}:
            return []
        admitted: list[IssuerReferenceFact] = []
        for field, pattern in _REFERENCE_PATTERNS.items():
            match = pattern.search(evidence.passage)
            if match is None:
                continue
            value = match.group(1).strip()
            admitted.append(
                await self.repository.put_reference_fact(
                    ticker=ticker,
                    field=field,
                    value=value,
                    source_url=evidence.source_url,
                    source_hash=evidence.content_hash,
                    valid_from=evidence.published_at,
                    valid_until=valid_until,
                )
            )
        return admitted

    async def observe_provider_outcome(self, outcome: ProviderOutcome[object]) -> None:
        await self.repository.record_provider_health(
            provider=outcome.provider,
            status=str(outcome.status),
            source_hash=(outcome.artifact.sha256 if outcome.artifact else None),
            source_url=f"provider://{outcome.provider}",
            observed_at=outcome.retrieved_at,
            valid_until=outcome.retrieved_at + timedelta(minutes=5),
        )

    async def retrieval_context(self, ticker: str, as_of: datetime) -> RetrievalContext:
        facts = await self.repository.list_context_facts(ticker, as_of=as_of)
        health = await self.repository.list_provider_health(as_of=as_of)
        unavailable = {
            entry.payload.get("provider", "")
            for entry in health
            if entry.payload.get("status")
            in {str(ProviderStatus.RETRYABLE_FAILURE), str(ProviderStatus.PERMANENT_FAILURE)}
        }
        unavailable.discard("")
        return RetrievalContext(facts=facts, unavailable_providers=unavailable)
