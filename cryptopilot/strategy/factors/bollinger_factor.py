"""Bollinger Bands 突破因子."""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class BollingerFactor(FactorBase):
    """布林带突破评分.

    价格接近/突破上轨 → 看多; 接近/突破下轨 → 看空.
    """

    def __init__(self, name: str = "bollinger", weight: float = 0.10, **params) -> None:
        super().__init__(name, weight, **params)
        self._period = params.get("period", 20)
        self._num_std = params.get("num_std", 2.0)
        self._interval = params.get("interval", "5m")

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        sym = candidate.symbol
        klines = cache.get_klines(sym, self._interval, limit=self._period + 10)
        if len(klines) < self._period:
            return self._make_score(0, "NEUTRAL", "K线数据不足")

        closes = [k.close for k in klines]
        mean = self._ma(closes, self._period)
        std = self._std(closes[-self._period:])
        if std <= 0 or mean <= 0:
            return self._make_score(0, "NEUTRAL", "波动率过低")

        price = candidate.current_price
        upper = mean + self._num_std * std
        lower = mean - self._num_std * std
        bw = upper - lower

        # 价格在带宽中的位置
        pos_in_band = (price - lower) / bw if bw > 0 else 0.5

        if price >= upper:
            strength = min((price - upper) / upper * 500, 100)
            return self._make_score(strength, "LONG", f"突破上轨 {price:.4f} > {upper:.4f}")
        if price <= lower:
            strength = min((lower - price) / lower * 500, 100)
            return self._make_score(strength, "SHORT", f"跌破下轨 {price:.4f} < {lower:.4f}")
        if pos_in_band > 0.8:
            return self._make_score(50, "LONG", f"接近上轨 ({pos_in_band*100:.0f}%)")
        if pos_in_band < 0.2:
            return self._make_score(50, "SHORT", f"接近下轨 ({pos_in_band*100:.0f}%)")

        return self._make_score(20, "NEUTRAL", f"中轨 ({pos_in_band*100:.0f}%)")


register_factor("bollinger", BollingerFactor)
