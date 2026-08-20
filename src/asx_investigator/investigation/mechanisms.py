"""Deterministic mechanism tests over extractive evidence assertions."""

from __future__ import annotations

from datetime import datetime

from asx_investigator.domain.models import (
    CausalMechanism,
    EvidenceAssertion,
    MechanismTest,
    ValidationStatus,
)

MECHANISM_TAXONOMY_VERSION = "causal-mechanisms-v1"
MECHANISM_POLICY_VERSION = "phase2-v1"


def _mechanism_test(
    mechanism: CausalMechanism,
    assertions: list[EvidenceAssertion],
    evaluated_at: datetime,
) -> MechanismTest:
    supporting_assertions = [
        item
        for item in assertions
        if item.causal_eligible and item.mechanism_hint == mechanism
    ]
    supporting = [item.assertion_id for item in supporting_assertions]
    available_at = max(
        [
            evaluated_at,
            *[
                max(assertion.published_at, assertion.retrieved_at)
                for assertion in supporting_assertions
            ],
        ]
    )
    return MechanismTest(
        test_id=f"MT-{mechanism.value.replace('_', '-')}",
        mechanism=mechanism,
        status=ValidationStatus.PASS if supporting else ValidationStatus.NOT_AVAILABLE,
        summary=(
            f"{mechanism.value.replace('_', ' ').title()} is supported by exact, "
            "time-eligible source assertions."
            if supporting
            else f"No time-eligible {mechanism.value.lower()} assertion was available."
        ),
        taxonomy_version=MECHANISM_TAXONOMY_VERSION,
        policy_version=MECHANISM_POLICY_VERSION,
        created_at=available_at,
        supporting_assertion_ids=supporting,
    )


def run_mechanism_tests(
    assertions: list[EvidenceAssertion], *, evaluated_at: datetime
) -> list[MechanismTest]:
    """Record factual candidates at their deterministic evidence-availability time."""

    if evaluated_at.tzinfo is None:
        raise ValueError("Mechanism evaluation timestamp must be timezone-aware")
    # Each test uses the actual availability time of its own supporting
    # assertions. This handles an in-session corporate-action feed without
    # inventing a market-open timestamp or waiting on unrelated later evidence.
    tests = [_mechanism_test(CausalMechanism.MECHANICAL, assertions, evaluated_at)]
    for mechanism in (
        CausalMechanism.ISSUER_EVENT,
        CausalMechanism.SECTOR_READTHROUGH,
        CausalMechanism.COMMODITY_FX,
        CausalMechanism.MACRO_MARKET,
        CausalMechanism.MARKET_STRUCTURE,
        CausalMechanism.UNKNOWN,
    ):
        test = _mechanism_test(mechanism, assertions, evaluated_at)
        if test.supporting_assertion_ids:
            tests.append(test)
    return tests
