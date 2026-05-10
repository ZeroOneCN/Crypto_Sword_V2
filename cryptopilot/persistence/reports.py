"""Trading report generation from database records.

Computes: total P&L, win rate, max drawdown, trade list, Sharpe ratio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptopilot.persistence.database import Database


@dataclass
class TradeSummary:
    """Summary of a single completed trade (open + close = 1 trade)."""
    symbol: str
    side: str
    entry_qty: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    opened_at: str
    closed_at: str


@dataclass
class PerformanceReport:
    """Aggregated trading performance metrics."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    start_balance: float = 0.0
    current_balance: float = 0.0
    trades: list[TradeSummary] = field(default_factory=list)
    generated_at: str = ""


class ReportGenerator:
    """Generates performance reports from the database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def generate(self) -> PerformanceReport:
        """Build a complete performance report."""
        report = PerformanceReport()
        report.generated_at = datetime.now(tz=timezone.utc).isoformat()

        # Get all filled orders
        orders = await self._db.fetch_all(
            "SELECT * FROM orders WHERE status = 'FILLED' ORDER BY created_at"
        )

        # Get fills
        fills = await self._db.fetch_all(
            "SELECT * FROM fills ORDER BY filled_at"
        )

        # Get account snapshots
        snaps = await self._db.fetch_all(
            "SELECT * FROM account_snapshots ORDER BY taken_at"
        )

        if snaps:
            report.start_balance = snaps[0].get("total_balance", 0)
            report.current_balance = snaps[-1].get("total_balance", 0)
            report.total_pnl = report.current_balance - report.start_balance

        # Derive trades from orders (simplified: matching opens to closes)
        report.trades = self._derive_trades(orders, fills)

        # Compute metrics
        if report.trades:
            wins = [t for t in report.trades if t.pnl > 0]
            losses = [t for t in report.trades if t.pnl < 0]

            report.total_trades = len(report.trades)
            report.winning_trades = len(wins)
            report.losing_trades = len(losses)
            report.win_rate = len(wins) / len(report.trades) * 100 if report.trades else 0

            report.total_pnl = sum(t.pnl for t in report.trades)
            report.avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
            report.avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0

            total_wins = sum(t.pnl for t in wins) if wins else 0
            total_losses = abs(sum(t.pnl for t in losses)) if losses else 0
            report.profit_factor = total_wins / total_losses if total_losses else float("inf")

            report.max_drawdown_pct = self._calc_max_drawdown(report.trades)
            report.sharpe_ratio = self._calc_sharpe(report.trades)

        return report

    async def generate_summary(self) -> dict:
        """Generate a lightweight summary for Telegram / API."""
        report = await self.generate()
        return {
            "total_trades": report.total_trades,
            "win_rate": round(report.win_rate, 1),
            "total_pnl": round(report.total_pnl, 2),
            "profit_factor": round(report.profit_factor, 2) if report.profit_factor != float("inf") else None,
            "max_drawdown_pct": round(report.max_drawdown_pct, 1),
            "sharpe_ratio": round(report.sharpe_ratio, 2),
            "current_balance": round(report.current_balance, 2),
            "generated_at": report.generated_at,
        }

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _derive_trades(self, orders: list[dict], fills: list[dict]) -> list[TradeSummary]:
        """Derive completed trades from filled orders.

        Each FILLED order that has a counterpart = one round-trip trade.
        fills 表没有 symbol, 通过 order_id JOIN orders 获取.
        """
        # 建立 order_id -> order 的映射
        orders_by_id: dict[int, dict] = {}
        for o in orders:
            oid = o.get("id")
            if oid:
                orders_by_id[oid] = o

        # 按币种分组 fills
        fills_by_symbol: dict[str, list[dict]] = {}
        for f in fills:
            oid = f.get("order_id")
            order = orders_by_id.get(oid, {})
            sym = order.get("symbol", "")
            if sym:
                fills_by_symbol.setdefault(sym, []).append(f)

        trades = []
        for sym, sym_fills in fills_by_symbol.items():
            # Simple approach: every two fills = one round-trip trade
            for i in range(0, len(sym_fills) - 1, 2):
                entry = sym_fills[i]
                exit_ = sym_fills[i + 1]

                pnl = (exit_["price"] - entry["price"]) * entry["qty"]
                entry_price = entry["price"]
                exit_price = exit_["price"]

                pnl_pct = 0.0
                if entry_price > 0:
                    pnl_pct = (exit_price - entry_price) / entry_price * 100

                trades.append(TradeSummary(
                    symbol=sym,
                    side="",
                    entry_qty=entry.get("qty", 0),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    opened_at=entry.get("filled_at", ""),
                    closed_at=exit_.get("filled_at", ""),
                ))

        return trades

    @staticmethod
    def _calc_max_drawdown(trades: list[TradeSummary]) -> float:
        """Calculate maximum drawdown as a percentage from peak equity."""
        if not trades:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for t in trades:
            cumulative += t.pnl
            peak = max(peak, cumulative)
            if peak > 0:
                dd = (peak - cumulative) / peak * 100
                max_dd = max(max_dd, dd)

        return max_dd

    @staticmethod
    def _calc_sharpe(trades: list[TradeSummary]) -> float:
        """Estimate Sharpe ratio from trade P&L series (assuming risk-free=0)."""
        if len(trades) < 2:
            return 0.0

        pnls = [t.pnl_pct for t in trades]
        mean = sum(pnls) / len(pnls)

        variance = sum((x - mean) ** 2 for x in pnls) / len(pnls)
        std = math.sqrt(variance)

        if std == 0:
            return 0.0

        # Annualize assuming daily trading frequency (~365 periods/year)
        # For percentage returns per trade, use sqrt(365) scaling
        return (mean / std) * math.sqrt(365)
