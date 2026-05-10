"""暗流复合因子 — 结合 OI + 资金费率检测隐藏的吸筹/派发行为.

Dark Flow 定义 (基于 V1 逻辑):
  主信号: OI 上升 + 价格横盘 + 资金费率为负 → 暗流吸筹 (强烈做多)
  副信号: OI 上升 + 价格横盘 + 资金费率偏高 → 暗流派发 (做空预警)
  弱信号: OI 上升 + 价格横盘 (费率中性) → 中性暗流 (关注)

三重确认逻辑:
  1. OI 维度: 1h 骤升 (≥5%) 或 24h 单调上升
  2. 价格维度: 24h 变化在 ±0.5% 以内 (横盘)
  3. 费率维度: 负费率 (空头付费) 或 极端正费率 (多头拥挤)
"""

from __future__ import annotations

import time

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class DarkFlowFactor(FactorBase):
    """暗流复合因子 — OI + 价格 + 费率 三维度确认.

    暗流 = 大户在不惊动价格的情况下建立仓位。
    OI 持续上升但价格不动 → 有资金在默默吸筹/派发。
    配合费率方向可判断多空意图。
    """

    # ---- 可调参数 ----
    SURGE_THRESHOLD: float = 5.0          # OI 1h 骤升阈值 (%)
    PRICE_FLAT_MAX: float = 0.5           # 价格横盘判定: |Δprice| < 此值 (%)
    NEGATIVE_FUNDING_LEVEL: float = -0.0001  # 负费率信号阈值
    HIGH_POSITIVE_FUNDING: float = 0.001   # 高正费率阈值 (0.1%)
    STRONG_SIGNAL_BONUS: float = 6.0      # 强暗流加分
    WEAK_SIGNAL_BONUS: float = 3.0        # 弱暗流加分
    BONUS_CAP: float = 10.0               # 总加分上限
    BONUS_DIVISOR: float = 300.0          # 乘法除数

    # 信号等级
    SIGNAL_STRONG = "dark_flow_strong"    # 三重确认
    SIGNAL_WEAK = "dark_flow_weak"        # 双重确认 (OI + price, 费率中性)
    SIGNAL_DISTRIBUTION = "dark_flow_distribution"  # 暗流派发

    def __init__(self, name: str = "dark_flow", weight: float = 0.15, **params) -> None:
        super().__init__(name, weight, **params)
        if "surge_threshold" in params:
            self.SURGE_THRESHOLD = float(params["surge_threshold"])
        if "price_flat_max" in params:
            self.PRICE_FLAT_MAX = float(params["price_flat_max"])
        if "strong_signal_bonus" in params:
            self.STRONG_SIGNAL_BONUS = float(params["strong_signal_bonus"])
        if "weak_signal_bonus" in params:
            self.WEAK_SIGNAL_BONUS = float(params["weak_signal_bonus"])
        if "bonus_cap" in params:
            self.BONUS_CAP = float(params["bonus_cap"])

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        symbol = candidate.symbol
        price_change = candidate.change_24h_pct
        funding_rate = candidate.funding_rate

        # ================================================================
        # 维度1: OI 状态检测
        # ================================================================
        oi_rising = False
        oi_surge = False
        oi_monotonic = False
        oi_1h_pct = 0.0

        # 1a. Candidate 自带 OI 变化
        if candidate.oi_change_pct > 0.5:
            oi_rising = True

        # 1b. OI 1h 骤升
        try:
            oi_1h_pct = cache.get_oi_change_pct(symbol, 3600.0)
        except Exception:
            oi_1h_pct = 0.0

        if oi_1h_pct >= self.SURGE_THRESHOLD:
            oi_surge = True
            oi_rising = True

        # 1c. OI 24h 单调上升
        try:
            oi_history = cache.get_oi_history(symbol)
        except AttributeError:
            oi_history = []

        if oi_history and len(oi_history) >= 8:
            now = time.time()
            cutoff = now - 86400
            recent = [(ts, val) for ts, val in oi_history if ts >= cutoff]
            if len(recent) < 8:
                recent = oi_history
            values = [v for _, v in recent]
            segments = self._segment_values(values, 4)
            if len(segments) >= 2:
                oi_monotonic = all(
                    segments[i + 1] >= segments[i] for i in range(len(segments) - 1)
                )
                if oi_monotonic:
                    oi_rising = True

        # ================================================================
        # 维度2: 价格横盘判定
        # ================================================================
        price_flat = abs(price_change) < self.PRICE_FLAT_MAX

        # ================================================================
        # 维度3: 资金费率方向
        # ================================================================
        funding_negative = funding_rate < self.NEGATIVE_FUNDING_LEVEL
        funding_high_positive = funding_rate > self.HIGH_POSITIVE_FUNDING

        # ================================================================
        # 信号合成
        # ================================================================
        if not oi_rising or not price_flat:
            # 暗流条件不满足
            fs = self._make_score(
                10, "NEUTRAL",
                f"暗流未触发 (OI↑={oi_rising}, 价平={price_flat})"
            )
            fs.bonus_breakdown = []
            fs.special_signal = ""
            return fs

        # OI 上升 + 价格横盘 → 基础暗流确认
        total_bonus = 0.0
        bonus_breakdown: list[str] = []
        signal_level = ""
        direction = "NEUTRAL"
        detail = ""

        oi_desc = f"OI1h{oi_1h_pct:+.1f}%" if oi_surge else "OI↑"

        if funding_negative:
            # ★★★ 强暗流吸筹: OI↑ + 价平 + 费率负 → 强烈做多
            signal_level = self.SIGNAL_STRONG
            direction = "LONG"
            total_bonus += self.STRONG_SIGNAL_BONUS
            bonus_breakdown.append(
                f"暗流吸筹+{self.STRONG_SIGNAL_BONUS:.0f}"
                f"({oi_desc}, 费率{funding_rate*100:+.4f}%)"
            )
            detail = (
                f"🔥 暗流吸筹: OI上升+价平+负费率 "
                f"(OI1h{oi_1h_pct:+.1f}%, 费率{funding_rate*100:+.4f}%) → 强烈做多"
            )

        elif funding_high_positive:
            # ★★ 暗流派发: OI↑ + 价平 + 费率极高 → 做空预警
            signal_level = self.SIGNAL_DISTRIBUTION
            direction = "SHORT"
            total_bonus += self.STRONG_SIGNAL_BONUS * 0.7
            bonus_breakdown.append(
                f"暗流派发+{self.STRONG_SIGNAL_BONUS*0.7:.0f}"
                f"({oi_desc}, 费率{funding_rate*100:+.4f}%)"
            )
            detail = (
                f"⚠️ 暗流派发: OI上升+价平+高费率 "
                f"(OI1h{oi_1h_pct:+.1f}%, 费率{funding_rate*100:+.4f}%) → 做空预警"
            )

        else:
            # ★ 弱暗流: OI↑ + 价平, 费率中性 → 观望偏多
            signal_level = self.SIGNAL_WEAK
            direction = "LONG"
            total_bonus += self.WEAK_SIGNAL_BONUS
            bonus_breakdown.append(
                f"暗流关注+{self.WEAK_SIGNAL_BONUS:.0f}({oi_desc})"
            )
            detail = (
                f"👁 暗流关注: OI上升+价平 "
                f"(OI1h{oi_1h_pct:+.1f}%, 费率{funding_rate*100:+.4f}%) → 偏多关注"
            )

        # 陡升额外加分
        if oi_surge:
            surge_extra = 2.0
            total_bonus += surge_extra
            bonus_breakdown.append(f"OI骤升加码+{surge_extra:.0f}")

        # ================================================================
        # 加分应用
        # ================================================================
        total_bonus = min(total_bonus, self.BONUS_CAP)
        # 基础分: 暗流确认即给 50 分
        base_score = 50.0
        multiplier = 1.0 + total_bonus / self.BONUS_DIVISOR
        final_score = self._clamp(base_score * multiplier, 0, 100)

        fs = self._make_score(final_score, direction, detail)
        fs.bonus_breakdown = bonus_breakdown
        fs.special_signal = signal_level
        return fs

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _segment_values(values: list[float], n: int) -> list[float]:
        """将列表等分为 n 段, 返回各段均值。"""
        if n <= 0 or not values:
            return []
        total = len(values)
        seg_len = max(1, total // n)
        segments: list[float] = []
        for i in range(n):
            start = i * seg_len
            chunk = values[start:start + seg_len] if i < n - 1 else values[start:]
            if chunk:
                segments.append(sum(chunk) / len(chunk))
        return segments


register_factor("dark_flow", DarkFlowFactor)
