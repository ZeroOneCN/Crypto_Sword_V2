"""Volume anomaly / spike detection strategy.

Current bar volume exceeds N times the average volume → breakout signal.
Direction is determined by price movement.
"""

from __future__ import annotations

from collections import deque

from cryptopilot.market.types import KlineData
from cryptopilot.strategy.base import StrategyBase, Signal


class VolumeBreakoutStrategy(StrategyBase):
    """Volume spike + price direction strategy.

    When volume spikes above a multiple of the average, go with the direction
    of the price movement on that bar.

    Parameters:
        lookback (int): Number of bars for average volume (default 20)
        volume_mult (float): Volume multiplier trigger (default 2.5)
        min_price_move_pct (float): Minimum price move % to confirm direction (default 0.3)
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._volumes: deque[float] = deque(maxlen=500)
        self._prices: deque[float] = deque(maxlen=500)
        self._last_ts: int = 0
        self._avg_volume: float = 0.0

    async def on_init(self) -> None:
        lookback = self.parameters.get("lookback", 20)
        vol_mult = self.parameters.get("volume_mult", 2.5)
        self.logger.info(
            f"Initializing Volume Breakout: lookback={lookback} mult={vol_mult}x"
        )

        interval = self.parameters.get("interval", "5m")
        klines = self.get_klines(interval, limit=lookback * 3)
        for k in klines:
            self._volumes.append(k.volume)
            self._prices.append(k.close)
            self._calc_avg()

        self.logger.info(f"Volume breakout ready: avg_vol={self._avg_volume:.2f}")

    async def on_kline(self, kline: KlineData) -> None:
        if self._prices and self._last_ts == kline.open_time:
            self._volumes[-1] = kline.volume
            self._prices[-1] = kline.close
        else:
            self._last_ts = kline.open_time
            self._volumes.append(kline.volume)
            self._prices.append(kline.close)
        self._calc_avg()

        if not kline.is_final:
            return

        lookback = self.parameters.get("lookback", 20)
        vol_mult = self.parameters.get("volume_mult", 2.5)
        min_move = self.parameters.get("min_price_move_pct", 0.3)

        if self._avg_volume <= 0 or kline.volume < self._avg_volume * vol_mult:
            return

        # Volume spike detected — determine direction
        price_change = (kline.close - kline.open) / kline.open * 100

        if abs(price_change) < min_move:
            return

        has_pos = self.has_position()

        # Volume spike on positive bar
        if price_change > 0:
            if has_pos:
                # Already long — skip (or add)
                return
            signal = await self._emit_volume_signal("OPEN_LONG", kline.close, kline.volume, self._avg_volume, price_change)
            return signal

        # Volume spike on negative bar
        if price_change < 0:
            if has_pos:
                # Close long
                signal = await self._emit_volume_signal("CLOSE_LONG", kline.close, kline.volume, self._avg_volume, price_change)
                return signal
            signal = await self._emit_volume_signal("OPEN_SHORT", kline.close, kline.volume, self._avg_volume, price_change)
            return signal

    async def on_signal(self) -> Signal | None:
        return None  # Signal emitted directly in on_kline

    async def _emit_volume_signal(
        self, action: str, price: float, volume: float, avg_vol: float, move_pct: float
    ) -> Signal:
        mult = volume / avg_vol if avg_vol > 0 else 0
        return Signal(
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            action=action,
            order_type="MARKET",
            price=price,
            comment=f"Volume spike {mult:.1f}x, move={move_pct:+.2f}%",
        )

    def _calc_avg(self) -> None:
        lookback = self.parameters.get("lookback", 20)
        vols = list(self._volumes)
        if len(vols) >= lookback:
            self._avg_volume = sum(vols[-lookback:]) / lookback
