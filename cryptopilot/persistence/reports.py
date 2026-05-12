"""Trading report generation from persisted position and fill records."""

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
    hold_seconds: float = 0.0
    entry_reason: str = ""
    exit_reason: str = ""
    tp_tiers_hit: list[str] = field(default_factory=list)


@dataclass
class FeeBreakdown:
    """Commission/funding fee summary."""

    total_commission: float = 0.0
    total_funding: float = 0.0
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
    avg_hold_time_seconds: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    start_balance: float = 0.0
    current_balance: float = 0.0
    fees: FeeBreakdown = field(default_factory=FeeBreakdown)
    trades: list[TradeSummary] = field(default_factory=list)
    daily_pnl: list[dict] = field(default_factory=list)
    strategies: dict[str, dict] = field(default_factory=dict)
    period_days: int = 0
    generated_at: str = ""


class ReportGenerator:
    """Generates performance reports from the database with period filtering."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _period_cutoff(self, days: int | None) -> str | None:
        if days is None:
            return None
        return (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()

    async def generate(self, days: int | None = None) -> PerformanceReport:
        """Build a performance report. days=None for all-time."""

        report = PerformanceReport()
        report.period_days = days or 0
        report.generated_at = datetime.now(tz=timezone.utc).isoformat()

        cutoff = self._period_cutoff(days)
        report.trades = await self._load_closed_trades(cutoff)

        snaps = await self._db.fetch_all(
            "SELECT * FROM account_snapshots ORDER BY taken_at"
        )
        if snaps:
            report.start_balance = snaps[0].get("total_balance", 0)
            report.current_balance = snaps[-1].get("total_balance", 0)

        if report.trades:
            wins = [t for t in report.trades if t.pnl > 0]
            losses = [t for t in report.trades if t.pnl < 0]

            report.total_trades = len(report.trades)
            report.winning_trades = len(wins)
            report.losing_trades = len(losses)
            report.win_rate = len(wins) / len(report.trades) * 100 if report.trades else 0.0
            report.total_pnl = sum(t.pnl for t in report.trades)
            report.avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
            report.avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0
            total_win_pnl = sum(t.pnl for t in wins)
            total_loss_pnl = abs(sum(t.pnl for t in losses))
            report.profit_factor = total_win_pnl / total_loss_pnl if total_loss_pnl else float("inf")
            report.avg_hold_time_seconds = (
                sum(t.hold_seconds for t in report.trades) / len(report.trades)
                if report.trades else 0.0
            )
            report.max_drawdown_pct = self._calc_max_drawdown(report.trades)
            report.sharpe_ratio = self._calc_sharpe(report.trades)

        report.fees = self._calc_fees(report.trades)
        report.daily_pnl = self._calc_daily_pnl(report.trades)
        report.strategies = self._calc_strategy_breakdown(report.trades)

        if not report.total_pnl and snaps and len(snaps) >= 2:
            first_bal = snaps[0].get("total_balance", 0)
            last_bal = snaps[-1].get("total_balance", 0)
            if first_bal > 0:
                report.total_pnl = last_bal - first_bal
                report.total_pnl_pct = (last_bal - first_bal) / first_bal * 100
        elif report.start_balance > 0:
            report.total_pnl_pct = report.total_pnl / report.start_balance * 100

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
            "avg_win": round(report.avg_win, 2),
            "avg_loss": round(report.avg_loss, 2),
            "avg_hold_time_seconds": round(report.avg_hold_time_seconds, 1),
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

    async def _load_closed_trades(self, cutoff: str | None) -> list[TradeSummary]:
        """Load closed trades from archived position history with fill-fee enrichment."""

        sql = """
            SELECT p.*,
                   COALESCE((
                       SELECT o.strategy_name
                       FROM orders o
                       WHERE o.symbol = p.symbol AND o.strategy_name != ''
                       ORDER BY o.created_at DESC, o.id DESC
                       LIMIT 1
                   ), '') AS fallback_strategy_name
            FROM position_history p
            WHERE p.exit_time != ''
        """
        params: list = []
        if cutoff:
            sql += " AND p.exit_time >= ?"
            params.append(cutoff)
        sql += " ORDER BY p.exit_time ASC, p.id ASC"

        rows = await self._db.fetch_all(sql, tuple(params))
        fees = await self._fee_by_symbol_and_window()
        events = await self._event_summary_by_symbol()

        trades: list[TradeSummary] = []
        for row in rows:
            created_at = str(row.get("created_at", "") or "")
            exit_time = str(row.get("exit_time", "") or "")
            hold_seconds = self._hold_seconds(created_at, exit_time)
            strategy = (
                str(row.get("strategy_preset", "") or "")
                or self._strategy_from_entry_reason(str(row.get("entry_reason", "") or ""))
                or str(row.get("fallback_strategy_name", "") or "")
                or "unknown"
            )
            event_meta = events.get((row.get("symbol", ""), exit_time), {})
            tp_tiers_hit = self._tiers_from_position_row(row) or event_meta.get("tp_tiers_hit", [])
            trades.append(TradeSummary(
                symbol=str(row.get("symbol", "") or ""),
                side=str(row.get("side", "") or ""),
                strategy=strategy,
                entry_qty=float(row.get("initial_qty", row.get("qty", 0)) or 0),
                entry_price=float(row.get("entry_price", 0) or 0),
                exit_price=float(row.get("exit_price", 0) or 0),
                pnl=round(float(row.get("pnl", 0) or 0), 8),
                pnl_pct=round(float(row.get("pnl_pct", 0) or 0), 4),
                fee=round(self._estimate_fee(fees, row.get("symbol", ""), created_at, exit_time), 8),
                opened_at=created_at,
                closed_at=exit_time,
                hold_seconds=hold_seconds,
                entry_reason=str(row.get("entry_reason", "") or ""),
                exit_reason=str(row.get("exit_reason", "") or ""),
                tp_tiers_hit=tp_tiers_hit,
            ))
        return trades

    async def _fee_by_symbol_and_window(self) -> dict[str, list[dict]]:
        rows = await self._db.fetch_all(
            """
            SELECT o.symbol, f.commission, f.filled_at
            FROM fills f
            JOIN orders o ON o.id = f.order_id
            ORDER BY f.filled_at ASC
            """
        )
        bucket: dict[str, list[dict]] = {}
        for row in rows:
            bucket.setdefault(str(row.get("symbol", "") or ""), []).append({
                "filled_at": str(row.get("filled_at", "") or ""),
                "commission": float(row.get("commission", 0) or 0),
            })
        return bucket

    async def _event_summary_by_symbol(self) -> dict[tuple[str, str], dict]:
        rows = await self._db.fetch_all(
            """
            SELECT symbol, event_type, details, created_at
            FROM strategy_events
            WHERE event_type IN ('partial_take_profit', 'position_closed')
            ORDER BY created_at ASC, id ASC
            """
        )
        summary: dict[tuple[str, str], dict] = {}
        for row in rows:
            symbol = str(row.get("symbol", "") or "")
            created_at = str(row.get("created_at", "") or "")
            key = (symbol, created_at) if row.get("event_type") == "position_closed" else None
            details = str(row.get("details", "") or "")
            tier_hits: list[str] = []
            if "TP1" in details:
                tier_hits.append("TP1")
            if "TP2" in details:
                tier_hits.append("TP2")
            if "TP3" in details:
                tier_hits.append("TP3")
            if row.get("event_type") == "position_closed":
                summary[key] = {"tp_tiers_hit": tier_hits}
        return summary

    def _estimate_fee(self, fees: dict[str, list[dict]], symbol: str, opened_at: str, closed_at: str) -> float:
        rows = fees.get(symbol, [])
        if not rows:
            return 0.0
        opened = self._parse_dt(opened_at)
        closed = self._parse_dt(closed_at)
        if opened is None or closed is None:
            return 0.0
        total = 0.0
        for row in rows:
            filled = self._parse_dt(row["filled_at"])
            if filled is None:
                continue
            if opened <= filled <= closed:
                total += float(row["commission"])
        return total

    @staticmethod
    def _tiers_from_position_row(row: dict) -> list[str]:
        raw = str(row.get("tp_tiers_filled", "") or "").strip()
        if not raw:
            return []
        tiers: list[str] = []
        for part in raw.split(","):
            token = part.strip().upper().replace("TP", "")
            if token in {"1", "2", "3"}:
                tiers.append(f"TP{token}")
        return tiers

    @staticmethod
    def _strategy_from_entry_reason(entry_reason: str) -> str:
        if entry_reason.startswith("preset:"):
            preset_part, _, _ = entry_reason.partition("|")
            return preset_part.replace("preset:", "", 1).strip()
        return ""

    @staticmethod
    def _parse_dt(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _hold_seconds(self, opened_at: str, closed_at: str) -> float:
        opened = self._parse_dt(opened_at)
        closed = self._parse_dt(closed_at)
        if opened is None or closed is None:
            return 0.0
        return max((closed - opened).total_seconds(), 0.0)

    def _calc_fees(self, trades: list[TradeSummary]) -> FeeBreakdown:
        fb = FeeBreakdown()
        by_symbol: dict[str, float] = {}
        for trade in trades:
            fb.total_commission += trade.fee
            by_symbol[trade.symbol] = by_symbol.get(trade.symbol, 0.0) + trade.fee
        fb.by_symbol = {k: round(v, 6) for k, v in sorted(by_symbol.items(), key=lambda x: -x[1])[:10]}
        fb.total_commission = round(fb.total_commission, 6)
        return fb

    @staticmethod
    def _calc_daily_pnl(trades: list[TradeSummary]) -> list[dict]:
        daily: dict[str, dict] = {}
        for trade in trades:
            date = trade.closed_at[:10] if trade.closed_at else ""
            if not date:
                continue
            row = daily.setdefault(date, {"date": date, "pnl": 0.0, "trades": 0, "fee": 0.0})
            row["pnl"] += trade.pnl
            row["trades"] += 1
            row["fee"] += trade.fee
        return sorted(daily.values(), key=lambda item: item["date"])

    @staticmethod
    def _format_hold_time(avg_seconds: float) -> str:
        seconds = int(max(avg_seconds, 0))
        if seconds <= 0:
            return "0m"
        minutes, _ = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}m"
        hours, minutes = divmod(minutes, 60)
        if hours < 24:
            return f"{hours}h{minutes:02d}m"
        days, hours = divmod(hours, 24)
        return f"{days}d{hours:02d}h"

    @classmethod
    def _calc_strategy_breakdown(cls, trades: list[TradeSummary]) -> dict[str, dict]:
        strat: dict[str, dict] = {}
        for trade in trades:
            name = trade.strategy or "unknown"
            item = strat.setdefault(name, {
                "trades": 0,
                "pnl": 0.0,
                "fee": 0.0,
                "win": 0,
                "loss": 0,
                "wins": [],
                "losses": [],
                "hold_seconds_total": 0.0,
                "exit_reason_breakdown": {},
                "tp_hits": {"TP1": 0, "TP2": 0, "TP3": 0},
            })
            item["trades"] += 1
            item["pnl"] += trade.pnl
            item["fee"] += trade.fee
            item["hold_seconds_total"] += trade.hold_seconds
            if trade.pnl > 0:
                item["win"] += 1
                item["wins"].append(trade.pnl)
            elif trade.pnl < 0:
                item["loss"] += 1
                item["losses"].append(trade.pnl)
            reason = trade.exit_reason or "unknown"
            item["exit_reason_breakdown"][reason] = item["exit_reason_breakdown"].get(reason, 0) + 1
            for tier in trade.tp_tiers_hit:
                if tier in item["tp_hits"]:
                    item["tp_hits"][tier] += 1

        for name, item in strat.items():
            wins = item.pop("wins")
            losses = item.pop("losses")
            total_win_pnl = sum(wins)
            total_loss_pnl = abs(sum(losses))
            item["pnl"] = round(item["pnl"], 4)
            item["fee"] = round(item["fee"], 4)
            item["win_rate"] = round(item["win"] / item["trades"] * 100, 1) if item["trades"] else 0.0
            item["avg_hold_time_seconds"] = round(item["hold_seconds_total"] / item["trades"], 1) if item["trades"] else 0.0
            item["avg_hold_time"] = cls._format_hold_time(item["avg_hold_time_seconds"])
            item["avg_win"] = round(sum(wins) / len(wins), 4) if wins else 0.0
            item["avg_loss"] = round(sum(losses) / len(losses), 4) if losses else 0.0
            item["profit_factor"] = round(total_win_pnl / total_loss_pnl, 2) if total_loss_pnl else None
            item["hold_seconds_total"] = round(item["hold_seconds_total"], 1)
        return strat

    @staticmethod
    def _calc_max_drawdown(trades: list[TradeSummary]) -> float:
        if not trades:
            return 0.0
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for trade in trades:
            cumulative += trade.pnl
            peak = max(peak, cumulative)
            if peak > 0:
                dd = (peak - cumulative) / peak * 100
                max_dd = max(max_dd, dd)
        return max_dd

    @staticmethod
    def _calc_sharpe(trades: list[TradeSummary]) -> float:
        if len(trades) < 2:
            return 0.0
        pnls = [trade.pnl_pct for trade in trades]
        mean = sum(pnls) / len(pnls)
        variance = sum((x - mean) ** 2 for x in pnls) / len(pnls)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(365)
