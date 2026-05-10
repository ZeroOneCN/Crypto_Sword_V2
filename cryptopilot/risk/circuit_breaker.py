"""Daily loss circuit breaker — monitors P&L and halts trading on threshold breach."""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger


class CircuitBreaker:
    """Tracks daily realized P&L and trips when loss exceeds threshold.

    On trip: all strategies are stopped and all positions closed.
    Resets daily at midnight UTC.
    """

    def __init__(self, max_daily_loss_pct: float = 2.0) -> None:
        self._max_daily_loss_pct = max_daily_loss_pct
        self._day_start_balance: float | None = None
        self._current_day = None  # datetime.date
        self._tripped: bool = False
        self._daily_pnl: float = 0.0

    @property
    def tripped(self) -> bool:
        """Whether the circuit breaker has been tripped."""
        return self._tripped

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    def _check_day_rollover(self) -> None:
        """Reset daily tracking if UTC date has changed."""
        today = datetime.now(tz=timezone.utc).date()
        if self._current_day != today:
            self._current_day = today
            self._day_start_balance = None
            self._daily_pnl = 0.0
            self._tripped = False

    def update(
        self,
        current_balance: float,
        realized_pnl_change: float = 0.0,
    ) -> bool:
        """Update P&L and check if the breaker should trip.

        Args:
            current_balance: Current total account balance.
            realized_pnl_change: P&L change since last update.

        Returns:
            True if trading should continue, False if breaker tripped.
        """
        self._check_day_rollover()

        if self._day_start_balance is None:
            self._day_start_balance = current_balance

        self._daily_pnl += realized_pnl_change

        # Check threshold
        if self._day_start_balance > 0:
            loss_pct = -self._daily_pnl / self._day_start_balance * 100
            if loss_pct >= self._max_daily_loss_pct and not self._tripped:
                self._tripped = True
                logger.error(
                    f"熔断已触发：当日亏损 {loss_pct:.2f}% 超过阈值 "
                    f"{self._max_daily_loss_pct}%（盈亏：${self._daily_pnl:.2f}）"
                )
                return False

        return not self._tripped

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._tripped = False
        logger.warning("熔断已手动重置")
