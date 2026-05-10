"""Profit locking — automatically secures profits by partial closing or tightening stops."""

from __future__ import annotations

from loguru import logger


class ProfitLocker:
    """Monitors position profit and triggers profit-locking actions.

    Two strategies:
    - **Partial close**: When profit exceeds threshold_pct, close fraction of position
    - **Tighten stop**: Move stop-loss to breakeven once profit exceeds activation_pct
    """

    def __init__(
        self,
        activation_pct: float = 3.0,      # Profit % to trigger lock
        lock_fraction: float = 0.5,        # Fraction of position to close (0.5 = half)
        breakeven_after_pct: float = 2.0,  # Move SL to entry after this % profit
    ) -> None:
        self._activation = activation_pct
        self._lock_fraction = lock_fraction
        self._breakeven_pct = breakeven_after_pct
        self._has_locked: dict[str, bool] = {}       # symbol -> already locked?
        self._has_moved_sl: dict[str, bool] = {}      # symbol -> already moved SL to BE?

    def should_lock(self, symbol: str, entry_price: float, current_price: float, side: str) -> bool:
        """Check if profit locking should trigger (partial close)."""
        if self._has_locked.get(symbol, False):
            return False

        pnl_pct = self._calc_pnl_pct(entry_price, current_price, side)
        return pnl_pct >= self._activation

    def should_breakeven(self, symbol: str, entry_price: float, current_price: float, side: str) -> bool:
        """Check if stop-loss should move to breakeven."""
        if self._has_moved_sl.get(symbol, False):
            return False

        pnl_pct = self._calc_pnl_pct(entry_price, current_price, side)
        return pnl_pct >= self._breakeven_pct

    def mark_locked(self, symbol: str) -> None:
        self._has_locked[symbol] = True
        logger.info(f"利润已锁定：{symbol}")

    def mark_breakeven(self, symbol: str) -> None:
        self._has_moved_sl[symbol] = True
        logger.info(f"止损已移至保本价：{symbol}")

    def reset(self, symbol: str) -> None:
        """Reset lock state when position closes."""
        self._has_locked.pop(symbol, None)
        self._has_moved_sl.pop(symbol, None)

    def lock_quantity(self, original_qty: float) -> float:
        """Quantity to close for partial profit locking."""
        return original_qty * self._lock_fraction

    @staticmethod
    def _calc_pnl_pct(entry: float, current: float, side: str) -> float:
        if entry <= 0:
            return 0.0
        if side.upper() == "LONG":
            return (current - entry) / entry * 100
        return (entry - current) / entry * 100
