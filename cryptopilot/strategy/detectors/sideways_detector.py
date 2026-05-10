"""横盘收筹检测器 — 检测长期横盘 + 低量的庄家收筹信号.

核心逻辑 (来自 connectfarm1 积累雷达):
  庄家拉盘前必须先收筹 →
  长期横盘 + 低成交量 = 收筹中 →
  OI 暴涨 = 大资金进场 = 即将拉盘
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from loguru import logger


@dataclass
class SidewaysResult:
    """横盘检测结果."""
    symbol: str
    sideways_days: int          # 当前横盘持续天数
    sideways_days_90d: int      # 近 90 天内最大横盘天数
    price_range_pct: float      # 横盘区间波动幅度 (%)
    volume_ratio: float         # 近期量 / 历史均量
    is_accumulating: bool       # 是否处于收筹状态
    score: float                # 横盘收筹评分 (0-100)
    detail: str = ""


class SidewaysDetector:
    """横盘收筹检测器.

    使用 4h K 线分析:
    - 高低点区间 < max_range_pct → 视为横盘
    - 当前量 < 历史均量 × 0.7 → 缩量
    - 横盘天数 > min_days → 收筹确认
    """

    def __init__(
        self,
        max_range_pct: float = 40.0,     # 横盘判定: 高低差 < 40%
        min_days: int = 30,               # 最少横盘天数
        volume_decline_threshold: float = 0.7,  # 缩量阈值
    ) -> None:
        self._max_range = max_range_pct
        self._min_days = min_days
        self._vol_threshold = volume_decline_threshold

    def detect(self, symbol: str, cache) -> SidewaysResult:
        """检测指定币种的横盘收筹状态.

        需要 4h K 线数据 (至少 180 根 = 30 天).
        """
        klines = cache.get_klines(symbol, "4h", limit=200)
        if len(klines) < 30:
            return SidewaysResult(
                symbol=symbol, sideways_days=0, sideways_days_90d=0,
                price_range_pct=0, volume_ratio=1.0,
                is_accumulating=False, score=0, detail="4h K线不足30根"
            )

        closes = [k.close for k in klines]
        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        volumes = [k.volume for k in klines]

        # 计算横盘天数 (从最近往前找, 直到波动超过阈值)
        sideways_count = 0
        current_high = highs[-1]
        current_low = lows[-1]

        for i in range(len(klines) - 1, -1, -1):
            ch = max(current_high, highs[i])
            cl = min(current_low, lows[i])
            rng_pct = (ch - cl) / cl * 100 if cl > 0 else 0
            if rng_pct <= self._max_range:
                sideways_count += 1
                current_high = ch
                current_low = cl
            else:
                break

        sideways_days = sideways_count * 4 // 24  # 4h K线 → 天数

        # 计算横盘区间波动幅度
        if len(closes) >= sideways_count and sideways_count > 0:
            window_closes = closes[-sideways_count:]
            window_highs = highs[-sideways_count:]
            window_lows = lows[-sideways_count:]
            price_range_pct = (max(window_highs) - min(window_lows)) / min(window_lows) * 100 if min(window_lows) > 0 else 0
        else:
            price_range_pct = 0

        # 成交量衰减比 (近期 vs 横盘前)
        if len(volumes) > sideways_count + 20 and sideways_count > 0:
            recent_vol = sum(volumes[-sideways_count:]) / max(sideways_count, 1)
            prior_vol = sum(volumes[-(sideways_count + 20):-sideways_count]) / 20 if sideways_count > 0 else recent_vol
            volume_ratio = recent_vol / prior_vol if prior_vol > 0 else 1.0
        else:
            volume_ratio = 1.0

        # 收筹判定: 横盘 > min_days 且 缩量
        is_accumulating = (sideways_days >= self._min_days and volume_ratio < self._vol_threshold)

        # 评分: 横盘天数 + 缩量程度 + 区间窄幅
        day_score = min(sideways_days / 120 * 50, 50)    # 横盘天数 → 最高 50
        vol_score = max(0, (1 - volume_ratio)) * 30      # 缩量 → 最高 30
        tight_score = max(0, (self._max_range - price_range_pct) / self._max_range * 20)  # 窄幅 → 最高 20
        score = day_score + vol_score + tight_score

        detail = (
            f"横盘={sideways_days}天 波幅={price_range_pct:.1f}% "
            f"量比={volume_ratio:.2f}x "
            f"{'[收筹中]' if is_accumulating else '[非收筹]'}"
        )

        return SidewaysResult(
            symbol=symbol,
            sideways_days=sideways_days,
            sideways_days_90d=sideways_days,  # simplified
            price_range_pct=round(price_range_pct, 1),
            volume_ratio=round(volume_ratio, 2),
            is_accumulating=is_accumulating,
            score=round(score, 1),
            detail=detail,
        )

    def oi_signal(
        self,
        sideways_result: SidewaysResult,
        oi_change_pct: float,
        price_change_pct: float,
    ) -> str:
        """OI × 价格矩阵信号解读 (connectfarm1 经典矩阵).

        返回: "dark_flow" / "longs_adding" / "shorts_adding" / "squeeze" / "liquidation" / "neutral"
        """
        oi_up = oi_change_pct > 2.0
        oi_down = oi_change_pct < -2.0
        price_up = price_change_pct > 1.0
        price_down = price_change_pct < -1.0
        price_flat = abs(price_change_pct) <= 1.0

        if oi_up and price_flat:
            return "dark_flow"     # ⚡ 暗流涌动 — 最佳埋伏时机
        if oi_up and price_up:
            return "longs_adding"  # 🟢 多头加仓
        if oi_up and price_down:
            return "shorts_adding" # 🔴 空头加仓
        if oi_down and price_up:
            return "squeeze"       # 💪 空头爆仓
        if oi_down and price_down:
            return "liquidation"   # 💨 多头平仓
        return "neutral"
