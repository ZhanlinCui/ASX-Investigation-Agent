"""Versioned source authority and timing decisions for investigation evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from asx_investigator.domain.models import EvidenceRole, TradingSession
from asx_investigator.market.sessions import classify_event

SOURCE_POLICY_VERSION = "source-policy-v5"

_APPROVED_OFFICIAL_SUFFIXES = (
    "rba.gov.au",
    "abs.gov.au",
    "spglobal.com",
    "ftserussell.com",
)
_REJECTED_SUFFIXES = ("asx.com.au", "x.com", "twitter.com", "facebook.com", "linkedin.com")


class SourceDecision(BaseModel):
    """The only policy output used to classify a frozen source passage."""

    authority: Literal["PRIMARY_ISSUER", "APPROVED_OFFICIAL", "DISCOVERY_ONLY", "REJECTED"]
    evidence_role: EvidenceRole
    causal_eligible: bool
    reason_code: str
    policy_version: str = SOURCE_POLICY_VERSION

    @property
    def role(self) -> EvidenceRole:
        """Compatibility alias for evidence-construction call sites."""

        return self.evidence_role

    model_config = ConfigDict(frozen=True)


class SourcePolicy:
    """Classify sources by explicit host policy before causal use.

    Discovery is deliberately conservative. A known issuer IR host must be
    configured externally before an acquired document can become primary.
    """

    version = SOURCE_POLICY_VERSION

    def __init__(self, issuer_domains: set[str] | None = None) -> None:
        self.issuer_domains = frozenset(
            self._normalize_host(value) for value in issuer_domains or set() if value.strip()
        )

    @classmethod
    def from_csv(cls, issuer_domains: str | None) -> SourcePolicy:
        values = set((issuer_domains or "").split(","))
        return cls(values)

    def decide(
        self,
        source_url: str,
        published_at: datetime,
        session: TradingSession,
    ) -> SourceDecision:
        parsed = httpx.URL(source_url)
        host = self._normalize_host(parsed.host or "")
        if parsed.scheme != "https" or not host:
            return self._rejected("SOURCE_SCHEME_OR_HOST_REJECTED")
        if self._matches_any(host, _REJECTED_SUFFIXES):
            return self._rejected("SOURCE_DOMAIN_REJECTED")
        authority: Literal["PRIMARY_ISSUER", "APPROVED_OFFICIAL", "DISCOVERY_ONLY"]
        reason_code: str
        if self._matches_any(host, self.issuer_domains):
            authority = "PRIMARY_ISSUER"
            reason_code = "APPROVED_ISSUER_DOMAIN"
        elif self._matches_any(host, _APPROVED_OFFICIAL_SUFFIXES):
            authority = "APPROVED_OFFICIAL"
            reason_code = "APPROVED_OFFICIAL_DOMAIN"
        else:
            authority = "DISCOVERY_ONLY"
            reason_code = "UNAPPROVED_DISCOVERY_DOMAIN"

        if authority == "DISCOVERY_ONLY":
            return SourceDecision(
                authority=authority,
                evidence_role=EvidenceRole.CONTEMPORANEOUS_REACTION,
                causal_eligible=False,
                reason_code=reason_code,
            )
        timing = classify_event(published_at, session)
        if timing.eligible_same_day_cause:
            return SourceDecision(
                authority=authority,
                evidence_role=EvidenceRole.CAUSAL_INPUT,
                causal_eligible=True,
                reason_code=reason_code,
            )
        return SourceDecision(
            authority=authority,
            evidence_role=EvidenceRole.RETROSPECTIVE_CONTEXT,
            causal_eligible=False,
            reason_code=(
                "POST_CUTOFF_SOURCE"
                if timing.session_relationship == "POST_CLOSE"
                else "TIMING_INELIGIBLE"
            ),
        )

    @staticmethod
    def _normalize_host(value: str) -> str:
        return value.strip().lower().rstrip(".")

    @staticmethod
    def _matches_any(host: str, suffixes: tuple[str, ...] | frozenset[str]) -> bool:
        return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)

    @staticmethod
    def _rejected(reason_code: str) -> SourceDecision:
        return SourceDecision(
            authority="REJECTED",
            evidence_role=EvidenceRole.EXCLUDED,
            causal_eligible=False,
            reason_code=reason_code,
        )
