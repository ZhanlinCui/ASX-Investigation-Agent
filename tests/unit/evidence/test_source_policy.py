from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from asx_investigator.domain.models import EvidenceRole
from asx_investigator.evidence.source_policy import SourcePolicy
from asx_investigator.market.sessions import resolve_session

SYDNEY = ZoneInfo("Australia/Sydney")


def test_approved_issuer_source_is_causal_only_when_available_before_the_session() -> None:
    policy = SourcePolicy(issuer_domains={"investors.issuer.example"})
    session = resolve_session(date(2026, 8, 20))

    eligible = policy.decide(
        "https://investors.issuer.example/results/guidance.html",
        datetime(2026, 8, 20, 8, 15, tzinfo=SYDNEY),
        session,
    )
    after_close = policy.decide(
        "https://investors.issuer.example/results/guidance.html",
        datetime(2026, 8, 20, 16, 30, tzinfo=SYDNEY),
        session,
    )

    assert eligible.authority == "PRIMARY_ISSUER"
    assert eligible.role == EvidenceRole.CAUSAL_INPUT
    assert eligible.causal_eligible is True
    assert after_close.authority == "PRIMARY_ISSUER"
    assert after_close.role == EvidenceRole.RETROSPECTIVE_CONTEXT
    assert after_close.causal_eligible is False


def test_unapproved_search_and_prohibited_asx_domains_never_become_primary() -> None:
    policy = SourcePolicy(issuer_domains={"investors.issuer.example"})
    session = resolve_session(date(2026, 8, 20))
    published = datetime(2026, 8, 20, 8, 15, tzinfo=SYDNEY)

    news = policy.decide("https://news.example/rewrite", published, session)
    asx = policy.decide("https://www.asx.com.au/announcement", published, session)
    social = policy.decide("https://x.com/example/status/1", published, session)

    assert news.authority == "DISCOVERY_ONLY"
    assert news.role == EvidenceRole.CONTEMPORANEOUS_REACTION
    assert asx.authority == "REJECTED"
    assert social.authority == "REJECTED"


def test_approved_official_index_and_macro_domains_are_typed_separately() -> None:
    policy = SourcePolicy()
    session = resolve_session(date(2026, 8, 20))

    decision = policy.decide(
        "https://www.spglobal.com/spdji/en/indices/equity/notice.html",
        datetime(2026, 8, 20, 8, 15, tzinfo=SYDNEY),
        session,
    )

    assert decision.authority == "APPROVED_OFFICIAL"
    assert decision.role == EvidenceRole.CAUSAL_INPUT
    assert decision.reason_code == "APPROVED_OFFICIAL_DOMAIN"
