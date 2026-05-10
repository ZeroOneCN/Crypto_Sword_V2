"""Central event bus — routes trading events to all notification channels."""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import NamedTuple, Callable

from loguru import logger


class Events(str, Enum):
    """All notifiable event types."""
    # Trade events
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    TAKE_PROFIT_TRIGGERED = "take_profit_triggered"
    TRAILING_STOP_ADJUSTED = "trailing_stop_adjusted"

    # System events
    CIRCUIT_BREAKER_ACTIVATED = "circuit_breaker_activated"
    STRATEGY_STARTED = "strategy_started"
    STRATEGY_STOPPED = "strategy_stopped"
    STRATEGY_ERROR = "strategy_error"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    DAILY_REPORT = "daily_report"
    ERROR = "error"
    WARNING = "warning"


class EventData(NamedTuple):
    """An event payload with type-appropriate data fields."""
    event: Events
    message: str
    symbol: str = ""
    strategy_id: str = ""
    price: float = 0.0
    quantity: float = 0.0
    pnl: float = 0.0
    extra: dict | None = None


Handler = Callable[[EventData], None]


class Notifier:
    """Central event dispatcher. Handlers are registered per event type.

    Supports multiple channels (Telegram, console, etc.) via handler registration.
    """

    def __init__(self) -> None:
        self._handlers: dict[Events, list[Handler]] = {}

    def register(self, event: Events, handler: Handler) -> None:
        """Register a handler for a specific event type."""
        self._handlers.setdefault(event, []).append(handler)

    def unregister(self, event: Events, handler: Handler) -> None:
        try:
            self._handlers.get(event, []).remove(handler)
        except ValueError:
            pass

    def notify(self, data: EventData) -> None:
        """Dispatch an event to all registered handlers synchronously."""
        handlers = self._handlers.get(data.event, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception:
                logger.exception(f"Notification handler error for event {data.event}")

    async def notify_async(self, data: EventData) -> None:
        """Dispatch an event to all registered handlers asynchronously."""
        handlers = self._handlers.get(data.event, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception:
                logger.exception(f"Notification handler error for event {data.event}")

    # -- Convenience helpers --
    def order_filled(self, symbol: str, side: str, price: float, qty: float, **extra) -> None:
        self.notify(EventData(
            event=Events.ORDER_FILLED,
            message=f"{side} {qty} {symbol} @ {price:.4f} filled",
            symbol=symbol, price=price, quantity=qty,
            extra={"side": side, **extra},
        ))

    def position_opened(self, symbol: str, side: str, price: float, qty: float) -> None:
        self.notify(EventData(
            event=Events.POSITION_OPENED,
            message=f"Position OPENED: {side} {qty} {symbol} @ {price:.4f}",
            symbol=symbol, price=price, quantity=qty,
        ))

    def position_closed(self, symbol: str, side: str, price: float, pnl: float) -> None:
        self.notify(EventData(
            event=Events.POSITION_CLOSED,
            message=f"Position CLOSED: {side} {symbol} @ {price:.4f}, PnL: ${pnl:.2f}",
            symbol=symbol, price=price, pnl=pnl,
        ))

    def circuit_breaker_activated(self, loss_pct: float, pnl: float) -> None:
        self.notify(EventData(
            event=Events.CIRCUIT_BREAKER_ACTIVATED,
            message=f"[ALERT] CIRCUIT BREAKER: Daily loss {loss_pct:.2f}% (${pnl:.2f})",
            pnl=pnl,
        ))

    def strategy_error(self, strategy_id: str, error: str) -> None:
        self.notify(EventData(
            event=Events.STRATEGY_ERROR,
            message=f"Strategy '{strategy_id}' error: {error}",
            strategy_id=strategy_id,
        ))
