"""aiosqlite-based database connection manager."""

from __future__ import annotations

import aiosqlite
from pathlib import Path
from loguru import logger

from cryptopilot.core.config import ROOT_DIR
from cryptopilot.core.exceptions import DatabaseError
from cryptopilot.persistence.models import CREATE_TABLES

DB_PATH = ROOT_DIR / "data" / "crypto_pilot.db"


class Database:
    """Async SQLite database with connection pooling and migration."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = Path(db_path) if db_path else DB_PATH
        self._conn: aiosqlite.Connection | None = None

    @property
    def path(self) -> Path:
        return self._path

    async def connect(self) -> None:
        """Open database connection and run migrations."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = await aiosqlite.connect(
                str(self._path),
                isolation_level=None,  # autocommit mode
            )
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._migrate()
            logger.info(f"数据库已连接: {self._path}")
        except Exception as exc:
            raise DatabaseError(f"Failed to connect to database: {exc}") from exc

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("数据库连接已关闭")

    async def get_conn(self) -> aiosqlite.Connection:
        """Return the connection. Auto-connect if needed."""
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        return self._conn

    async def execute(self, sql: str, params: tuple | None = None) -> aiosqlite.Cursor:
        """Execute a SQL statement."""
        conn = await self.get_conn()
        return await conn.execute(sql, params or ())

    async def fetch_all(self, sql: str, params: tuple | None = None) -> list[dict]:
        """Execute a query and return all rows as dicts."""
        conn = await self.get_conn()
        cursor = await conn.execute(sql, params or ())
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def fetch_one(self, sql: str, params: tuple | None = None) -> dict | None:
        """Execute a query and return one row as dict, or None."""
        conn = await self.get_conn()
        cursor = await conn.execute(sql, params or ())
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _migrate(self) -> None:
        """Run table creation statements, then add any missing columns."""
        for stmt in CREATE_TABLES:
            await self.execute(stmt)

        # 增量迁移: 检测并添加缺失的列 (SQLite 不支持 ADD COLUMN IF NOT EXISTS)
        COLUMN_ADDITIONS = {
            "positions": {
                "tp_tiers_filled": "TEXT DEFAULT ''",
                "partial_tp_count": "INTEGER DEFAULT 0",
                "highest_price": "REAL DEFAULT 0",
                "lowest_price": "REAL DEFAULT 0",
                "current_stop": "REAL DEFAULT 0",
                "sideways_defense_moved": "INTEGER DEFAULT 0",
                "sideways_start_ts": "REAL DEFAULT 0",
                "initial_qty": "REAL DEFAULT 0",
                "take_profit_price": "REAL DEFAULT 0",
                "stop_loss_price": "REAL DEFAULT 0",
                "strategy_id": "TEXT DEFAULT ''",
                "strategy_preset": "TEXT DEFAULT ''",
                "support_presets": "TEXT DEFAULT ''",
                "entry_reason": "TEXT DEFAULT ''",
                "exit_reason": "TEXT DEFAULT ''",
                "exit_price": "REAL DEFAULT 0",
                "exit_time": "TEXT DEFAULT ''",
                "pnl": "REAL DEFAULT 0",
                "pnl_pct": "REAL DEFAULT 0",
            },
            "position_history": {
                "source_position_id": "INTEGER DEFAULT 0",
                "tp_tiers_filled": "TEXT DEFAULT ''",
                "partial_tp_count": "INTEGER DEFAULT 0",
                "highest_price": "REAL DEFAULT 0",
                "lowest_price": "REAL DEFAULT 0",
                "current_stop": "REAL DEFAULT 0",
                "sideways_defense_moved": "INTEGER DEFAULT 0",
                "sideways_start_ts": "REAL DEFAULT 0",
                "initial_qty": "REAL DEFAULT 0",
                "take_profit_price": "REAL DEFAULT 0",
                "stop_loss_price": "REAL DEFAULT 0",
                "strategy_id": "TEXT DEFAULT ''",
                "strategy_preset": "TEXT DEFAULT ''",
                "support_presets": "TEXT DEFAULT ''",
                "entry_reason": "TEXT DEFAULT ''",
                "exit_reason": "TEXT DEFAULT ''",
                "exit_price": "REAL DEFAULT 0",
                "exit_time": "TEXT DEFAULT ''",
                "pnl": "REAL DEFAULT 0",
                "pnl_pct": "REAL DEFAULT 0",
                "archived_at": "TEXT DEFAULT ''",
            },
        }
        for table, columns in COLUMN_ADDITIONS.items():
            rows = await self.fetch_all(f"PRAGMA table_info({table})")
            existing = {r["name"] for r in rows}
            for col_name, col_type in columns.items():
                if col_name not in existing:
                    await self.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
                    )
                    logger.info(f"数据库迁移: {table}.{col_name} 列已添加")

        migrate_count = len(CREATE_TABLES)
        logger.info(f"数据库迁移完成 ({migrate_count} 条 DDL)")
