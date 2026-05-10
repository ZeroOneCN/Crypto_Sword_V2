"""MA 双均线交叉因子."""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class MAFactor(FactorBase):
    """快慢均线交叉评分.

    快线上穿慢线 → LONG; 快线下穿 → SHORT.
    """

    def __init__(self, name: str = "ma", weight: float = 0.15, **params) -> None:
        super().__init__(name, weight, **params)
        self._fast = params.get("fast", 7)
        self._slow = params.get("slow", 25)
        self._interval = params.get("interval", "1m")
        self._prev_fast_val: dict[str, float] = {}
        self._prev_slow_val: dict[str, float] = {}

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        sym = candidate.symbol
        klines = cache.get_klines(sym, self._interval, limit=self._slow + 10)
        if len(klines) < self._slow:
            return self._make_score(0, "NEUTRAL", "K线数据不足")

        closes = [k.close for k in klines]
        fast_val = self._ma(closes, self._fast)
        slow_val = self._ma(closes, self._slow)
        prev_fast = self._prev_fast_val.get(sym, fast_val)
        prev_slow = self._prev_slow_val.get(sym, slow_val)
        self._prev_fast_val[sym] = fast_val
        self._prev_slow_val[sym] = slow_val

        if fast_val <= 0 or slow_val <= 0:
            return self._make_score(0, "NEUTRAL", "均线未就绪")

        # 金叉
        if prev_fast <= prev_slow and fast_val > slow_val:
            strength = min((fast_val - slow_val) / slow_val * 1000, 100)
            return self._make_score(strength, "LONG", f"金叉 FA={fast_val:.2f} > SA={slow_val:.2f}")

        # 死叉
        if prev_fast >= prev_slow and fast_val < slow_val:
            strength = min((slow_val - fast_val) / fast_val * 1000, 100)
            return self._make_score(strength, "SHORT", f"死叉 FA={fast_val:.2f} < SA={slow_val:.2f}")

        # 均线多头排列
        if fast_val > slow_val:
            return self._make_score(40, "LONG", f"多头排列 FA({fast_val:.2f}) > SA({slow_val:.2f})")

        return self._make_score(40, "SHORT", f"空头排列 FA({fast_val:.2f}) < SA({slow_val:.2f})")


register_factor("ma", MAFactor)
