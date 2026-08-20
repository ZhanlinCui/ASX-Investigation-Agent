from datetime import date, datetime

import pytest

from asx_investigator.market.sessions import classify_event, resolve_session


def test_resolves_aest_session_on_winter_trading_day() -> None:
    session = resolve_session(date(2026, 8, 20))

    assert session.is_trading_day is True
    assert session.timezone_label == "AEST"
    assert session.market_open.isoformat() == "2026-08-20T10:00:00+10:00"
    assert session.market_close.isoformat() == "2026-08-20T16:00:00+10:00"


def test_resolves_early_close_with_aedt_offset() -> None:
    session = resolve_session(date(2026, 12, 24))

    assert session.timezone_label == "AEDT"
    assert session.market_close.isoformat() == "2026-12-24T14:10:00+11:00"


def test_non_trading_date_is_not_silently_remapped() -> None:
    session = resolve_session(date(2026, 8, 23))

    assert session.is_trading_day is False
    assert session.market_open is None
    assert session.previous_session == date(2026, 8, 21)
    assert session.next_session == date(2026, 8, 24)


def test_post_close_event_is_only_eligible_for_next_session() -> None:
    session = resolve_session(date(2026, 8, 20))
    timing = classify_event(datetime.fromisoformat("2026-08-20T16:10:00+10:00"), session)

    assert timing.session_relationship == "POST_CLOSE"
    assert timing.eligible_same_day_cause is False
    assert timing.eligible_next_day_cause is True


def test_prior_session_post_close_is_eligible_for_the_next_open() -> None:
    next_session = resolve_session(date(2026, 8, 21))
    timing = classify_event(
        datetime.fromisoformat("2026-08-20T16:10:00+10:00"), next_session
    )

    assert timing.session_relationship == "PRIOR_TO_SESSION"
    assert timing.eligible_same_day_cause is True


def test_older_evidence_is_context_not_an_automatic_current_session_cause() -> None:
    session = resolve_session(date(2026, 8, 21))
    timing = classify_event(datetime.fromisoformat("2026-08-19T12:00:00+10:00"), session)

    assert timing.session_relationship == "OLDER_CONTEXT"
    assert timing.eligible_same_day_cause is False


def test_christmas_and_boxing_day_observance_do_not_collide_in_2027() -> None:
    boxing_observed = resolve_session(date(2027, 12, 28))
    last_session_before_christmas = resolve_session(date(2027, 12, 24))

    assert boxing_observed.is_trading_day is False
    assert boxing_observed.previous_session == date(2027, 12, 24)
    assert boxing_observed.next_session == date(2027, 12, 29)
    assert last_session_before_christmas.market_close.isoformat() == "2027-12-24T14:10:00+11:00"


@pytest.mark.parametrize("year", (2022, 2033))
def test_sunday_christmas_keeps_both_observed_holidays(year: int) -> None:
    second_observed_holiday = resolve_session(date(year, 12, 27))

    assert second_observed_holiday.is_trading_day is False
    assert second_observed_holiday.previous_session == date(year, 12, 23)
    assert second_observed_holiday.next_session == date(year, 12, 28)
