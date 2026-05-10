"""横盘收筹因子 — 长期横盘 + 缩量 = 庄家收筹信号.

connectfarm1 核心逻辑:
  横盘天数 > 120 天 → 满分
  横盘天数 > 60 天  → 70 分
  横盘天数 > 30 天  → 40 分
"""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate
from cryptopilot.strategy.detectors.sideways_detector import SidewaysDetector


class SidewaysFactor(FactorBase):
    """横盘收筹评分因子.

    检测横盘天数、波动范围、量能变化.
    结合 OI 变化判断是否处于收筹末期.
    """

    def __init__(self, name: str = "sideways", weight: float = 0.20, **params) -> None:
        super().__init__(name, weight, **params)
        self._detector = SidewaysDetector(
            max_range_pct=params.get("max_range_pct", 40.0),
            min_days=params.get("min_days", 30),
            volume_decline_threshold=params.get("volume_threshold", 0.7),
        )

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        result = self._detector.detect(candidate.symbol, cache)

        if result.sideways_days == 0:
            return self._make_score(0, "NEUTRAL", "无横盘数据")

        # 横盘天数评分 (connectfarm1 标准)
        if result.sideways_days >= 120:
            day_score = 100
            desc = "超长期横盘"
        elif result.sideways_days >= 90:
            day_score = 85
            desc = "长期横盘"
        elif result.sideways_days >= 60:
            day_score = 65
            desc = "中期横盘"
        elif result.sideways_days >= 30:
            day_score = 40
            desc = "短期横盘"
        else:
            day_score = 15
            desc = "轻度横盘"

        # 收筹加权: 缩量 + 窄幅 额外加分
        if result.is_accumulating:
            bonus = 20
            desc += " + 收筹确认"
        else:
            bonus = 0

        score = min(day_score + bonus, 100)

        # OI 确认: OI 上涨 + 价格不动 = 暗流 (最佳埋伏)
        oi_signal_type = self._detector.oi_signal(
            result, candidate.oi_change_pct, candidate.change_24h_pct
        )
        if oi_signal_type == "dark_flow":
            score = min(score + 15, 100)
            desc += " + 暗流"
        elif oi_signal_type == "longs_adding":
            score = min(score + 10, 100)
            desc += " + 多头加仓"

        return self._make_score(score, "LONG", f"{desc} ({result.detail})")


register_factor("sideways", SidewaysFactor)
