from datetime import date, timedelta

from asx_investigator.market.forensics import DailyBar, calculate_market_move


def test_calculates_return_gap_turnover_and_volume_anomaly() -> None:
    start = date(2026, 5, 1)
    bars = [
        DailyBar(
            trade_date=start + timedelta(days=index),
            open=10.0,
            high=10.2,
            low=9.9,
            close=10.0,
            adjusted_close=10.0,
            volume=100_000,
        )
        for index in range(61)
    ]
    bars[-1] = DailyBar(
        trade_date=bars[-1].trade_date,
        open=10.5,
        high=11.2,
        low=10.4,
        close=11.0,
        adjusted_close=11.0,
        volume=500_000,
    )

    move = calculate_market_move(bars, benchmark_return_pct=1.0)

    assert move.close_return_pct == 10.0
    assert move.open_gap_pct == 5.0
    assert move.open_to_close_pct == round((11.0 / 10.5 - 1) * 100, 4)
    assert move.turnover_aud == 5_500_000.0
    assert move.market_relative_return_pct == 9.0
    assert move.volume_zscore is not None
    assert move.is_unusual is True
