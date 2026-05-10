"""Dual moving average crossover strategy example.

Fast MA crosses above Slow MA → OPEN_LONG
Fast MA crosses below Slow MA → CLOSE_LONG + OPEN_SHORT
"""

from __future__ import annotations

from collections import deque

from cryptopilot.market.types import KlineData, TickerData
from cryptopilot.strategy.base import StrategyBase, Signal


class MACrossoverStrategy(StrategyBase):
    """Simple dual-MA crossover strategy.

    Parameters:
        fast_ma (int): Fast moving average period (default 7)
        slow_ma (int): Slow moving average period (default 25)
        use_close_only (bool): Only trade on closed bars (default True)
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._prices: deque[float] = deque(maxlen=200)
        self._fast_ma_val: float = 0.0
        self._slow_ma_val: float = 0.0
        self._prev_fast: float = 0.0
        self._prev_slow: float = 0.0
        self._last_kline_ts: int = 0

    async def on_init(self) -> None:
        fast = self.parameters.get("fast_ma", 7)
        slow = self.parameters.get("slow_ma", 25)
        self.logger.info(f"Initializing MA Crossover: fast={fast} slow={slow}")

        # Preload recent klines for indicator warmup
        interval = self.parameters.get("interval", "1m")
        klines = self.get_klines(interval, limit=slow + 50)
        for k in klines:
            self._prices.append(k.close)
            self._calculate_mas()

        if self._prices:
            self.logger.info(
                f"Preloaded {len(klines)} klines — "
                f"fast_ma={self._fast_ma_val:.4f} slow_ma={self._slow_ma_val:.4f}"
            )

    async def on_kline(self, kline: KlineData) -> None:
        # Only process new candles
        if kline.open_time == self._last_kline_ts:
            self._prices[-1] = kline.close  # update last entry in-place
        else:
            self._last_kline_ts = kline.open_time
            self._prices.append(kline.close)

        self._calculate_mas()

    async def on_signal(self) -> Signal | None:
        use_close_only = self.parameters.get("use_close_only", True)
        if use_close_only and not (self._prices and True):
            return None

        slow = self.parameters.get("slow_ma", 25)
        if len(self._prices) < slow:
            return None

        prev_fast, self._prev_fast = self._prev_fast, self._fast_ma_val
        prev_slow, self._prev_slow = self._prev_slow, self._slow_ma_val

        pos = self.get_position()
        has_pos = pos and abs(pos.get("qty", 0)) > 0

        # Bullish crossover: fast crosses above slow
        if prev_fast <= prev_slow and self._fast_ma_val > self._slow_ma_val:
            if has_pos:
                # Close short, open long
                return Signal(
                    strategy_id=self.strategy_id,
                    symbol=self.symbol,
                    action="OPEN_LONG",
                    order_type="MARKET",
                    comment=f"MA Crossover: fast({self._fast_ma_val:.4f}) > slow({self._slow_ma_val:.4f})",
                )
            return Signal(
                strategy_id=self.strategy_id,
                symbol=self.symbol,
                action="OPEN_LONG",
                order_type="MARKET",
                comment=f"MA Crossover: fast({self._fast_ma_val:.4f}) > slow({self._slow_ma_val:.4f})",
            )

        # Bearish crossover: fast crosses below slow
        if prev_fast >= prev_slow and self._fast_ma_val < self._slow_ma_val:
            if has_pos:
                return Signal(
                    strategy_id=self.strategy_id,
                    symbol=self.symbol,
                    action="CLOSE_SHORT",
                    order_type="MARKET",
                    comment=f"MA Crossunder: fast({self._fast_ma_val:.4f}) < slow({self._slow_ma_val:.4f})",
                )
            return Signal(
                strategy_id=self.strategy_id,
                symbol=self.symbol,
                action="CLOSE_LONG",
                order_type="MARKET",
                comment=f"MA Crossunder: fast({self._fast_ma_val:.4f}) < slow({self._slow_ma_val:.4f})",
            )

        return None

    def _calculate_mas(self) -> None:
        fast_p = self.parameters.get("fast_ma", 7)
        slow_p = self.parameters.get("slow_ma", 25)
        prices = list(self._prices)

        self._prev_fast = self._fast_ma_val
        self._prev_slow = self._slow_ma_val

        if len(prices) >= fast_p:
            self._fast_ma_val = sum(prices[-fast_p:]) / fast_p
        if len(prices) >= slow_p:
            self._slow_ma_val = sum(prices[-slow_p:]) / slow_p
