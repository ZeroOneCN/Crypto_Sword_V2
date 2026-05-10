"""资金费率因子 — 增强版含费率转向与温和负费率检测.

基于 V1 OiFundingService 逻辑升级：
  - 费率转负检测 (从 >=0 翻转为 <0 → 强做多信号)
  - 温和负费率加分 (-0.005% ≤ rate < 0 + OI 上升 → 蓄势吸筹)
  - 乘法倍数加分系统 (score × (1 + bonus/300))
  - 加分明细追踪 (bonus_breakdown)
"""

from __future__ import annotations

import time
from collections import deque

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class FundingFactor(FactorBase):
    """资金费率极值 + 转向 + 温和负费率评分 (增强版).

    极度正费率 → 多头拥挤需支付高额费率 → 做空(反指)
    极度负费率 → 空头拥挤可收高额费率 → 做多(反指)

    增强信号:
      费率转负 (≥0 → <0)            → 强做多 + 加分
      温和负费率 (-0.005%~0) + OI↑  → 蓄势吸筹 + 加分
    """

    # ---- 可调参数 ----
    TURN_BONUS: float = 4.0               # 费率转负加分
    MILD_NEGATIVE_BONUS: float = 3.0      # 温和负费率加分
    MILD_NEGATIVE_MIN: float = -0.0005    # 温和负费率下限 (-0.05%)
    MILD_NEGATIVE_MAX: float = -0.00005   # 温和负费率上限 (-0.005%)
    BONUS_CAP: float = 8.0                # 总加分上限
    BONUS_DIVISOR: float = 300.0          # 乘法除数 (V1 标准)
    SNAPSHOT_TTL: float = 3600.0          # 费率快照有效期 (秒)

    def __init__(self, name: str = "funding", weight: float = 0.20, **params) -> None:
        super().__init__(name, weight, **params)
        # 费率历史快照: {symbol: (timestamp, rate)}
        self._funding_snapshot: dict[str, tuple[float, float]] = {}

        if "turn_bonus" in params:
            self.TURN_BONUS = float(params["turn_bonus"])
        if "mild_negative_bonus" in params:
            self.MILD_NEGATIVE_BONUS = float(params["mild_negative_bonus"])
        if "mild_negative_min" in params:
            self.MILD_NEGATIVE_MIN = float(params["mild_negative_min"])
        if "mild_negative_max" in params:
            self.MILD_NEGATIVE_MAX = float(params["mild_negative_max"])
        if "bonus_cap" in params:
            self.BONUS_CAP = float(params["bonus_cap"])

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        symbol = candidate.symbol
        rate = candidate.funding_rate
        rate_pct = rate * 100  # 转为百分比

        # ================================================================
        # Phase 1: 基础极值评分 (保持向后兼容)
        # ================================================================
        base_direction = "NEUTRAL"
        base_score = 30.0
        base_detail = ""

        # 正费率: 多头拥挤 → 做空
        if rate_pct > 0.2:
            base_score = self._clamp(rate_pct / 0.5 * 100, 0, 100)
            base_direction = "SHORT"
            base_detail = f"多头拥挤 费率={rate_pct:.4f}% → 做空"
        elif rate_pct > 0.1:
            base_score = self._clamp(rate_pct / 0.3 * 100, 0, 100)
            base_direction = "SHORT"
            base_detail = f"费率偏高 费率={rate_pct:.4f}% → 偏空"

        # 负费率: 空头拥挤 → 做多
        elif rate_pct < -0.1:
            base_score = self._clamp(abs(rate_pct) / 0.3 * 100, 0, 100)
            base_direction = "LONG"
            base_detail = f"空头拥挤 费率={rate_pct:.4f}% → 做多"
        elif rate_pct < -0.05:
            base_score = self._clamp(abs(rate_pct) / 0.15 * 100, 0, 100)
            base_direction = "LONG"
            base_detail = f"费率偏低 费率={rate_pct:.4f}% → 偏多"
        else:
            base_detail = f"费率正常 ({rate_pct:.4f}%)"

        # ================================================================
        # Phase 2: 增强信号检测
        # ================================================================
        total_bonus = 0.0
        bonus_breakdown: list[str] = []
        special_signal = ""

        previous_rate = self._get_previous_funding(symbol)
        # 更新快照 (记录当前费率)
        self._update_snapshot(symbol, rate)

        # 2a. 费率转负检测 — 从 >=0 翻转为 <0
        turned_negative = (
            previous_rate is not None
            and previous_rate >= 0
            and rate < 0
        )
        if turned_negative:
            total_bonus += self.TURN_BONUS
            bonus_breakdown.append(
                f"费率转负+{self.TURN_BONUS:.0f} ({previous_rate*100:+.4f}%→{rate*100:+.4f}%)"
            )
            special_signal = "funding_turn_negative"
            # 转向信号强制偏多
            if base_direction == "NEUTRAL":
                base_direction = "LONG"
                base_score = max(base_score, 40.0)
                base_detail = (
                    f"费率转负 {previous_rate*100:+.4f}%→{rate*100:+.4f}% → 强做多"
                )

        # 2b. 温和负费率检测 — -0.005% ≤ rate < 0 且 OI 上升
        is_mild_negative = self.MILD_NEGATIVE_MIN <= rate <= self.MILD_NEGATIVE_MAX
        if is_mild_negative and not turned_negative:
            # 确认 OI 是否在上升
            oi_rising = self._is_oi_rising(symbol, cache)
            if oi_rising:
                total_bonus += self.MILD_NEGATIVE_BONUS
                bonus_breakdown.append(
                    f"温和负费率+{self.MILD_NEGATIVE_BONUS:.0f} "
                    f"({rate*100:+.4f}%, OI↑)"
                )
                if not special_signal:
                    special_signal = "mild_negative_accumulation"
                # 温和负费率 + OI 上升 → 暗示蓄势做多
                if base_direction == "NEUTRAL":
                    base_direction = "LONG"
                    base_score = max(base_score, 35.0)
                    base_detail = (
                        f"温和负费率 ({rate*100:.4f}%) + OI↑ → 蓄势吸筹"
                    )

        # ================================================================
        # Phase 3: 乘法加分 (V1 style)
        # ================================================================
        total_bonus = min(total_bonus, self.BONUS_CAP)
        multiplier = 1.0 + total_bonus / self.BONUS_DIVISOR
        final_score = self._clamp(base_score * multiplier, 0, 100)

        # 构建 detail
        detail_parts = [base_detail]
        if bonus_breakdown:
            detail_parts.append(" | 加分: " + ", ".join(bonus_breakdown))
        final_detail = "".join(detail_parts)

        fs = self._make_score(final_score, base_direction, final_detail)
        fs.bonus_breakdown = bonus_breakdown
        fs.special_signal = special_signal
        return fs

    # ------------------------------------------------------------------
    # 费率快照管理
    # ------------------------------------------------------------------

    def _get_previous_funding(self, symbol: str) -> float | None:
        """获取上一次记录的费率快照。过期返回 None。"""
        snapshot = self._funding_snapshot.get(symbol)
        if snapshot is None:
            return None
        ts, rate = snapshot
        if time.time() - ts > self.SNAPSHOT_TTL:
            return None
        return rate

    def _update_snapshot(self, symbol: str, rate: float) -> None:
        """更新费率快照。"""
        self._funding_snapshot[symbol] = (time.time(), rate)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _is_oi_rising(symbol: str, cache) -> bool:
        """检测 OI 是否在上升 (1h 变化率 > 0)。"""
        try:
            oi_1h = cache.get_oi_change_pct(symbol, 3600.0)
            return oi_1h > 0.5  # 至少 0.5% 才算上升
        except Exception:
            return False


register_factor("funding", FundingFactor)
