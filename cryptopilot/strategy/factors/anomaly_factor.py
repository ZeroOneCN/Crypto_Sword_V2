"""Z-Score 异动检测因子."""

import math
from collections import deque

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class AnomalyFactor(FactorBase):
    """Z-Score 异常检测.

    追踪价格和成交量的 Z-Score.
    偏离均值超过 2.5σ → 异动信号.
    """

    def __init__(self, name: str = "anomaly", weight: float = 0.10, **params) -> None:
        super().__init__(name, weight, **params)
        self._lookback = params.get("lookback", 30)
        self._price_history: dict[str, deque[float]] = {}
        self._vol_history: dict[str, deque[float]] = {}

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        sym = candidate.symbol
        price = candidate.current_price

        prices = self._price_history.setdefault(sym, deque(maxlen=self._lookback))
        volumes = self._vol_history.setdefault(sym, deque(maxlen=self._lookback))

        prices.append(price)
        kline_1m = cache.get_kline(sym, "1m")
        vol = kline_1m.volume if kline_1m else 0
        volumes.append(vol)

        z_scores = []

        if len(prices) >= 5:
            mean_p = sum(prices) / len(prices)
            std_p = math.sqrt(sum((p - mean_p) ** 2 for p in prices) / len(prices))
            z_price = abs(price - mean_p) / std_p if std_p > 0 else 0
            z_scores.append(z_price)

        if len(volumes) >= 5 and vol > 0:
            mean_v = sum(volumes) / len(volumes)
            std_v = math.sqrt(sum((v - mean_v) ** 2 for v in volumes) / len(volumes))
            z_vol = abs(vol - mean_v) / std_v if std_v > 0 else 0
            z_scores.append(z_vol)

        if not z_scores:
            return self._make_score(10, "NEUTRAL", "数据不足")

        max_z = max(z_scores)

        if max_z > 4.0:
            score = 100
        elif max_z > 3.0:
            score = 85
        elif max_z > 2.5:
            score = 70
        elif max_z > 2.0:
            score = 50
        elif max_z > 1.5:
            score = 30
        else:
            score = 10

        direction = "LONG" if candidate.change_24h_pct > 0 else "SHORT"
        return self._make_score(score, direction, f"Z={max_z:.1f}σ (价/量异常)")


register_factor("anomaly", AnomalyFactor)
