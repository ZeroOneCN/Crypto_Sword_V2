"""ATR 动态止损因子 — crypto_sword 风控核心.

ATR (Average True Range) 衡量真实波动幅度,
用于计算动态止损距禈, 代替固定百分比.
"""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class ATRFactor(FactorBase):
    """ATR 波动率因子.

    ATR 越高 → 波动越大 → 止损距禈需要更大.
    评分方向: 高 ATR = 高风险, 降低仓位; 低 ATR = 稳定, 适合开仓.

    止损价计算 (供外部调用):
      stop_distance = ATR * multiplier
    """

    def __init__(self, name: str = "atr", weight: float = 0.10, **params) -> None:
        super().__init__(name, weight, **params)
        self._period = params.get("period", 14)
        self._interval = params.get("interval", "5m")
        self._multiplier = params.get("multiplier", 2.0)

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        sym = candidate.symbol
        klines = cache.get_klines(sym, self._interval, limit=self._period + 10)
        if len(klines) < self._period + 1:
            return self._make_score(0, "NEUTRAL", "K线数据不足")

        atr = self._calc_atr(klines)
        if atr <= 0 or candidate.current_price <= 0:
            return self._make_score(0, "NEUTRAL", "ATR计算异常")

        atr_pct = atr / candidate.current_price * 100

        # ATR% 评分: 中等波动最佳 (1-3%)
        if atr_pct < 0.5:
            score = 30  # 波动太小, 没空间
        elif atr_pct < 1.5:
            score = 70  # 适中波动
        elif atr_pct < 3.0:
            score = 60  # 可接受
        elif atr_pct < 5.0:
            score = 40  # 偏高
        else:
            score = 20  # 过高风险

        return self._make_score(
            score, "LONG",
            f"ATR={atr_pct:.2f}% (止损距={atr_pct*self._multiplier:.2f}%)"
        )

    def calc_stop_distance(self, symbol: str, cache) -> float:
        """返回建议的止损距禈 (价格百分比)."""
        klines = cache.get_klines(symbol, self._interval, limit=self._period + 10)
        if len(klines) < self._period + 1:
            return 2.0  # 默认 2%
        atr = self._calc_atr(klines)
        if atr <= 0:
            return 2.0
        return atr / klines[-1].close * 100 * self._multiplier

    def _calc_atr(self, klines) -> float:
        """计算 Average True Range."""
        if len(klines) < 2:
            return 0.0
        trs = []
        for i in range(1, len(klines)):
            high = klines[i].high
            low = klines[i].low
            prev_close = klines[i - 1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        if len(trs) < self._period:
            return sum(trs) / len(trs)
        return sum(trs[-self._period:]) / self._period


register_factor("atr", ATRFactor)
