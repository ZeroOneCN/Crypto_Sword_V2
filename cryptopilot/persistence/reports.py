"""Trading report generation from database records.

Computes: period P&L, win rate, max drawdown, trade list, Sharpe ratio,
fee breakdown, strategy performance, daily P&L series.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from cryptopilot.persistence.database import Database


@dataclass
class TradeSummary:
    """Single completed round-trip trade."""
    symbol: str
    side: str
    strategy: str
    entry_qty: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    fee: float
    opened_at: str
    closed_at: str


@dataclass
class FeeBreakdown:
    """Commission/funding fee summary."""
    total_commission: float = 0.0
    total_funding: float = 0.0  # from income history
    commission_asset: str = "USDT"
    by_symbol: dict[str, float] = field(default_factory=dict)


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
    fees: FeeBreakdown = field(default_factory=FeeBreakdown)
    trades: list[TradeSummary] = field(default_factory=list)
    daily_pnl: list[dict] = field(default_factory=list)  # [{date, pnl, trades}]
    strategies: dict[str, dict] = field(default_factory=dict)  # {name: {trades, pnl, win_rate}}
    period_days: int = 0
    generated_at: str = ""


class ReportGenerator:
    """Generates performance reports from the database with period filtering."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _where_clause(self, days: int | None) -> tuple[str, tuple]:
        """Build WHERE clause for date filtering. None = all-time."""
        if days is None:
            return "", ()
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
        return " WHERE f.filled_at >= ?", (cutoff,)

    async def generate(self, days: int | None = None) -> PerformanceReport:
        """Build a performance report. days=None for all-time."""
        report = PerformanceReport()
        report.period_days = days or 0
        report.generated_at = datetime.now(tz=timezone.utc).isoformat()

        where_sql, params = self._where_clause(days)

        # 成交明细 (JOIN fills + orders, 带策略名)
        fills = await self._db.fetch_all(
            f"""SELECT f.*, o.symbol, o.side, o.type AS order_type,
                       o.strategy_name, o.pos_side
                FROM fills f
                JOIN orders o ON o.id = f.order_id
                {where_sql}
                ORDER BY f.filled_at ASC""",
            params,
        )

        # 账户快照
        snaps = await self._db.fetch_all(
            "SELECT * FROM account_snapshots ORDER BY taken_at"
        )

        if snaps:
            report.start_balance = snaps[0].get("total_balance", 0)
            report.current_balance = snaps[-1].get("total_balance", 0)

        # 推导完整交易
        report.trades = self._derive_trades(fills)

        # ---- 指标计算 ----
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
            total_win_pnl = sum(t.pnl for t in wins) if wins else 0
            total_loss_pnl = abs(sum(t.pnl for t in losses)) if losses else 0
            report.profit_factor = total_win_pnl / total_loss_pnl if total_loss_pnl else float("inf")
            report.max_drawdown_pct = self._calc_max_drawdown(report.trades)
            report.sharpe_ratio = self._calc_sharpe(report.trades)

        # ---- 手续费统计 ----
        report.fees = self._calc_fees(fills)

        # ---- 每日盈亏序列 ----
        report.daily_pnl = self._calc_daily_pnl(report.trades)

        # ---- 策略绩效 ----
        report.strategies = self._calc_strategy_breakdown(report.trades)

        # 余额趋势法计算总盈亏 (更准确)
        if not report.total_pnl and snaps:
            if len(snaps) >= 2:
                first_bal = snaps[0].get("total_balance", 0)
                last_bal = snaps[-1].get("total_balance", 0)
                if first_bal > 0:
                    report.total_pnl = last_bal - first_bal
                    report.total_pnl_pct = (last_bal - first_bal) / first_bal * 100

        return report

    async def generate_summary(self, days: int | None = None) -> dict:
        """Lightweight summary for API."""
        report = await self.generate(days)
        return {
            "period_days": report.period_days,
            "total_trades": report.total_trades,
            "win_rate": round(report.win_rate, 1),
            "total_pnl": round(report.total_pnl, 2),
            "total_pnl_pct": round(report.total_pnl_pct, 2),
            "profit_factor": round(report.profit_factor, 2) if report.profit_factor != float("inf") else None,
            "max_drawdown_pct": round(report.max_drawdown_pct, 1),
            "sharpe_ratio": round(report.sharpe_ratio, 2),
            "current_balance": round(report.current_balance, 2),
            "start_balance": round(report.start_balance, 2),
            "total_commission": round(report.fees.total_commission, 4),
            "total_funding": round(report.fees.total_funding, 4),
            "strategies": report.strategies,
            "daily_pnl": report.daily_pnl[-30:] if report.daily_pnl else [],
            "generated_at": report.generated_at,
        }

    # ----------------------------------------------------------------
    # Trade derivation
    # ----------------------------------------------------------------

    def _derive_trades(self, fills: list[dict]) -> list[TradeSummary]:
        """从 fills 推导完整交易: 按币种分组, BUY→SELL 配对."""
        # 按 symbol 分组 (不按 strategy_name, 避免拆散配对)
        grouped: dict[str, list[dict]] = {}
        for f in fills:
            sym = f.get("symbol", "")
            grouped.setdefault(sym, []).append(f)

        trades = []
        for sym, sym_fills in grouped.items():
            i = 0
            while i < len(sym_fills) - 1:
                entry = sym_fills[i]
                # 找下一个反方向的成交
                found = False
                for j in range(i + 1, len(sym_fills)):
                    exit_ = sym_fills[j]
                    if entry.get("side") != exit_.get("side"):
                        # 计算本次交易的 PnL
                        ep = entry["price"]
                        xp = exit_["price"]
                        eq = entry["qty"]
                        xq = exit_["qty"]
                        fee = float(entry.get("commission", 0)) + float(exit_.get("commission", 0))

                        if entry.get("side") == "BUY":
                            pnl = (xp - ep) * min(eq, xq) - fee
                            pnl_pct = (xp - ep) / ep * 100 if ep > 0 else 0
                        else:
                            pnl = (ep - xp) * min(eq, xq) - fee
                            pnl_pct = (ep - xp) / ep * 100 if ep > 0 else 0

                        trades.append(TradeSummary(
                            symbol=sym,
                            side=entry.get("side", ""),
                            strategy=entry.get("strategy_name", ""),
                            entry_qty=eq,
                            entry_price=ep,
                            exit_price=xp,
                            pnl=round(pnl, 8),
                            pnl_pct=round(pnl_pct, 4),
                            fee=round(fee, 8),
                            opened_at=entry.get("filled_at", ""),
                            closed_at=exit_.get("filled_at", ""),
                        ))
                        i = j + 1
                        found = True
                        break
                if not found:
                    break

        return trades

    # ----------------------------------------------------------------
    # Fee breakdown
    # ----------------------------------------------------------------

    def _calc_fees(self, fills: list[dict]) -> FeeBreakdown:
        """从 fills 汇总手续费."""
        fb = FeeBreakdown()
        by_sym: dict[str, float] = {}
        for f in fills:
            comm = float(f.get("commission", 0))
            asset = f.get("commission_asset", "")
            fb.total_commission += comm
            if asset and asset != fb.commission_asset:
                fb.commission_asset = asset  # track most recent non-empty
            sym = f.get("symbol", "")
            by_sym[sym] = by_sym.get(sym, 0) + comm
        fb.by_symbol = {k: round(v, 6) for k, v in sorted(by_sym.items(), key=lambda x: -x[1])[:10]}
        fb.total_commission = round(fb.total_commission, 6)
        return fb

    # ----------------------------------------------------------------
    # Daily PnL
    # ----------------------------------------------------------------

    @staticmethod
    def _calc_daily_pnl(trades: list[TradeSummary]) -> list[dict]:
        """聚合每日盈亏."""
        daily: dict[str, dict] = {}
        for t in trades:
            date = t.closed_at[:10] if t.closed_at else ""
            if not date:
                continue
            d = daily.setdefault(date, {"date": date, "pnl": 0.0, "trades": 0, "fee": 0.0})
            d["pnl"] += t.pnl
            d["trades"] += 1
            d["fee"] += t.fee
        return sorted(daily.values(), key=lambda x: x["date"])

    # ----------------------------------------------------------------
    # Strategy breakdown
    # ----------------------------------------------------------------

    @staticmethod
    def _calc_strategy_breakdown(trades: list[TradeSummary]) -> dict[str, dict]:
        """按策略聚合绩效."""
        strat: dict[str, dict] = {}
        for t in trades:
            name = t.strategy or "unknown"
            s = strat.setdefault(name, {"trades": 0, "pnl": 0.0, "win": 0, "loss": 0, "fee": 0.0})
            s["trades"] += 1
            s["pnl"] += t.pnl
            s["fee"] += t.fee
            if t.pnl > 0:
                s["win"] += 1
            elif t.pnl < 0:
                s["loss"] += 1
        for _, v in strat.items():
            v["pnl"] = round(v["pnl"], 4)
            v["fee"] = round(v["fee"], 4)
            v["win_rate"] = round(v["win"] / v["trades"] * 100, 1) if v["trades"] else 0
        return strat

    # ----------------------------------------------------------------
    # Risk metrics
    # ----------------------------------------------------------------

    @staticmethod
    def _calc_max_drawdown(trades: list[TradeSummary]) -> float:
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
        if len(trades) < 2:
            return 0.0
        pnls = [t.pnl_pct for t in trades]
        mean = sum(pnls) / len(pnls)
        variance = sum((x - mean) ** 2 for x in pnls) / len(pnls)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(365)
