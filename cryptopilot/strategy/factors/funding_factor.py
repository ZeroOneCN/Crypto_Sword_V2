"""资金费率因子 — 极值反指信号."""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class FundingFactor(FactorBase):
    """资金费率极值评分.

    极度正费率 → 多头拥挤需支付高额费率 → 做空(反指)
    极度负费率 → 空头拥挤可收高额费率 → 做多(反指)
    """

    def __init__(self, name: str = "funding", weight: float = 0.20, **params) -> None:
        super().__init__(name, weight, **params)

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        rate = candidate.funding_rate
        rate_pct = rate * 100  # 转为百分比

        # 正费率阈值: >0.1% 即多头拥挤
        if rate_pct > 0.2:
            score = self._clamp(rate_pct / 0.5 * 100, 0, 100)
            return self._make_score(score, "SHORT", f"多头拥挤 费率={rate_pct:.4f}% → 做空")
        if rate_pct > 0.1:
            score = self._clamp(rate_pct / 0.3 * 100, 0, 100)
            return self._make_score(score, "SHORT", f"费率偏高 费率={rate_pct:.4f}% → 偏空")

        # 负费率阈值: <-0.05% 即空头拥挤
        if rate_pct < -0.1:
            score = self._clamp(abs(rate_pct) / 0.3 * 100, 0, 100)
            return self._make_score(score, "LONG", f"空头拥挤 费率={rate_pct:.4f}% → 做多")
        if rate_pct < -0.05:
            score = self._clamp(abs(rate_pct) / 0.15 * 100, 0, 100)
            return self._make_score(score, "LONG", f"费率偏低 费率={rate_pct:.4f}% → 偏多")

        return self._make_score(30, "NEUTRAL", f"费率正常 ({rate_pct:.4f}%)")


register_factor("funding", FundingFactor)
