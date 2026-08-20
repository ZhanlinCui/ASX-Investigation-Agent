from datetime import date

import httpx

from asx_investigator.providers.market_adapters import EODHDProvider, MarketstackProvider
from asx_investigator.providers.outcomes import ProviderStatus


def response(payload: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


async def test_eodhd_parses_official_eod_shape_and_sorts_oldest_first() -> None:
    rows = [
        {
            "date": "2026-08-20",
            "open": 10.5,
            "high": 11.2,
            "low": 10.4,
            "close": 11,
            "adjusted_close": 10.9,
            "volume": 500000,
        },
        {
            "date": "2026-08-19",
            "open": 10,
            "high": 10.2,
            "low": 9.9,
            "close": 10,
            "adjusted_close": 9.9,
            "volume": 100000,
        },
    ]
    transport = httpx.MockTransport(lambda request: response(rows))
    provider = EODHDProvider("secret", httpx.AsyncClient(transport=transport))

    result = await provider.get_daily_bars("BHP", date(2026, 8, 20))

    assert result.status == ProviderStatus.PARTIAL
    assert result.data is not None
    assert [item.trade_date.isoformat() for item in result.data] == ["2026-08-19", "2026-08-20"]
    assert result.provenance["symbol"] == "BHP.AU"


async def test_marketstack_parses_v2_shape() -> None:
    payload = {
        "pagination": {"count": 1, "total": 1},
        "data": [
            {
                "date": "2026-08-20T00:00:00+0000",
                "open": 10.5,
                "high": 11.2,
                "low": 10.4,
                "close": 11,
                "adj_close": 10.9,
                "volume": 500000.0,
                "symbol": "BHP",
                "exchange": "XASX",
            }
        ],
    }
    transport = httpx.MockTransport(lambda request: response(payload))
    provider = MarketstackProvider("secret", httpx.AsyncClient(transport=transport))

    result = await provider.get_daily_bars("BHP", date(2026, 8, 20))

    assert result.status == ProviderStatus.PARTIAL
    assert result.data is not None
    assert result.data[0].adjusted_close == 10.9
    assert result.provenance["exchange"] == "XASX"


async def test_http_rate_limit_is_retryable_and_empty_success_is_not_failure() -> None:
    rate_limited = EODHDProvider(
        "secret",
        httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response({}, 429))),
    )
    empty = MarketstackProvider(
        "secret",
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: response({"pagination": {"count": 0}, "data": []})
            )
        ),
    )

    failed = await rate_limited.get_daily_bars("BHP", date(2026, 8, 20))
    no_rows = await empty.get_daily_bars("BHP", date(2026, 8, 20))

    assert failed.status == ProviderStatus.RETRYABLE_FAILURE
    assert failed.error_code == "HTTP_429"
    assert no_rows.status == ProviderStatus.EMPTY
    assert no_rows.data == []
