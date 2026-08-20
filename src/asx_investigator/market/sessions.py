from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from asx_investigator.domain.models import EventTiming, TradingSession

SYDNEY = ZoneInfo("Australia/Sydney")


def _easter_sunday(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * offset) // 451
    month, day = divmod(h + offset - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day + timedelta(days=2)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _asx_holidays(year: int) -> set[date]:
    easter = _easter_sunday(year)
    kings_birthday = date(year, 6, 1) + timedelta(days=(7 - date(year, 6, 1).weekday()) % 7 + 7)
    return {
        _observed(date(year, 1, 1)),
        _observed(date(year, 1, 26)),
        easter - timedelta(days=2),
        easter + timedelta(days=1),
        _observed(date(year, 4, 25)),
        kings_birthday,
        _observed(date(year, 12, 25)),
        _observed(date(year, 12, 26)),
    }


def _is_trading_day(value: date) -> bool:
    return value.weekday() < 5 and value not in _asx_holidays(value.year)


def _adjacent_session(value: date, direction: int) -> date:
    candidate = value + timedelta(days=direction)
    while not _is_trading_day(candidate):
        candidate += timedelta(days=direction)
    return candidate


def resolve_session(trade_date: date) -> TradingSession:
    is_trading_day = _is_trading_day(trade_date)
    local_midday = datetime.combine(trade_date, time(12), tzinfo=SYDNEY)
    label = "AEDT" if local_midday.utcoffset() == timedelta(hours=11) else "AEST"
    previous_session = _adjacent_session(trade_date, -1)
    next_session = _adjacent_session(trade_date, 1)
    if not is_trading_day:
        return TradingSession(
            trade_date=trade_date,
            timezone_label=label,
            is_trading_day=False,
            previous_session=previous_session,
            next_session=next_session,
        )
    is_early_close = trade_date.month == 12 and trade_date.day in {24, 31}
    close_time = time(14, 10) if is_early_close else time(16, 0)
    return TradingSession(
        trade_date=trade_date,
        timezone_label=label,
        is_trading_day=True,
        market_open=datetime.combine(trade_date, time(10), tzinfo=SYDNEY),
        market_close=datetime.combine(trade_date, close_time, tzinfo=SYDNEY),
        previous_session=previous_session,
        next_session=next_session,
    )


def classify_event(published_at: datetime, session: TradingSession) -> EventTiming:
    local = published_at.astimezone(SYDNEY)
    if not session.is_trading_day or local.date() != session.trade_date:
        return EventTiming(
            published_at=local,
            session_relationship="NON_TRADING_DAY",
            eligible_same_day_cause=False,
            eligible_next_day_cause=True,
        )
    assert session.market_open is not None and session.market_close is not None
    if local < session.market_open:
        relationship = "PRE_OPEN"
        same_day, next_day = True, False
    elif local <= session.market_close:
        relationship = "DURING_SESSION"
        same_day, next_day = True, False
    else:
        relationship = "POST_CLOSE"
        same_day, next_day = False, True
    return EventTiming(
        published_at=local,
        session_relationship=relationship,
        eligible_same_day_cause=same_day,
        eligible_next_day_cause=next_day,
    )
