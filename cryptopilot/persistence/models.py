"""Dataclasses and SQL DDL for all database tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ----------------------------------------------------------------
# Table creation SQL
# ----------------------------------------------------------------

CREATE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        strategy_name TEXT NOT NULL,
        side TEXT NOT NULL,
        type TEXT NOT NULL,
        price REAL DEFAULT 0,
        orig_qty REAL NOT NULL,
        executed_qty REAL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'NEW',
        client_order_id TEXT UNIQUE,
        exchange_order_id TEXT,
        pos_side TEXT DEFAULT 'BOTH',
        leverage INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER REFERENCES orders(id),
        price REAL NOT NULL,
        qty REAL NOT NULL,
        commission REAL DEFAULT 0,
        commission_asset TEXT DEFAULT '',
        filled_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        qty REAL NOT NULL,
        entry_price REAL NOT NULL,
        mark_price REAL DEFAULT 0,
        leverage INTEGER DEFAULT 1,
        liquidation_price REAL DEFAULT 0,
        unrealized_pnl REAL DEFAULT 0,
        tp_tiers_filled TEXT DEFAULT '',     -- comma-separated tier levels filled, e.g. "1,2"
        partial_tp_count INTEGER DEFAULT 0,   -- number of partial TP fills
        highest_price REAL DEFAULT 0,         -- highest price seen (LONG) / 0 if SHORT
        lowest_price REAL DEFAULT 0,          -- lowest price seen (SHORT) / 0 if LONG
        current_stop REAL DEFAULT 0,          -- current stop-loss price
        sideways_defense_moved INTEGER DEFAULT 0,  -- 1 if sideways defense stop deployed
        sideways_start_ts REAL DEFAULT 0,     -- epoch timestamp when sideways range began
        initial_qty REAL DEFAULT 0,           -- original position quantity (before TP fills)
        take_profit_price REAL DEFAULT 0,     -- original take-profit price (highest tier)
        stop_loss_price REAL DEFAULT 0,       -- original stop-loss price
        strategy_id TEXT DEFAULT '',          -- stable strategy attribution for the position
        strategy_preset TEXT DEFAULT '',      -- preset name (ambush/chase/composite)
        support_presets TEXT DEFAULT '',      -- comma-separated supporting presets
        entry_reason TEXT DEFAULT '',          -- reason for entry (set on open)
        exit_reason TEXT DEFAULT '',          -- reason for exit (set on close)
        exit_price REAL DEFAULT 0,            -- avg exit price (set on close)
        exit_time TEXT DEFAULT '',            -- iso timestamp of exit
        pnl REAL DEFAULT 0,                   -- realized PnL (set on close)
        pnl_pct REAL DEFAULT 0,              -- realized PnL % (set on close)
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS position_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_position_id INTEGER DEFAULT 0,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        qty REAL NOT NULL,
        entry_price REAL NOT NULL,
        mark_price REAL DEFAULT 0,
        leverage INTEGER DEFAULT 1,
        liquidation_price REAL DEFAULT 0,
        unrealized_pnl REAL DEFAULT 0,
        tp_tiers_filled TEXT DEFAULT '',
        partial_tp_count INTEGER DEFAULT 0,
        highest_price REAL DEFAULT 0,
        lowest_price REAL DEFAULT 0,
        current_stop REAL DEFAULT 0,
        sideways_defense_moved INTEGER DEFAULT 0,
        sideways_start_ts REAL DEFAULT 0,
        initial_qty REAL DEFAULT 0,
        take_profit_price REAL DEFAULT 0,
        stop_loss_price REAL DEFAULT 0,
        strategy_id TEXT DEFAULT '',
        strategy_preset TEXT DEFAULT '',
        support_presets TEXT DEFAULT '',
        entry_reason TEXT DEFAULT '',
        exit_reason TEXT DEFAULT '',
        exit_price REAL DEFAULT 0,
        exit_time TEXT DEFAULT '',
        pnl REAL DEFAULT 0,
        pnl_pct REAL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived_at TEXT NOT NULL,
        UNIQUE(symbol, side, created_at, exit_time)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_balance REAL NOT NULL,
        available_balance REAL NOT NULL,
        unrealized_pnl REAL DEFAULT 0,
        margin_ratio REAL DEFAULT 0,
        taken_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        symbol TEXT NOT NULL DEFAULT '',
        details TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_position_history_symbol ON position_history(symbol);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_position_history_exit_time ON position_history(exit_time);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_snapshots_taken ON account_snapshots(taken_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_strategy ON strategy_events(strategy_id);
    """,
]


# ----------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------

@dataclass
class OrderRecord:
    symbol: str
    strategy_name: str
    side: str
    type: str
    orig_qty: float
    price: float = 0.0
    executed_qty: float = 0.0
    status: str = "NEW"
    client_order_id: str = ""
    exchange_order_id: str = ""
    pos_side: str = "BOTH"
    leverage: int = 1
    id: Optional[int] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class FillRecord:
    order_id: int
    price: float
    qty: float
    commission: float = 0.0
    commission_asset: str = ""
    filled_at: str = ""
    id: Optional[int] = None


@dataclass
class PositionRecord:
    symbol: str
    side: str
    qty: float
    entry_price: float
    mark_price: float = 0.0
    leverage: int = 1
    liquidation_price: float = 0.0
    unrealized_pnl: float = 0.0
    tp_tiers_filled: str = ""           # comma-separated "1,2"
    partial_tp_count: int = 0
    highest_price: float = 0.0
    lowest_price: float = 0.0
    current_stop: float = 0.0
    sideways_defense_moved: int = 0
    sideways_start_ts: float = 0.0
    initial_qty: float = 0.0
    take_profit_price: float = 0.0
    stop_loss_price: float = 0.0
    strategy_id: str = ""
    strategy_preset: str = ""
    support_presets: str = ""
    entry_reason: str = ""
    exit_reason: str = ""
    exit_price: float = 0.0
    exit_time: str = ""
    pnl: float = 0.0
    pnl_pct: float = 0.0
    id: Optional[int] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class AccountSnapshot:
    total_balance: float
    available_balance: float
    unrealized_pnl: float = 0.0
    margin_ratio: float = 0.0
    taken_at: str = ""
    id: Optional[int] = None


@dataclass
class StrategyEvent:
    strategy_id: str
    event_type: str
    symbol: str = ""
    details: str = "{}"
    created_at: str = ""
    id: Optional[int] = None
