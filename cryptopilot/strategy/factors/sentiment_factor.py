"""市场情绪因子 — 基于强平数据的多空比."""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class SentimentFactor(FactorBase):
    """多空强平比评分.

    ratio = BUY强平 / SELL强平
    >2.0 → 多方被大量强平 → 卖压释放 → 可能反弹 LONG
    <0.5 → 空方被大量强平 → 买压释放 → 可能回落 SHORT
    """

    def __init__(self, name: str = "sentiment", weight: float = 0.15, **params) -> None:
        super().__init__(name, weight, **params)
        self._window = params.get("window_seconds", 3600)

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        sym = candidate.symbol
        liq_ratio = cache.get_liquidation_ratio(sym)
        liq_counts = cache.get_liquidation_count(sym)
        total_liq = liq_counts.get("BUY", 0) + liq_counts.get("SELL", 0)

        if total_liq < 3:
            return self._make_score(30, "NEUTRAL", f"强平数据不足 (共{total_liq}笔)")

        if liq_ratio > 3.0:
            score = self._clamp(liq_ratio * 25, 0, 100)
            return self._make_score(score, "LONG",
                f"多空强平比={liq_ratio:.1f} (多{liq_counts['BUY']}/空{liq_counts['SELL']}) → 空方衰竭")
        if liq_ratio > 1.8:
            score = self._clamp(liq_ratio * 20, 0, 100)
            return self._make_score(score, "LONG",
                f"强平比偏高={liq_ratio:.1f} → 偏多")
        if liq_ratio < 0.3:
            score = self._clamp((1/liq_ratio) * 15, 0, 100)
            return self._make_score(score, "SHORT",
                f"多空强平比={liq_ratio:.1f} → 多方衰竭")
        if liq_ratio < 0.6:
            score = self._clamp((1/liq_ratio) * 10, 0, 100)
            return self._make_score(score, "SHORT",
                f"强平比偏低={liq_ratio:.1f} → 偏空")

        return self._make_score(30, "NEUTRAL", f"强平平衡 (比={liq_ratio:.1f})")


register_factor("sentiment", SentimentFactor)
