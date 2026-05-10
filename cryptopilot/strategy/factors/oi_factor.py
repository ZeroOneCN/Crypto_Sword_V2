"""OI 持仓量变化因子."""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class OIFactor(FactorBase):
    """OI 变化 + 价格方向确认评分.

    OI↑+价↑ → 多头加仓 → LONG
    OI↑+价↓ → 空头加仓 → SHORT
    OI↓+价↑ → 空头平仓 → 偏 LONG
    OI↓+价↓ → 多头平仓 → 偏 SHORT
    """

    def __init__(self, name: str = "oi", weight: float = 0.20, **params) -> None:
        super().__init__(name, weight, **params)

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        oi_change = candidate.oi_change_pct
        price_change = candidate.change_24h_pct

        abs_oi = abs(oi_change)
        strength = self._clamp(abs_oi / 10.0, 0, 1) * 100

        if oi_change > 1.0 and price_change > 0.5:
            return self._make_score(strength, "LONG",
                f"OI增+价涨 (OI{oi_change:+.1f}%, 价{price_change:+.1f}%) → 多头加仓")
        if oi_change > 1.0 and price_change < -0.5:
            return self._make_score(strength, "SHORT",
                f"OI增+价跌 (OI{oi_change:+.1f}%, 价{price_change:+.1f}%) → 空头加仓")
        if oi_change < -1.0 and price_change > 0.5:
            return self._make_score(strength * 0.6, "LONG",
                f"OI减+价涨 (OI{oi_change:+.1f}%, 价{price_change:+.1f}%) → 空头平仓")
        if oi_change < -1.0 and price_change < -0.5:
            return self._make_score(strength * 0.6, "SHORT",
                f"OI减+价跌 (OI{oi_change:+.1f}%, 价{price_change:+.1f}%) → 多头平仓")

        return self._make_score(20, "NEUTRAL", f"OI无显著变化 ({oi_change:+.1f}%)")


register_factor("oi", OIFactor)
