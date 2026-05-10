"""Abstract strategy base class with lifecycle hooks and helpers."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from loguru import logger

from cryptopilot.market.types import KlineData, TickerData


@dataclass
class Signal:
    """Trading signal emitted by a strategy."""
    strategy_id: str
    symbol: str
    action: str          # OPEN_LONG, OPEN_SHORT, CLOSE_LONG, CLOSE_SHORT
    order_type: str      # MARKET, LIMIT, STOP_MARKET
    price: float = 0.0
    stop_loss: float = 0.0      # absolute stop-loss price
    take_profit: float = 0.0    # absolute take-profit price
    stop_loss_pct: float = 0.0  # stop-loss distance as % of price
    take_profit_pct: float = 0.0  # take-profit distance as % of price
    comment: str = ""


class StrategyBase(ABC):
    """Abstract base for all trading strategies.

    Each instance is bound to ONE symbol with ONE set of parameters.
    Subclasses implement on_init, on_tick, on_kline, on_signal.

    Lifecycle:
        __init__ → on_init → [on_tick / on_kline → on_signal → emit_signal] → on_stop
    """

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        parameters: dict,
        risk_config: dict,
        signal_queue: asyncio.Queue,
        cache,  # MarketDataCache (avoid circular import)
        position_manager,  # PositionManager
        order_manager,  # OrderManager
    ) -> None:
        self.strategy_id = strategy_id
        self.symbol = symbol.upper()
        self.parameters = parameters
        self.risk_config = risk_config
        self._signal_queue = signal_queue
        self._cache = cache
        self._position_manager = position_manager
        self._order_manager = order_manager
        self._enabled = True
        self._paused = False
        self.logger = logger.bind(strategy=self.strategy_id, symbol=self.symbol)

    # ----------------------------------------------------------------
    # Properties
    # ----------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        state = "已启用" if value else "已禁用"
        self.logger.info(f"策略{state}")

    @property
    def paused(self) -> bool:
        return self._paused

    @paused.setter
    def paused(self, value: bool) -> None:
        self._paused = value
        state = "已暂停" if value else "已恢复"
        self.logger.info(f"策略{state}")

    # ----------------------------------------------------------------
    # Lifecycle hooks — override in subclasses
    # ----------------------------------------------------------------

    @abstractmethod
    async def on_init(self) -> None:
        """Called once at startup. Load history, initialize indicators."""

    async def on_tick(self, ticker: TickerData) -> None:
        """Called on each ticker update (may be skipped for bar-only strategies)."""

    async def on_kline(self, kline: KlineData) -> None:
        """Called on each kline update."""

    async def on_signal(self) -> Signal | None:
        """Check conditions and return a Signal, or None (no action)."""
        return None

    async def on_stop(self) -> None:
        """Called when strategy is stopped. Persist state, cancel orders."""

    # ----------------------------------------------------------------
    # Helpers for subclasses
    # ----------------------------------------------------------------

    async def emit_signal(self, signal: Signal) -> None:
        """Put a trading signal onto the central signal queue."""
        signal.strategy_id = self.strategy_id
        signal.symbol = self.symbol
        await self._signal_queue.put(signal)
        self.logger.info(
            f"信号已发出：{signal.action} {signal.symbol} @ {signal.price:.4f} "
            f"[{signal.comment}]"
        )

    def get_position(self) -> dict | None:
        """Query current position for this strategy's symbol."""
        return self._position_manager.get_position(self.symbol)

    def has_position(self) -> bool:
        """Check if we currently hold a position."""
        return self._position_manager.has_position(self.symbol)

    def get_klines(self, interval: str, limit: int = 100) -> list[KlineData]:
        """Get recent klines from the market data cache."""
        return self._cache.get_klines(self.symbol, interval, limit)

    def get_latest_kline(self, interval: str) -> KlineData | None:
        """Get the most recent kline for a given interval."""
        return self._cache.get_kline(self.symbol, interval)

    def get_ticker(self) -> TickerData | None:
        """Get the latest ticker for this symbol."""
        return self._cache.get_ticker(self.symbol)

    def has_open_order(self) -> bool:
        """Check if there are pending orders for this symbol."""
        return self._order_manager.has_open_order(self.symbol)
