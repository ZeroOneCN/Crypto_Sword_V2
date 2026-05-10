"""RSI overbought/oversold reversal strategy.

RSI < oversold (default 30) → reversal buy signal
RSI > overbought (default 70) → reversal sell signal
"""

from __future__ import annotations

from collections import deque

from cryptopilot.market.types import KlineData
from cryptopilot.strategy.base import StrategyBase, Signal


class RSIStrategy(StrategyBase):
    """RSI reversal strategy.

    Parameters:
        period (int): RSI calculation period (default 14)
        oversold (float): Oversold threshold (default 30)
        overbought (float): Overbought threshold (default 70)
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._prices: deque[float] = deque(maxlen=500)
        self._rsi: float = 50.0
        self._prev_rsi: float = 50.0
        self._last_ts: int = 0

    async def on_init(self) -> None:
        period = self.parameters.get("period", 14)
        self.logger.info(
            f"Initializing RSI: period={period} "
            f"oversold={self.parameters.get('oversold', 30)} "
            f"overbought={self.parameters.get('overbought', 70)}"
        )
        interval = self.parameters.get("interval", "5m")
        klines = self.get_klines(interval, limit=period * 4)
        for k in klines:
            self._prices.append(k.close)
        self._calc_rsi()
        self._prev_rsi = self._rsi
        self.logger.info(f"RSI ready: {self._rsi:.1f} (from {len(klines)} klines)")

    async def on_kline(self, kline: KlineData) -> None:
        # 去重: 同一根 K 线多次推送时更新末位, 不追加
        if self._prices and self._last_ts == kline.open_time:
            self._prices[-1] = kline.close
        else:
            self._last_ts = kline.open_time
            self._prices.append(kline.close)
        self._calc_rsi()

    async def on_signal(self) -> Signal | None:
        period = self.parameters.get("period", 14)
        if len(self._prices) < period + 1:
            return None

        oversold = self.parameters.get("oversold", 30)
        overbought = self.parameters.get("overbought", 70)

        self._prev_rsi, prev = self._rsi, self._prev_rsi

        has_pos = self.has_position()

        # RSI crosses above oversold → buy
        if prev <= oversold and self._rsi > oversold and not has_pos:
            return Signal(
                strategy_id=self.strategy_id,
                symbol=self.symbol,
                action="OPEN_LONG",
                order_type="MARKET",
                comment=f"RSI reversal: {self._rsi:.1f} crossing above {oversold}",
            )

        # RSI crosses below overbought → sell
        if prev >= overbought and self._rsi < overbought:
            if has_pos:
                return Signal(
                    strategy_id=self.strategy_id,
                    symbol=self.symbol,
                    action="CLOSE_LONG",
                    order_type="MARKET",
                    comment=f"RSI reversal: {self._rsi:.1f} crossing below {overbought}",
                )
            return Signal(
                strategy_id=self.strategy_id,
                symbol=self.symbol,
                action="OPEN_SHORT",
                order_type="MARKET",
                comment=f"RSI reversal: {self._rsi:.1f} crossing below {overbought}",
            )

        return None

    def _calc_rsi(self) -> None:
        period = self.parameters.get("period", 14)
        prices = list(self._prices)

        if len(prices) < period + 1:
            return

        self._prev_rsi = self._rsi

        gains = 0.0
        losses = 0.0
        for i in range(-period, 0):
            delta = prices[i + 1] - prices[i]
            if delta > 0:
                gains += delta
            else:
                losses += -delta

        avg_gain = gains / period
        avg_loss = losses / period

        if avg_loss == 0:
            self._rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            self._rsi = 100.0 - (100.0 / (1.0 + rs))
