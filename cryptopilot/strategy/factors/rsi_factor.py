"""RSI 超买超卖因子."""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class RSIFactor(FactorBase):
    """RSI 超买超卖评分.

    RSI < oversold → 超卖做多; RSI > overbought → 超买做空.
    """

    def __init__(self, name: str = "rsi", weight: float = 0.10, **params) -> None:
        super().__init__(name, weight, **params)
        self._period = params.get("period", 14)
        self._oversold = params.get("oversold", 30)
        self._overbought = params.get("overbought", 70)
        self._interval = params.get("interval", "5m")

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        sym = candidate.symbol
        klines = cache.get_klines(sym, self._interval, limit=self._period * 3)
        if len(klines) < self._period + 1:
            return self._make_score(0, "NEUTRAL", "K线数据不足")

        closes = [k.close for k in klines]
        rsi = self._calc_rsi(closes)
        if rsi <= 0:
            return self._make_score(0, "NEUTRAL", "RSI 未就绪")

        if rsi < self._oversold:
            strength = (self._oversold - rsi) / self._oversold * 100
            return self._make_score(strength, "LONG", f"超卖 RSI={rsi:.1f} < {self._oversold}")

        if rsi > self._overbought:
            strength = (rsi - self._overbought) / (100 - self._overbought) * 100
            return self._make_score(strength, "SHORT", f"超买 RSI={rsi:.1f} > {self._overbought}")

        return self._make_score(20, "NEUTRAL", f"中性 RSI={rsi:.1f}")

    def _calc_rsi(self, closes: list[float]) -> float:
        period = self._period
        if len(closes) < period + 1:
            return 0.0
        gains = losses = 0.0
        for i in range(-period, 0):
            delta = closes[i + 1] - closes[i]
            if delta > 0:
                gains += delta
            else:
                losses += -delta
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))


register_factor("rsi", RSIFactor)
