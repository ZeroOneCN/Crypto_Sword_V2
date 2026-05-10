"""Async CRUD operations for orders, fills, positions, account snapshots, and strategy events."""

from __future__ import annotations

from cryptopilot.persistence.database import Database
from cryptopilot.persistence.models import (
    OrderRecord,
    FillRecord,
    PositionRecord,
    AccountSnapshot,
    StrategyEvent,
)
from cryptopilot.utils.time_utils import iso_now


class OrderRepository:
    """CRUD for orders table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, order: OrderRecord) -> int:
        now = iso_now()
        order.created_at = now
        order.updated_at = now
        sql = """
            INSERT INTO orders (symbol, strategy_name, side, type, price, orig_qty,
                executed_qty, status, client_order_id, exchange_order_id, pos_side,
                leverage, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = await self._db.execute(sql, (
            order.symbol, order.strategy_name, order.side, order.type,
            order.price, order.orig_qty, order.executed_qty, order.status,
            order.client_order_id, order.exchange_order_id, order.pos_side,
            order.leverage, order.created_at, order.updated_at,
        ))
        return cursor.lastrowid

    async def update_status(
        self,
        client_order_id: str,
        status: str,
        executed_qty: float | None = None,
        exchange_order_id: str | None = None,
    ) -> None:
        now = iso_now()
        parts = ["status = ?", "updated_at = ?"]
        params: list = [status, now]
        if executed_qty is not None:
            parts.append("executed_qty = ?")
            params.append(executed_qty)
        if exchange_order_id is not None:
            parts.append("exchange_order_id = ?")
            params.append(exchange_order_id)
        params.append(client_order_id)
        await self._db.execute(
            f"UPDATE orders SET {', '.join(parts)} WHERE client_order_id = ?",
            tuple(params),
        )

    async def get_by_client_id(self, client_order_id: str) -> dict | None:
        return await self._db.fetch_one(
            "SELECT * FROM orders WHERE client_order_id = ?",
            (client_order_id,),
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        if symbol:
            return await self._db.fetch_all(
                "SELECT * FROM orders WHERE status IN ('NEW', 'PARTIALLY_FILLED') AND symbol = ?",
                (symbol,),
            )
        return await self._db.fetch_all(
            "SELECT * FROM orders WHERE status IN ('NEW', 'PARTIALLY_FILLED')",
        )

    async def get_history(
        self, symbol: str | None = None, limit: int = 100
    ) -> list[dict]:
        if symbol:
            return await self._db.fetch_all(
                "SELECT * FROM orders WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
                (symbol, limit),
            )
        return await self._db.fetch_all(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )


class FillRepository:
    """CRUD for fills table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, fill: FillRecord) -> int:
        fill.filled_at = iso_now()
        sql = """
            INSERT INTO fills (order_id, price, qty, commission, commission_asset, filled_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor = await self._db.execute(sql, (
            fill.order_id, fill.price, fill.qty,
            fill.commission, fill.commission_asset, fill.filled_at,
        ))
        return cursor.lastrowid

    async def get_for_order(self, order_id: int) -> list[dict]:
        return await self._db.fetch_all(
            "SELECT * FROM fills WHERE order_id = ?",
            (order_id,),
        )


class PositionRepository:
    """CRUD for positions table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert(self, pos: PositionRecord) -> None:
        now = iso_now()
        existing = await self._db.fetch_one(
            "SELECT id FROM positions WHERE symbol = ? AND side = ?",
            (pos.symbol, pos.side),
        )
        if existing:
            pos.updated_at = now
            await self._db.execute(
                """UPDATE positions SET qty=?, entry_price=?, mark_price=?,
                   leverage=?, liquidation_price=?, unrealized_pnl=?, updated_at=?
                   WHERE symbol=? AND side=?""",
                (pos.qty, pos.entry_price, pos.mark_price, pos.leverage,
                 pos.liquidation_price, pos.unrealized_pnl, now,
                 pos.symbol, pos.side),
            )
        else:
            pos.created_at = now
            pos.updated_at = now
            await self._db.execute(
                """INSERT INTO positions (symbol, side, qty, entry_price,
                   mark_price, leverage, liquidation_price, unrealized_pnl,
                   created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (pos.symbol, pos.side, pos.qty, pos.entry_price, pos.mark_price,
                 pos.leverage, pos.liquidation_price, pos.unrealized_pnl,
                 pos.created_at, pos.updated_at),
            )

    async def delete(self, symbol: str, side: str) -> None:
        await self._db.execute(
            "DELETE FROM positions WHERE symbol = ? AND side = ?",
            (symbol, side),
        )

    async def get_all(self) -> list[dict]:
        return await self._db.fetch_all("SELECT * FROM positions")

    async def get_by_symbol(self, symbol: str) -> dict | None:
        return await self._db.fetch_one(
            "SELECT * FROM positions WHERE symbol = ?",
            (symbol,),
        )


class AccountRepository:
    """CRUD for account_snapshots table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, snap: AccountSnapshot) -> int:
        snap.taken_at = iso_now()
        sql = """
            INSERT INTO account_snapshots (total_balance, available_balance,
                unrealized_pnl, margin_ratio, taken_at) VALUES (?, ?, ?, ?, ?)
        """
        cursor = await self._db.execute(sql, (
            snap.total_balance, snap.available_balance,
            snap.unrealized_pnl, snap.margin_ratio, snap.taken_at,
        ))
        return cursor.lastrowid

    async def get_recent(self, limit: int = 100) -> list[dict]:
        return await self._db.fetch_all(
            "SELECT * FROM account_snapshots ORDER BY taken_at DESC LIMIT ?",
            (limit,),
        )


class StrategyEventRepository:
    """CRUD for strategy_events table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, event: StrategyEvent) -> int:
        event.created_at = iso_now()
        sql = """
            INSERT INTO strategy_events (strategy_id, event_type, symbol, details, created_at)
            VALUES (?, ?, ?, ?, ?)
        """
        cursor = await self._db.execute(sql, (
            event.strategy_id, event.event_type, event.symbol,
            event.details, event.created_at,
        ))
        return cursor.lastrowid

    async def get_for_strategy(
        self, strategy_id: str, limit: int = 100
    ) -> list[dict]:
        return await self._db.fetch_all(
            "SELECT * FROM strategy_events WHERE strategy_id = ? ORDER BY created_at DESC LIMIT ?",
            (strategy_id, limit),
        )
