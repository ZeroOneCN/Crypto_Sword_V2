"""Position tracking — sync with exchange & database."""

from __future__ import annotations

from loguru import logger

from cryptopilot.persistence.database import Database
from cryptopilot.persistence.repositories import PositionRepository
from cryptopilot.persistence.models import PositionRecord
from cryptopilot.trading.order_executor import PositionInfo


class PositionManager:
    """In-memory position cache synced with exchange and persisted to DB."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = PositionRepository(db)
        self._positions: dict[str, dict] = {}  # symbol -> db row

    async def sync_from_exchange(self, executor) -> None:
        """Pull positions from exchange, update memory + DB."""
        positions = await executor.get_position_info()
        active_symbols = set()

        for pos in positions:
            sym = pos.symbol
            active_symbols.add(sym)

            rec = PositionRecord(
                symbol=pos.symbol,
                side=pos.position_side,
                qty=pos.quantity,
                entry_price=pos.entry_price,
                mark_price=pos.mark_price,
                leverage=pos.leverage,
                liquidation_price=pos.liquidation_price,
                unrealized_pnl=pos.unrealized_pnl,
            )
            await self._repo.upsert(rec)
            row = await self._repo.get_by_symbol(sym)
            if row:
                self._positions[sym] = row

        # Remove positions that are no longer open
        for sym in list(self._positions.keys()):
            if sym not in active_symbols and self._positions[sym].get("qty", 0) == 0:
                await self._repo.delete(sym, self._positions[sym].get("side", ""))
                self._positions.pop(sym, None)

    def get_position(self, symbol: str) -> dict | None:
        """Get a position for a symbol (or None)."""
        return self._positions.get(symbol)

    def get_all_positions(self) -> list[dict]:
        """Return all tracked positions."""
        return list(self._positions.values())

    def has_position(self, symbol: str) -> bool:
        """Check if we hold a position in this symbol."""
        pos = self._positions.get(symbol)
        return pos is not None and abs(pos.get("qty", 0)) > 0

    @property
    def position_count(self) -> int:
        return len([p for p in self._positions.values() if abs(p.get("qty", 0)) > 0])
