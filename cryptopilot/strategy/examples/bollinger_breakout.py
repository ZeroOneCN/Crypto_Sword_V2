"""Bollinger Bands breakout strategy.

Price closes above upper band → breakout buy
Price closes below lower band → breakout sell
"""

from __future__ import annotations

from collections import deque
import math

from cryptopilot.market.types import KlineData
from cryptopilot.strategy.base import StrategyBase, Signal


class BollingerBreakoutStrategy(StrategyBase):
    """Bollinger Bands breakout strategy.

    Parameters:
        period (int): MA period for middle band (default 20)
        num_std (float): Standard deviation multiplier (default 2.0)
        require_close (bool): Only signal on closed bars (default True)
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._prices: deque[float] = deque(maxlen=500)
        self._last_ts: int = 0
        self._upper: float = 0.0
        self._middle: float = 0.0
        self._lower: float = 0.0
        self._prev_upper: float = 0.0
        self._prev_lower: float = 0.0

    async def on_init(self) -> None:
        period = self.parameters.get("period", 20)
        num_std = self.parameters.get("num_std", 2.0)
        self.logger.info(f"Initializing Bollinger: period={period} std={num_std}")

        interval = self.parameters.get("interval", "5m")
        klines = self.get_klines(interval, limit=period * 3)
        for k in klines:
            self._prices.append(k.close)
        self._calc_bands()
        self.logger.info(
            f"Bollinger ready: upper={self._upper:.4f} mid={self._middle:.4f} lower={self._lower:.4f}"
        )

    async def on_kline(self, kline: KlineData) -> None:
        if self._prices and self._last_ts == kline.open_time:
            self._prices[-1] = kline.close
        else:
            self._last_ts = kline.open_time
            self._prices.append(kline.close)
        self._calc_bands()

    async def on_signal(self) -> Signal | None:
        period = self.parameters.get("period", 20)
        require_close = self.parameters.get("require_close", True)
        prices = list(self._prices)

        if len(prices) < period + 1:
            return None

        prev_close = prices[-2]
        current_close = prices[-1]

        has_pos = self.has_position()

        # Breakout above upper band
        if prev_close <= self._upper and current_close > self._upper:
            if has_pos:
                return Signal(
                    strategy_id=self.strategy_id,
                    symbol=self.symbol,
                    action="CLOSE_SHORT",
                    order_type="MARKET",
                    comment=f"Bollinger breakout UP: {current_close:.4f} > upper={self._upper:.4f}",
                )
            return Signal(
                strategy_id=self.strategy_id,
                symbol=self.symbol,
                action="OPEN_LONG",
                order_type="MARKET",
                comment=f"Bollinger breakout UP: {current_close:.4f} > upper={self._upper:.4f}",
            )

        # Breakdown below lower band
        if prev_close >= self._lower and current_close < self._lower:
            if has_pos:
                return Signal(
                    strategy_id=self.strategy_id,
                    symbol=self.symbol,
                    action="CLOSE_LONG",
                    order_type="MARKET",
                    comment=f"Bollinger breakdown DOWN: {current_close:.4f} < lower={self._lower:.4f}",
                )
            return Signal(
                strategy_id=self.strategy_id,
                symbol=self.symbol,
                action="OPEN_SHORT",
                order_type="MARKET",
                comment=f"Bollinger breakdown DOWN: {current_close:.4f} < lower={self._lower:.4f}",
            )

        return None

    def _calc_bands(self) -> None:
        period = self.parameters.get("period", 20)
        num_std = self.parameters.get("num_std", 2.0)
        prices = list(self._prices)

        if len(prices) < period:
            return

        self._prev_upper = self._upper
        self._prev_lower = self._lower

        window = prices[-period:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        std = math.sqrt(variance)

        self._middle = mean
        self._upper = mean + num_std * std
        self._lower = mean - num_std * std
