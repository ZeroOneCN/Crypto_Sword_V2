"""Trailing stop management — dynamically adjusts stop-loss as price moves favorably."""

from __future__ import annotations

from loguru import logger


class TrailingStop:
    """Tracks a trailing stop level for a single position.

    The stop price trails the market price by a fixed distance (percentage or absolute).
    Only moves in the favorable direction (up for longs, down for shorts).
    """

    def __init__(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        initial_stop: float,
        trail_distance_pct: float,
        activation_pct: float = 0.0,
    ) -> None:
        self.symbol = symbol.upper()
        self.side = side.upper()  # LONG or SHORT
        self.entry_price = entry_price
        self._stop_price = initial_stop
        self._trail_pct = trail_distance_pct
        self._activation_pct = activation_pct  # Price must move this % before trailing starts
        self._highest_price = entry_price  # for LONG positions
        self._lowest_price = entry_price    # for SHORT positions
        self._activated = activation_pct <= 0
        self._logger = logger.bind(symbol=self.symbol, side=self.side)

    @property
    def current_stop(self) -> float:
        """Current stop-loss price."""
        return self._stop_price

    @property
    def activated(self) -> bool:
        return self._activated

    def update(self, current_price: float) -> float | None:
        """Update trailing stop based on current market price.

        Returns:
            New stop price if it changed, else None.
        """
        old_stop = self._stop_price

        if self.side == "LONG":
            self._update_long(current_price)
        else:
            self._update_short(current_price)

        if self._stop_price != old_stop:
            self._logger.info(
                f"移动止损已调整：{old_stop:.4f} → {self._stop_price:.4f} "
                f"（当前价={current_price:.4f}）"
            )
            return self._stop_price
        return None

    def should_trigger(self, current_price: float) -> bool:
        """Check if current price has breached the stop level."""
        if self.side == "LONG":
            return current_price <= self._stop_price
        return current_price >= self._stop_price

    def _update_long(self, price: float) -> None:
        """Update trailing stop for LONG position (stop moves UP only)."""
        self._highest_price = max(self._highest_price, price)

        if not self._activated:
            gain_pct = (self._highest_price - self.entry_price) / self.entry_price * 100
            if gain_pct >= self._activation_pct:
                self._activated = True
                self._logger.info(
                    f"移动止损已激活：{price:.4f} "
                    f"（涨幅={gain_pct:.2f}%，激活阈值={self._activation_pct}%）"
                )

        if self._activated:
            new_stop = self._highest_price * (1 - self._trail_pct / 100)
            if new_stop > self._stop_price:
                self._stop_price = new_stop

    def _update_short(self, price: float) -> None:
        """Update trailing stop for SHORT position (stop moves DOWN only)."""
        self._lowest_price = min(self._lowest_price, price)

        if not self._activated:
            gain_pct = (self.entry_price - self._lowest_price) / self.entry_price * 100
            if gain_pct >= self._activation_pct:
                self._activated = True
                self._logger.info(
                    f"移动止损已激活：{price:.4f} "
                    f"（涨幅={gain_pct:.2f}%，激活阈值={self._activation_pct}%）"
                )

        if self._activated:
            new_stop = self._lowest_price * (1 + self._trail_pct / 100)
            if new_stop < self._stop_price:
                self._stop_price = new_stop
