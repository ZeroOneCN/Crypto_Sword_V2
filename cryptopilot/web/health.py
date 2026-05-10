"""FastAPI health check, monitoring, and report endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse


# 全局信号日志 (环形缓冲区, 最多保留 200 条)
_signal_log: list[dict] = []
_MAX_SIGNAL_LOG = 200


def add_signal_log(entry: dict) -> None:
    """向全局信号日志追加一条记录."""
    _signal_log.append(entry)
    if len(_signal_log) > _MAX_SIGNAL_LOG:
        _signal_log[:50] = []  # 批量裁剪, 避免 O(n) 弹出


# Binance income 缓存 (直接拉取盈亏数据, 与交易所显示一致)
_income_cache: dict = {"data": None, "time": 0, "ttl": 120}  # 2 分钟缓存


async def _fetch_income_pnl(order_executor) -> dict | None:
    """从 Binance income API 拉取盈亏汇总 (分页拉全, 与交易所一致)."""
    import time as _time
    now = _time.time()
    if _income_cache["data"] and (now - _income_cache["time"]) < _income_cache["ttl"]:
        return _income_cache["data"]

    # 分页拉取全部 income 记录 (每次 1000 条, 最多拉 10 页)
    all_incomes = []
    end = int(now * 1000)
    start = end - 90 * 86400000
    try:
        for _ in range(10):
            batch = await order_executor.get_income_history(
                start_time=start, end_time=end, limit=1000,
            )
            if not batch:
                break
            all_incomes.extend(batch)
            if len(batch) < 1000:
                break  # 最后一页
            # 下一页: end = 最旧那条的时间 - 1ms
            end = min(i.time for i in batch) - 1
    except Exception:
        if _income_cache.get("data"):
            return _income_cache["data"]
        return None

    if not all_incomes:
        return None

    result = {
        "total_realized_pnl": 0.0,
        "total_commission": 0.0,
        "total_funding": 0.0,
        "realized_pnl_7d": 0.0,
        "commission_7d": 0.0,
        "funding_7d": 0.0,
        "realized_pnl_30d": 0.0,
        "commission_30d": 0.0,
        "funding_30d": 0.0,
        "realized_pnl_1d": 0.0,
        "commission_1d": 0.0,
        "funding_1d": 0.0,
        # 含手续费净盈亏 = Binance 显示的数据
        "net_pnl_7d": 0.0,
        "net_pnl_30d": 0.0,
        "net_pnl_total": 0.0,
        "net_pnl_1d": 0.0,
        "trade_count_7d": 0,
        "trade_count_30d": 0,
        "symbols_traded": set(),
        "total_events": len(all_incomes),
    }

    cutoff_1d = now - 86400
    cutoff_7d = now - 7 * 86400
    cutoff_30d = now - 30 * 86400

    for i in all_incomes:
        t = i.time / 1000
        if i.income_type == "REALIZED_PNL":
            result["total_realized_pnl"] += i.income
            if t >= cutoff_30d:
                result["realized_pnl_30d"] += i.income
                result["net_pnl_30d"] += i.income
                if i.symbol:
                    result["symbols_traded"].add(i.symbol)
                result["trade_count_30d"] += 1
            if t >= cutoff_7d:
                result["realized_pnl_7d"] += i.income
                result["net_pnl_7d"] += i.income
                result["trade_count_7d"] += 1
            if t >= cutoff_1d:
                result["realized_pnl_1d"] += i.income
                result["net_pnl_1d"] += i.income
            result["net_pnl_total"] += i.income
        elif i.income_type == "COMMISSION":
            result["total_commission"] += i.income
            if t >= cutoff_7d:
                result["commission_7d"] += i.income
                result["net_pnl_7d"] += i.income
            if t >= cutoff_30d:
                result["commission_30d"] += i.income
                result["net_pnl_30d"] += i.income
            if t >= cutoff_1d:
                result["commission_1d"] += i.income
                result["net_pnl_1d"] += i.income
            result["net_pnl_total"] += i.income
        elif i.income_type == "FUNDING_FEE":
            result["total_funding"] += i.income
            if t >= cutoff_7d:
                result["funding_7d"] += i.income
                result["net_pnl_7d"] += i.income
            if t >= cutoff_30d:
                result["funding_30d"] += i.income
                result["net_pnl_30d"] += i.income
            if t >= cutoff_1d:
                result["funding_1d"] += i.income
                result["net_pnl_1d"] += i.income
            result["net_pnl_total"] += i.income

    result["symbols_traded"] = len(result["symbols_traded"])

    for k in list(result.keys()):
        if isinstance(result[k], float):
            result[k] = round(result[k], 4)

    _income_cache["data"] = result
    _income_cache["time"] = now
    return result


def create_health_app(
    strategy_engine=None,
    position_manager=None,
    websocket_manager=None,
    circuit_breaker=None,
    notifier=None,
    db=None,
    report_generator=None,
    margin_monitor=None,
    candidate_pool=None,
    scoring_engine=None,
    order_executor=None,
) -> FastAPI:
    """Build the FastAPI app with injected dependencies."""

    app = FastAPI(title="CryptoPilot Health", version="0.1.0", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health():
        """Main health check — returns overall system status."""
        ws_connected = websocket_manager.is_connected if websocket_manager else False
        cb_tripped = circuit_breaker.tripped if circuit_breaker else False

        ok = ws_connected and not cb_tripped
        status = "ok" if ok else "degraded"

        return {
            "status": status,
            "version": "0.1.0",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "websocket_connected": ws_connected,
            "circuit_breaker_tripped": cb_tripped,
        }

    @app.get("/health/strategies")
    async def health_strategies():
        """Return per-strategy status."""
        if strategy_engine is None:
            return {"error": "Strategy engine not available"}
        return {
            "total": strategy_engine.total_count,
            "active": strategy_engine.active_count,
            "strategies": strategy_engine.get_status(),
        }

    @app.get("/health/positions")
    async def health_positions():
        """Return current open positions."""
        if position_manager is None:
            return {"error": "Position manager not available"}
        return {
            "count": position_manager.position_count,
            "positions": position_manager.get_all_positions(),
        }

    @app.get("/health/circuit")
    async def health_circuit():
        """Return circuit breaker state."""
        if circuit_breaker is None:
            return {"error": "Circuit breaker not available"}
        return {
            "tripped": circuit_breaker.tripped,
            "daily_pnl": circuit_breaker.daily_pnl,
        }

    @app.get("/health/margin")
    async def health_margin():
        """Return margin monitoring status."""
        if margin_monitor is None:
            return {"error": "Margin monitor not available"}
        return {
            "running": margin_monitor._running,
            "warning_threshold": margin_monitor._warning,
            "critical_threshold": margin_monitor._critical,
        }

    @app.get("/health/report")
    async def health_report():
        """Return full trading performance report."""
        if report_generator is None:
            return {"error": "Report generator not available"}
        report = await report_generator.generate()
        return {
            "total_trades": report.total_trades,
            "winning_trades": report.winning_trades,
            "losing_trades": report.losing_trades,
            "win_rate": round(report.win_rate, 1),
            "total_pnl": round(report.total_pnl, 2),
            "total_pnl_pct": round(report.total_pnl_pct, 2),
            "avg_win": round(report.avg_win, 2),
            "avg_loss": round(report.avg_loss, 2),
            "profit_factor": round(report.profit_factor, 2) if report.profit_factor != float("inf") else None,
            "max_drawdown_pct": round(report.max_drawdown_pct, 1),
            "sharpe_ratio": round(report.sharpe_ratio, 2),
            "start_balance": round(report.start_balance, 2),
            "current_balance": round(report.current_balance, 2),
            "trades": [
                {
                    "symbol": t.symbol,
                    "entry_price": round(t.entry_price, 4),
                    "exit_price": round(t.exit_price, 4),
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 2),
                    "opened_at": t.opened_at,
                }
                for t in report.trades[-20:]  # Last 20 trades
            ],
            "generated_at": report.generated_at,
        }

    @app.get("/health/report/summary")
    async def health_report_summary():
        """Return lightweight performance summary (all-time)."""
        if report_generator is None:
            return {"error": "Report generator not available"}
        return await report_generator.generate_summary()

    @app.get("/health/report/today")
    async def health_report_today():
        """今日绩效."""
        if report_generator is None:
            return {"error": "Report generator not available"}
        return await report_generator.generate_summary(days=1)

    @app.get("/health/report/7d")
    async def health_report_7d():
        """近7天绩效."""
        if report_generator is None:
            return {"error": "Report generator not available"}
        return await report_generator.generate_summary(days=7)

    @app.get("/health/report/30d")
    async def health_report_30d():
        """近30天绩效."""
        if report_generator is None:
            return {"error": "Report generator not available"}
        return await report_generator.generate_summary(days=30)

    @app.get("/health/candidates")
    async def health_candidates():
        """候选池快照."""
        if candidate_pool is None:
            return {"error": "候选池不可用"}
        candidates = await candidate_pool.get_all()
        return {
            "total": len(candidates),
            "candidates": [
                {
                    "symbol": c.symbol,
                    "price": round(c.current_price, 4),
                    "change_24h": round(c.change_24h_pct, 2),
                    "volume_ratio": round(c.volume_ratio, 1),
                    "oi_change": round(c.oi_change_pct, 1),
                    "funding_rate": f"{c.funding_rate*100:.4f}%",
                    "score": round(c.scanner_score, 1),
                    "reasons": c.scrape_reasons,
                }
                for c in candidates
            ],
        }

    @app.get("/health/scoring/{symbol}")
    async def health_scoring(symbol: str):
        """对指定币种实时评分."""
        if candidate_pool is None:
            return {"error": "候选池不可用"}
        # 从候选池中获取该币种
        candidates = await candidate_pool.get_all()
        target = None
        for c in candidates:
            if c.symbol.upper() == symbol.upper():
                target = c
                break
        if target is None:
            return {"error": f"候选池中未找到 {symbol}"}

        # 这里需要 scoring_engine, 但目前未暴露到 health app
        # 返回候选的基本数据供前端展示
        return {
            "symbol": symbol.upper(),
            "price": round(target.current_price, 4),
            "change_24h": round(target.change_24h_pct, 2),
            "volume_ratio": round(target.volume_ratio, 1),
            "oi_change": round(target.oi_change_pct, 1),
            "funding_rate": f"{target.funding_rate*100:.4f}%",
            "mark_price": round(target.mark_price, 4),
            "scanner_score": round(target.scanner_score, 1),
            "reasons": target.scrape_reasons,
        }

    @app.get("/health/pnl")
    async def health_pnl():
        """Binance 权威盈亏数据 (income API, 与交易所显示一致)."""
        if order_executor is None:
            return {"error": "订单执行器不可用"}
        data = await _fetch_income_pnl(order_executor)
        if data is None:
            return {"error": "无法获取盈亏数据"}
        return data

    @app.get("/health/account")
    async def health_account():
        """实时账户数据."""
        if order_executor is None:
            return {"error": "订单执行器不可用"}
        try:
            acct = await order_executor.get_account_info()
            return {
                "total_balance": round(acct.total_balance, 2),
                "available_balance": round(acct.available_balance, 2),
                "unrealized_pnl": round(acct.unrealized_pnl, 2),
                "margin_ratio": round(acct.margin_ratio, 4),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"error": f"获取账户信息失败: {exc}"}

    @app.get("/health/fees")
    async def health_fees():
        """手续费统计 (不同周期)."""
        if db is None:
            return {"error": "数据库不可用"}
        try:
            # All-time
            all_rows = await db.fetch_all("""
                SELECT f.commission, f.commission_asset, o.symbol
                FROM fills f JOIN orders o ON o.id = f.order_id
            """)
            total_commission = sum(float(r.get("commission", 0)) for r in all_rows)
            by_symbol: dict[str, float] = {}
            for r in all_rows:
                sym = r.get("symbol", "unknown")
                by_symbol[sym] = by_symbol.get(sym, 0) + float(r.get("commission", 0))

            # Past 7 days
            from datetime import datetime as dt, timezone as tz, timedelta
            cutoff = (dt.now(tz=tz.utc) - timedelta(days=7)).isoformat()
            rows7 = await db.fetch_all(
                """SELECT f.commission FROM fills f
                   WHERE f.filled_at >= ?""", (cutoff,),
            )
            comm_7d = sum(float(r.get("commission", 0)) for r in rows7)

            return {
                "total_commission": round(total_commission, 6),
                "commission_7d": round(comm_7d, 6),
                "by_symbol": {k: round(v, 6) for k, v in sorted(by_symbol.items(), key=lambda x: -x[1])[:10]},
            }
        except Exception as exc:
            return {"error": str(exc)}

    @app.get("/health/trades")
    async def health_trades():
        """返回最近成交记录 (JOIN fills + orders)."""
        if db is None:
            return {"error": "数据库不可用"}
        try:
            rows = await db.fetch_all("""
                SELECT o.symbol, o.side, o.type, o.pos_side,
                       f.price, f.qty, f.commission, f.commission_asset, f.filled_at
                FROM fills f
                JOIN orders o ON o.id = f.order_id
                ORDER BY f.filled_at DESC
                LIMIT 50
            """)
            return {"total": len(rows), "trades": [dict(r) for r in rows]}
        except Exception as exc:
            return {"error": str(exc)}

    @app.get("/health/signals")
    async def health_signals():
        """返回最近信号日志."""
        return {"total": len(_signal_log), "signals": list(_signal_log[-50:])}

    @app.get("/health/scoring-detail")
    async def health_scoring_detail():
        """返回候选池 Top-K 的因子评分明细."""
        if candidate_pool is None:
            return {"error": "候选池不可用"}
        candidates = await candidate_pool.get_all()
        if not candidates:
            return {"candidates": []}

        result = []
        for cand in sorted(candidates, key=lambda c: c.scanner_score, reverse=True)[:5]:
            factors_info = []
            if scoring_engine:
                try:
                    sr = scoring_engine.score(cand)
                    factors_info = [
                        {
                            "name": fs.name,
                            "score": fs.score,
                            "weight": fs.weight,
                            "direction": fs.direction,
                            "detail": fs.detail,
                        }
                        for fs in sr.factors
                    ]
                except Exception:
                    pass
            result.append({
                "symbol": cand.symbol,
                "price": round(cand.current_price, 4),
                "change_24h": round(cand.change_24h_pct, 2),
                "scanner_score": round(cand.scanner_score, 1),
                "factors": factors_info,
            })
        return {"candidates": result}

    @app.exception_handler(Exception)
    async def generic_handler(request, exc):
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)},
        )

    return app
