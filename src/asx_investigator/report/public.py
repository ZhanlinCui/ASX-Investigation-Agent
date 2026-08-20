"""Explicit, fail-closed projections for public investigation surfaces.

The durable report is an internal audit record. It retains raw evidence,
provider diagnostics and model configuration so a case can be reproduced.
This module is the only boundary that turns that record into a browser or
export payload. New internal model fields are intentionally invisible here
until they are individually admitted.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit

from asx_investigator.domain.models import (
    CausalMechanism,
    Claim,
    ClaimType,
    InvestigationOutcome,
    InvestigationReport,
)
from asx_investigator.market.sessions import SYDNEY

_EXTERNAL_URL = re.compile(r"(?i)(?:https?://|ftp://|www\.)[^\s<>()\[\]]+")
_PUBLIC_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_:-]{0,119}$")
_PUBLIC_STAGE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")


def _display_text(value: str) -> str:
    """Keep labels readable without letting a stored external URL become a link."""

    return _EXTERNAL_URL.sub("[external URL omitted]", value)


def public_timestamp(value: datetime) -> str:
    """Render every public timestamp in the ASX product timezone."""

    if value.tzinfo is None:
        raise ValueError("Public timestamps must be timezone-aware")
    return value.astimezone(SYDNEY).isoformat()


def _public_identifier(value: str, *, fallback: str) -> str:
    return value if _PUBLIC_IDENTIFIER.fullmatch(value) else fallback


def _public_stage(value: str) -> str:
    return value if _PUBLIC_STAGE.fullmatch(value) else "stage"


def _source_host(source_url: str) -> str | None:
    """Expose a host label, never the path/query or full external URL."""

    host = urlsplit(source_url).hostname
    return host.lower() if host else None


def _content_endpoint(*, evidence_id: str, version_id: str) -> str:
    return (
        f"/api/v1/evidence/{quote(evidence_id, safe='')}/content"
        f"?version_id={quote(version_id, safe='')}"
    )


def _mechanism_for_claim(report: InvestigationReport, claim: Claim) -> CausalMechanism:
    evidence_ids = set(claim.supporting_evidence_ids)
    for assertion in report.assertions:
        if assertion.evidence_id in evidence_ids:
            return assertion.mechanism_hint
    return CausalMechanism.UNKNOWN


def _public_claim_text(report: InvestigationReport, claim: Claim) -> str:
    """Describe the decision without copying a raw document span into the report."""

    if claim.claim_type == ClaimType.CAUSE:
        mechanism = _mechanism_for_claim(report, claim)
        mechanism_label = mechanism.value.replace("_", " ").lower()
        return (
            f"A time-eligible {mechanism_label} explanation was validated; "
            "inspect the cited evidence passage for the exact source text."
        )
    if report.outcome == InvestigationOutcome.NO_IDENTIFIABLE_CATALYST:
        return "No identifiable catalyst cleared the evidence controls for this session."
    return "No causal explanation cleared the evidence and confidence controls."


def _public_assessment_summary(report: InvestigationReport) -> str:
    claim_id = report.assessment.primary_claim_id
    claim = next((item for item in report.claims if item.claim_id == claim_id), None)
    if claim is not None:
        return _public_claim_text(report, claim)
    if report.outcome == InvestigationOutcome.INCOMPLETE_DATA:
        return "Required point-in-time data is incomplete; no causal conclusion is published."
    if report.outcome == InvestigationOutcome.NO_IDENTIFIABLE_CATALYST:
        return "No identifiable catalyst cleared the evidence controls for this session."
    return "The available evidence cannot support a validated causal explanation."


def _public_hypothesis_mechanism(report: InvestigationReport, evidence_ids: list[str]) -> str:
    evidence_id_set = set(evidence_ids)
    for assertion in report.assertions:
        if assertion.evidence_id in evidence_id_set:
            return assertion.mechanism_hint.value
    return CausalMechanism.UNKNOWN.value


def public_report_payload(report: InvestigationReport) -> dict[str, Any]:
    """Build the documented report contract from an explicit allowlist.

    Never begin from ``model_dump`` and redact: that pattern silently publishes
    every field added to the internal report in the future.
    """

    evidence = [
        {
            "evidence_id": item.evidence_id,
            "source_name": _display_text(item.source_name),
            "source_host": _source_host(item.source_url),
            "published_at": public_timestamp(item.published_at),
            "retrieved_at": public_timestamp(item.retrieved_at),
            "authority": item.authority,
            "title": _display_text(item.title),
            "role": str(item.role),
            "content_hash": item.content_hash,
            "locator": item.locator,
            "page": item.page,
            "content_endpoint": _content_endpoint(
                evidence_id=item.evidence_id, version_id=report.run_id
            ),
        }
        for item in report.evidence
    ]
    claims = [
        {
            "claim_id": item.claim_id,
            "claim_type": str(item.claim_type),
            "text": _public_claim_text(report, item),
            "supporting_evidence_ids": list(item.supporting_evidence_ids),
            "contradicting_evidence_ids": list(item.contradicting_evidence_ids),
        }
        for item in report.claims
    ]
    return {
        "case_id": report.case_id,
        "run_id": report.run_id,
        "case_version": report.case_version,
        "parent_version_id": report.parent_version_id,
        "status": str(report.status),
        "outcome": str(report.outcome),
        "ticker": report.ticker,
        "trade_date": report.trade_date.isoformat(),
        "timezone_label": report.timezone_label,
        "instrument": {
            "asx_code": report.instrument.asx_code,
            "company_name": _display_text(report.instrument.company_name),
            "exchange": report.instrument.exchange,
            "currency": report.instrument.currency,
            "sector": _display_text(report.instrument.sector)
            if report.instrument.sector
            else None,
        },
        "market_move": (
            {
                "close_return_pct": report.market_move.close_return_pct,
                "open_gap_pct": report.market_move.open_gap_pct,
                "open_to_close_pct": report.market_move.open_to_close_pct,
                "turnover_aud": report.market_move.turnover_aud,
                "volume_zscore": report.market_move.volume_zscore,
                "return_zscore": report.market_move.return_zscore,
                "market_relative_return_pct": report.market_move.market_relative_return_pct,
                "is_unusual": report.market_move.is_unusual,
                "resolution": report.market_move.resolution,
            }
            if report.market_move is not None
            else None
        ),
        "assessment": {
            "primary_claim_id": report.assessment.primary_claim_id,
            "summary": _public_assessment_summary(report),
        },
        "claims": claims,
        "evidence": evidence,
        "confidence": {
            "band": report.confidence.band,
            "calibration_status": report.confidence.calibration_status,
            "rule_version": report.confidence.rule_version,
            "positive_factors": [
                _display_text(item) for item in report.confidence.positive_factors
            ],
            "negative_factors": [
                _display_text(item) for item in report.confidence.negative_factors
            ],
            "applied_caps": [_display_text(item) for item in report.confidence.applied_caps],
        },
        "claim_support": [
            {
                "claim_id": item.claim_id,
                "band": item.band,
                "supporting_evidence_ids": list(item.supporting_evidence_ids),
                "contradicting_evidence_ids": list(item.contradicting_evidence_ids),
                "factors": [_display_text(factor) for factor in item.factors],
            }
            for item in report.claim_support
        ],
        "coverage_status": report.coverage_status,
        "completeness": {
            "status": report.completeness.status,
            "required_capabilities": list(report.completeness.required_capabilities),
            "missing_capabilities": list(report.completeness.missing_capabilities),
        },
        "hypotheses": [
            {
                "hypothesis_id": item.hypothesis_id,
                "rank": item.rank,
                "status": str(item.status),
                "driver_label": _public_hypothesis_mechanism(
                    report, item.supporting_evidence_ids
                ),
                "statement": "Candidate is assessed against the cited evidence passages.",
                "supporting_evidence_ids": list(item.supporting_evidence_ids),
                "contradicting_evidence_ids": list(item.contradicting_evidence_ids),
                "validation_ids": list(item.validation_ids),
            }
            for item in report.hypotheses
        ],
        "validation_results": [
            {
                "validation_id": item.validation_id,
                "kind": _public_identifier(item.kind, fallback="VALIDATION"),
                "status": str(item.status),
                "evidence_ids": list(item.evidence_ids),
            }
            for item in report.validation_results
        ],
        "coverage_gaps": [
            {
                "gap_id": item.gap_id,
                "capability": _public_identifier(item.capability, fallback="CAPABILITY"),
                "provider": _public_identifier(item.provider, fallback="PROVIDER"),
                "retryable": item.retryable,
            }
            for item in report.coverage_gaps
        ],
        "conflicts": [
            {
                "conflict_id": item.conflict_id,
                "field": _public_identifier(item.field, fallback="FIELD"),
                "primary_source": _display_text(item.primary_source),
                "primary_value": _display_text(item.primary_value),
                "secondary_source": _display_text(item.secondary_source),
                "secondary_value": _display_text(item.secondary_value),
                "resolution": _display_text(item.resolution),
                "material": item.material,
            }
            for item in report.conflicts
        ],
        "source_policy_version": report.source_policy_version,
        "artifact_hashes": list(report.artifact_hashes),
        "checkpoint_lineage": [
            {
                "stage": _public_stage(item.stage),
                "created_at": public_timestamp(item.created_at),
                "schema_version": item.schema_version,
                "policy_version": item.policy_version,
            }
            for item in report.checkpoint_lineage
        ],
        "assertions": [
            {
                "assertion_id": item.assertion_id,
                "evidence_id": item.evidence_id,
                "span_hash": item.span_hash,
                "artifact_hash": item.artifact_hash,
                "published_at": public_timestamp(item.published_at),
                "retrieved_at": public_timestamp(item.retrieved_at),
                "source_authority": item.source_authority,
                "locator": item.locator,
                "role": str(item.role),
                "causal_eligible": item.causal_eligible,
                "mechanism_hint": str(item.mechanism_hint),
                "normalized_entities": list(item.normalized_entities),
                "normalized_values": dict(item.normalized_values),
                "contradicting_assertion_ids": list(item.contradicting_assertion_ids),
                "content_endpoint": _content_endpoint(
                    evidence_id=item.evidence_id, version_id=report.run_id
                ),
            }
            for item in report.assertions
        ],
        "mechanism_tests": [
            {
                "test_id": item.test_id,
                "mechanism": str(item.mechanism),
                "status": str(item.status),
                "summary": (
                    f"{item.mechanism.value.replace('_', ' ').title()} "
                    f"returned {item.status.value} against registered assertions."
                ),
                "taxonomy_version": item.taxonomy_version,
                "policy_version": item.policy_version,
                "created_at": public_timestamp(item.created_at),
                "supporting_assertion_ids": list(item.supporting_assertion_ids),
                "contradicting_assertion_ids": list(item.contradicting_assertion_ids),
            }
            for item in report.mechanism_tests
        ],
        "ledger": [
            {
                "sequence": item.sequence,
                "stage": _public_stage(item.stage),
                "status": _public_identifier(item.status, fallback="STATUS"),
                "input_hashes": list(item.input_hashes),
                "output_hashes": list(item.output_hashes),
                "schema_version": item.schema_version,
                "policy_version": item.policy_version,
                "validation_status": str(item.validation_status)
                if item.validation_status is not None
                else None,
                "created_at": public_timestamp(item.created_at),
            }
            for item in report.ledger
        ],
        "calibration_metadata": {
            "label": _display_text(report.calibration_metadata.label),
            "status": report.calibration_metadata.status,
            "corpus_version": report.calibration_metadata.corpus_version,
            "confidence_rule_version": report.calibration_metadata.confidence_rule_version,
            "bands": {
                band: {
                    "eligible_cases": sample.eligible_cases,
                    "correct_cases": sample.correct_cases,
                    "acceptable_alternative_cases": sample.acceptable_alternative_cases,
                    "abstained_cases": sample.abstained_cases,
                    "material_errors": sample.material_errors,
                    "status": sample.status,
                }
                for band, sample in report.calibration_metadata.bands.items()
            },
        },
        "trace_reference": (
            {
                "event_count": report.trace_reference.event_count,
                "last_sequence": report.trace_reference.last_sequence,
            }
            if report.trace_reference is not None
            else None
        ),
    }
