from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import fmean, pstdev

from asx_investigator.domain.models import MarketMove


@dataclass(frozen=True)
class DailyBar:
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


def _zscore(value: float, values: list[float]) -> float | None:
    if len(values) < 40:
        return None
    deviation = pstdev(values)
    if deviation == 0:
        return 999.0 if value != fmean(values) else 0.0
    return round((value - fmean(values)) / deviation, 4)


def calculate_market_move(
    bars: list[DailyBar], benchmark_return_pct: float | None = None
) -> MarketMove:
    if len(bars) < 2:
        raise ValueError("At least two daily bars are required")
    previous, current = bars[-2], bars[-1]
    close_return = (current.close / previous.close - 1) * 100
    open_gap = (current.open / previous.close - 1) * 100
    open_to_close = (current.close / current.open - 1) * 100
    historical_returns = [
        (bar.close / prior.close - 1) * 100
        for prior, bar in zip(bars[:-2], bars[1:-1], strict=True)
    ]
    historical_volumes = [float(bar.volume) for bar in bars[:-1]]
    return_zscore = _zscore(close_return, historical_returns)
    volume_zscore = _zscore(float(current.volume), historical_volumes)
    market_relative = None if benchmark_return_pct is None else close_return - benchmark_return_pct
    unusual = bool(
        (return_zscore is not None and abs(return_zscore) >= 3)
        or (volume_zscore is not None and abs(volume_zscore) >= 3)
        or abs(close_return) >= 5
    )
    return MarketMove(
        close_return_pct=round(close_return, 4),
        open_gap_pct=round(open_gap, 4),
        open_to_close_pct=round(open_to_close, 4),
        turnover_aud=round(current.close * current.volume, 2),
        volume_zscore=volume_zscore,
        return_zscore=return_zscore,
        market_relative_return_pct=None if market_relative is None else round(market_relative, 4),
        is_unusual=unusual,
    )
