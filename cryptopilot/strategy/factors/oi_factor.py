"""OI 持仓量变化因子 — 增强版含暗流检测.

基于 V1 OiFundingService 逻辑升级：
  - OI 1h 骤升检测
  - OI 24h 趋势分析 (4段单调上升)
  - OI 暗流 (OI↑ + 价平 → 吸筹信号)
  - 乘法倍数加分系统 (score × (1 + bonus/300))
"""

from __future__ import annotations

import time
from collections import deque

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class OIFactor(FactorBase):
    """OI 变化 + 价格方向确认评分 (增强版).

    OI↑+价↑ → 多头加仓 → LONG
    OI↑+价↓ → 空头加仓 → SHORT
    OI↓+价↑ → 空头平仓 → 偏 LONG
    OI↓+价↓ → 多头平仓 → 偏 SHORT

    增强信号:
      OI 1h 骤升 (≥5%)        → 加分 + 特殊标记
      OI 24h 单调上升 (4段)    → 加分, 趋势确认
      OI 暗流 (OI↑ + 价平)     → 吸筹/派发预警
    """

    # ---- 可调参数 ----
    SURGE_THRESHOLD_PCT: float = 5.0       # OI 1h 骤升阈值 (%)
    SURGE_BONUS: float = 4.0               # 骤升加分
    MONOTONIC_BONUS: float = 3.0           # 单调上升加分
    DARK_FLOW_BONUS: float = 5.0           # 暗流加分
    PRICE_FLAT_THRESHOLD: float = 0.5      # 价平判定: |价格变化| < 此值 (%)
    BONUS_CAP: float = 8.0                 # 总加分上限
    BONUS_DIVISOR: float = 300.0           # 乘法除数 (V1 标准)
    SEGMENT_COUNT: int = 4                 # 24h 分段数

    def __init__(self, name: str = "oi", weight: float = 0.20, **params) -> None:
        super().__init__(name, weight, **params)
        # 覆盖参数
        if "surge_threshold_pct" in params:
            self.SURGE_THRESHOLD_PCT = float(params["surge_threshold_pct"])
        if "surge_bonus" in params:
            self.SURGE_BONUS = float(params["surge_bonus"])
        if "monotonic_bonus" in params:
            self.MONOTONIC_BONUS = float(params["monotonic_bonus"])
        if "dark_flow_bonus" in params:
            self.DARK_FLOW_BONUS = float(params["dark_flow_bonus"])
        if "price_flat_threshold" in params:
            self.PRICE_FLAT_THRESHOLD = float(params["price_flat_threshold"])
        if "bonus_cap" in params:
            self.BONUS_CAP = float(params["bonus_cap"])

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        symbol = candidate.symbol
        oi_change = candidate.oi_change_pct
        price_change = candidate.change_24h_pct

        # ================================================================
        # Phase 1: 基础方向评分 (保持向后兼容)
        # ================================================================
        abs_oi = abs(oi_change)
        strength = self._clamp(abs_oi / 10.0, 0, 1) * 100

        base_direction = "NEUTRAL"
        base_detail = ""

        if oi_change > 1.0 and price_change > 0.5:
            base_direction = "LONG"
            base_detail = (
                f"OI增+价涨 (OI{oi_change:+.1f}%, 价{price_change:+.1f}%) → 多头加仓"
            )
        elif oi_change > 1.0 and price_change < -0.5:
            base_direction = "SHORT"
            base_detail = (
                f"OI增+价跌 (OI{oi_change:+.1f}%, 价{price_change:+.1f}%) → 空头加仓"
            )
            strength *= 0.9  # 空头信号略打折
        elif oi_change < -1.0 and price_change > 0.5:
            base_direction = "LONG"
            base_detail = (
                f"OI减+价涨 (OI{oi_change:+.1f}%, 价{price_change:+.1f}%) → 空头平仓"
            )
            strength *= 0.6
        elif oi_change < -1.0 and price_change < -0.5:
            base_direction = "SHORT"
            base_detail = (
                f"OI减+价跌 (OI{oi_change:+.1f}%, 价{price_change:+.1f}%) → 多头平仓"
            )
            strength *= 0.6
        else:
            base_direction = "NEUTRAL"
            strength = 20.0
            base_detail = f"OI无显著变化 ({oi_change:+.1f}%)"

        # ================================================================
        # Phase 2: 增强信号检测
        # ================================================================
        total_bonus = 0.0
        bonus_breakdown: list[str] = []
        special_signal = ""

        # 2a. OI 1h 骤升检测
        oi_1h_surge, oi_1h_pct = self._detect_1h_surge(symbol, cache)
        if oi_1h_surge:
            total_bonus += self.SURGE_BONUS
            bonus_breakdown.append(f"OI1h骤升+{self.SURGE_BONUS:.0f}({oi_1h_pct:+.1f}%)")
            if not special_signal:
                special_signal = "oi_surge"

        # 2b. OI 24h 趋势分析 (4段单调上升)
        oi_monotonic, oi_segments = self._analyze_oi_trend(symbol, cache)
        if oi_monotonic:
            total_bonus += self.MONOTONIC_BONUS
            bonus_breakdown.append(f"OI24h单调升+{self.MONOTONIC_BONUS:.0f}")
            if not special_signal:
                special_signal = "oi_monotonic_up"

        # 2c. OI 暗流检测 — OI rising + price flat
        oi_rising = oi_change > 0.5 or oi_monotonic or oi_1h_surge
        price_flat = abs(price_change) < self.PRICE_FLAT_THRESHOLD
        dark_flow_detected = oi_rising and price_flat

        if dark_flow_detected:
            total_bonus += self.DARK_FLOW_BONUS
            direction_hint = "吸筹" if price_change >= 0 else "派发"
            bonus_breakdown.append(
                f"OI暗流+{self.DARK_FLOW_BONUS:.0f}({direction_hint})"
            )
            special_signal = "dark_flow"

        # ================================================================
        # Phase 3: 乘法加分 (V1 style: score × (1 + bonus/300))
        # ================================================================
        total_bonus = min(total_bonus, self.BONUS_CAP)
        multiplier = 1.0 + total_bonus / self.BONUS_DIVISOR
        final_score = self._clamp(strength * multiplier, 0, 100)

        # 暗流信号可能改变方向 (OI↑+价平 → 偏多)
        final_direction = base_direction
        if dark_flow_detected and base_direction == "NEUTRAL":
            final_direction = "LONG" if price_change >= 0 else "SHORT"

        # 构建 detail
        detail_parts = [base_detail]
        if bonus_breakdown:
            detail_parts.append(" | 加分: " + ", ".join(bonus_breakdown))
        final_detail = "".join(detail_parts)

        fs = self._make_score(final_score, final_direction, final_detail)
        fs.bonus_breakdown = bonus_breakdown
        fs.special_signal = special_signal
        return fs

    # ------------------------------------------------------------------
    # 检测方法
    # ------------------------------------------------------------------

    def _detect_1h_surge(self, symbol: str, cache) -> tuple[bool, float]:
        """检测 OI 最近 1 小时是否骤升 ≥5%.

        使用 cache 的 get_oi_change_pct 直接计算 1h 变化率。
        """
        try:
            oi_1h_pct = cache.get_oi_change_pct(symbol, 3600.0)
        except Exception:
            return False, 0.0

        if oi_1h_pct >= self.SURGE_THRESHOLD_PCT:
            return True, oi_1h_pct
        return False, oi_1h_pct

    def _analyze_oi_trend(self, symbol: str, cache) -> tuple[bool, list[float]]:
        """24h OI 趋势分析: 分为 N 段, 检测是否单调上升。

        Returns:
            (is_monotonic_up, [seg1_avg, seg2_avg, seg3_avg, seg4_avg])
        """
        try:
            oi_history = cache.get_oi_history(symbol)
        except AttributeError:
            # 如果 cache 没有 get_oi_history, 用 get_oi_change_pct 降级
            return self._fallback_trend(symbol, cache)

        if not oi_history or len(oi_history) < 8:
            return False, []

        now = time.time()
        cutoff = now - 86400  # 24h ago

        # 过滤 24h 内的数据点
        recent = [(ts, val) for ts, val in oi_history if ts >= cutoff]
        if len(recent) < 8:
            # 数据不足, 用全部数据
            recent = oi_history
        if len(recent) < 8:
            return False, []

        values = [val for _, val in recent]
        segments = self._segment_values(values, self.SEGMENT_COUNT)

        if len(segments) < 2:
            return False, segments

        # 检测单调上升: 每一段 ≥ 前一段
        monotonic = all(
            segments[i + 1] >= segments[i] for i in range(len(segments) - 1)
        )

        return monotonic, [round(s, 2) for s in segments]

    def _fallback_trend(self, symbol: str, cache) -> tuple[bool, list[float]]:
        """降级趋势检测: 使用多个时间窗口的变化率近似。"""
        try:
            oi_24h = cache.get_oi_change_pct(symbol, 86400.0)
            oi_12h = cache.get_oi_change_pct(symbol, 43200.0)
            oi_6h = cache.get_oi_change_pct(symbol, 21600.0)
            oi_1h = cache.get_oi_change_pct(symbol, 3600.0)
        except Exception:
            return False, []

        # 如果各时间窗口的变化率逐渐放大 → 加速上升
        if (oi_1h > 0 and oi_6h > 0 and oi_12h > 0 and oi_24h > 0
                and oi_1h >= oi_6h * 0.3):
            return True, []
        return False, []

    @staticmethod
    def _segment_values(values: list[float], n: int) -> list[float]:
        """将 values 分为 n 段, 返回每段的均值。"""
        if n <= 0 or not values:
            return []
        total = len(values)
        seg_len = max(1, total // n)
        segments: list[float] = []
        for i in range(n):
            start = i * seg_len
            if i == n - 1:
                chunk = values[start:]
            else:
                chunk = values[start:start + seg_len]
            if chunk:
                segments.append(sum(chunk) / len(chunk))
        return segments


register_factor("oi", OIFactor)
