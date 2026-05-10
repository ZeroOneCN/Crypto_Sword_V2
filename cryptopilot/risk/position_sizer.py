"""Dynamic position size calculation from balance, risk %, stop distance, leverage."""

from __future__ import annotations

from loguru import logger


class PositionSizer:
    """Calculates order quantity for a given risk profile.

    Formula:
        risk_amount = account_balance * risk_pct / 100
        stop_distance = entry_price * stop_loss_pct / 100  (in quote currency)
        quantity = risk_amount / stop_distance * leverage
    """

    def __init__(self, risk_config: dict) -> None:
        self._max_position_pct = risk_config.get("max_position_pct", 20)
        self._default_leverage = risk_config.get("default_leverage", 3)
        self._max_leverage = risk_config.get("max_leverage", 10)

    def calculate(
        self,
        balance: float,
        entry_price: float,
        stop_loss_pct: float,
        leverage: int | None = None,
        position_pct: float | None = None,
    ) -> float:
        """Calculate position quantity in base asset.

        Args:
            balance: Available account balance (USDT)
            entry_price: Current price of the asset
            stop_loss_pct: Distance to stop-loss as % of price (e.g. 2.0 = 2%)
            leverage: Leverage to use (default from config)
            position_pct: Max % of account to use for this position

        Returns:
            Quantity in base asset to buy/sell.
        """
        lev = min(leverage or self._default_leverage, self._max_leverage)
        max_pct = position_pct or self._max_position_pct

        # Maximum quantity based on position % of balance
        max_notional = balance * max_pct / 100 * lev
        max_qty = max_notional / entry_price

        # Risk-based quantity
        if stop_loss_pct > 0:
            stop_distance = entry_price * stop_loss_pct / 100
            risk_amount = balance * 1.0 / 100  # 1% account risk per trade
            risk_qty = risk_amount / stop_distance * lev
        else:
            risk_qty = max_qty

        qty = min(risk_qty, max_qty)
        return qty

    def max_quantity(
        self,
        balance: float,
        entry_price: float,
        leverage: int | None = None,
    ) -> float:
        """Calculate the maximum allowable quantity for a position."""
        lev = min(leverage or self._default_leverage, self._max_leverage)
        max_notional = balance * self._max_position_pct / 100 * lev
        return max_notional / entry_price
