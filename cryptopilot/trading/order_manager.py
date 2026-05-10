"""Local order state tracking, synced with database and exchange."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from cryptopilot.persistence.database import Database
from cryptopilot.persistence.repositories import OrderRepository, FillRepository
from cryptopilot.trading.order_executor import OrderResult


class OrderManager:
    """Tracks open orders in memory + database. Supports periodic exchange sync."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._order_repo = OrderRepository(db)
        self._fill_repo = FillRepository(db)
        self._open_orders: dict[str, dict] = {}  # client_order_id -> db row

    async def record_order(self, result: OrderResult, strategy_name: str = "") -> int:
        """Insert a new order record."""
        from cryptopilot.persistence.models import OrderRecord

        rec = OrderRecord(
            symbol=result.symbol,
            strategy_name=strategy_name,
            side=result.side,
            type=result.order_type,
            price=result.price,
            orig_qty=result.orig_qty,
            executed_qty=result.executed_qty,
            status=result.status,
            client_order_id=result.client_order_id,
            exchange_order_id=str(result.order_id),
            pos_side=result.position_side,
        )
        row_id = await self._order_repo.create(rec)

        if result.status in ("NEW", "PARTIALLY_FILLED"):
            row = await self._order_repo.get_by_client_id(result.client_order_id)
            if row:
                self._open_orders[result.client_order_id] = row

        return row_id

    async def update_order(self, client_order_id: str, status: str, executed_qty: float | None = None) -> None:
        """Update order status locally and in DB."""
        await self._order_repo.update_status(client_order_id, status, executed_qty)
        if status in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
            self._open_orders.pop(client_order_id, None)

    async def record_fill(self, order_db_id: int, price: float, qty: float, commission: float = 0, asset: str = "", filled_at: str = "") -> int:
        """Record a fill event."""
        from cryptopilot.persistence.models import FillRecord

        rec = FillRecord(
            order_id=order_db_id,
            price=price,
            qty=qty,
            commission=commission,
            commission_asset=asset,
        )
        return await self._fill_repo.create(rec, filled_at=filled_at)

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        """Get currently tracked open orders."""
        orders = await self._order_repo.get_open_orders(symbol)
        # Update in-memory cache
        for o in orders:
            cid = o.get("client_order_id")
            if cid:
                self._open_orders[cid] = o
        return orders

    async def sync_with_exchange(self, executor) -> None:
        """Pull open orders from exchange and reconcile with local state."""
        exchange_orders = await executor.get_open_orders()
        exchange_ids = {o.client_order_id for o in exchange_orders}

        # Close any local orders no longer on exchange
        for cid in list(self._open_orders.keys()):
            if cid not in exchange_ids:
                await self._order_repo.update_status(cid, "CANCELED")
                self._open_orders.pop(cid, None)

        # Upsert exchange orders
        for o in exchange_orders:
            await self._order_repo.update_status(
                o.client_order_id,
                o.status,
                o.executed_qty,
                exchange_order_id=str(o.order_id),
            )

    def has_open_order(self, symbol: str) -> bool:
        """Check if there are any open orders for a symbol."""
        for o in self._open_orders.values():
            if o.get("symbol") == symbol:
                return True
        return False
