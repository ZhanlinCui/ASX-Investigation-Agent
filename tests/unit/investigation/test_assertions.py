from datetime import UTC, date, datetime

from asx_investigator.domain.models import (
    CausalMechanism,
    EvidenceItem,
    EvidenceRole,
    ValidationStatus,
)
from asx_investigator.investigation.assertions import (
    MAX_ASSERTION_CHARACTERS,
    build_assertions,
)
from asx_investigator.investigation.mechanisms import run_mechanism_tests
from asx_investigator.market.sessions import SYDNEY, resolve_session


def issuer_evidence(evidence_id: str, passage: str) -> EvidenceItem:
    published_at = datetime(2026, 8, 20, 8, 30, tzinfo=SYDNEY)
    return EvidenceItem(
        evidence_id=evidence_id,
        source_name="BHP Investor Relations",
        source_url="https://example.test/bhp/guidance",
        published_at=published_at,
        retrieved_at=published_at,
        role=EvidenceRole.CAUSAL_INPUT,
        authority="PRIMARY_ISSUER",
        title="FY26 guidance update",
        passage=passage,
        content_hash="issuer-guidance-v1",
        locator="page:1:block:1",
    )


def test_assertions_are_extractable_and_case_scoped() -> None:
    assertions = build_assertions(
        [issuer_evidence("E1", "BHP raised FY26 production guidance.")],
        case_version_id="v1",
        session=resolve_session(date(2026, 8, 20)),
    )

    assert assertions[0].assertion_id == "A1"
    assert assertions[0].evidence_id == "E1"
    assert assertions[0].case_version_id == "v1"
    assert assertions[0].exact_text == "BHP raised FY26 production guidance."
    assert assertions[0].causal_eligible is True
    assert assertions[0].mechanism_hint == CausalMechanism.ISSUER_EVENT


def test_mechanism_tests_only_classify_factual_assertions() -> None:
    assertions = build_assertions(
        [
            issuer_evidence("M1", "SPLIT was effective on 2026-08-20.").model_copy(
                update={
                    "source_name": "Corporate action provider",
                    "authority": "APPROVED_OFFICIAL",
                    "evidence_kind": "CORPORATE_ACTION",
                }
            )
        ],
        case_version_id="v1",
        session=resolve_session(date(2026, 8, 20)),
    )

    tests = run_mechanism_tests(assertions, evaluated_at=datetime(2026, 8, 20, tzinfo=UTC))

    assert tests[0].mechanism == CausalMechanism.MECHANICAL
    assert tests[0].status == ValidationStatus.PASS
    assert tests[0].supporting_assertion_ids == ["A1"]


def test_mechanism_hint_ignores_adversarial_title_and_truncated_text() -> None:
    bounded_text = "BHP supplied this statement. "
    bounded_text += "x" * (MAX_ASSERTION_CHARACTERS - len(bounded_text))
    evidence = issuer_evidence("E1", bounded_text + " A dividend is effective today.").model_copy(
        update={
            "authority": "DISCOVERY_ONLY",
            "source_name": "Discovery feed",
            "title": "Dividend declaration and macro outlook",
        }
    )

    assertion = build_assertions(
        [evidence],
        case_version_id="v1",
        session=resolve_session(date(2026, 8, 20)),
    )[0]

    assert assertion.exact_text == bounded_text
    assert assertion.mechanism_hint == CausalMechanism.UNKNOWN
