"""成交量异动因子."""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class VolumeFactor(FactorBase):
    """成交量异动评分.

    当前量/均量 比值越大 → 信号越强.
    方向由价格涨跌决定.
    """

    def __init__(self, name: str = "volume", weight: float = 0.10, **params) -> None:
        super().__init__(name, weight, **params)

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        vol_ratio = candidate.volume_ratio

        if vol_ratio >= 4.0:
            score = 100
        elif vol_ratio >= 3.0:
            score = 90
        elif vol_ratio >= 2.0:
            score = 70
        elif vol_ratio >= 1.5:
            score = 50
        elif vol_ratio >= 1.0:
            score = 30
        else:
            score = 10

        direction = "LONG" if candidate.change_24h_pct > 0 else "SHORT"
        return self._make_score(score, direction, f"量比={vol_ratio:.1f}x (24h变化{candidate.change_24h_pct:+.1f}%)")


register_factor("volume", VolumeFactor)
