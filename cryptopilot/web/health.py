"""FastAPI health check, monitoring, and report endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from functools import wraps

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger


# ---- 简易 TTL 缓存 (避免仪表盘刷新狂打 REST API) ----
_ttl_cache: dict[str, tuple[float, object]] = {}

def _cached(ttl: float):
    """装饰器: 返回值缓存 ttl 秒."""
    def deco(fn):
        @wraps(fn)
        async def wrapper(*a, **kw):
            key = fn.__name__
            now = time.time()
            if key in _ttl_cache and (now - _ttl_cache[key][0]) < ttl:
                return _ttl_cache[key][1]
            result = await fn(*a, **kw)
            _ttl_cache[key] = (now, result)
            return result
        return wrapper
    return deco


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


def _parse_iso_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _recent_trade_symbols(db=None, position_manager=None, limit: int = 8) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()

    def _add(symbol: str | None) -> None:
        text = str(symbol or "").upper().strip()
        if not text or text in seen:
            return
        seen.add(text)
        symbols.append(text)

    if position_manager is not None:
        try:
            for pos in position_manager.get_all_positions():
                _add(pos.get("symbol"))
        except Exception:
            pass

    if db is not None:
        try:
            for row in await db.fetch_all(
                "SELECT symbol FROM orders ORDER BY created_at DESC LIMIT 60"
            ):
                _add(row.get("symbol"))
        except Exception:
            pass
        try:
            for row in await db.fetch_all(
                "SELECT symbol FROM positions ORDER BY updated_at DESC LIMIT 30"
            ):
                _add(row.get("symbol"))
        except Exception:
            pass

    return symbols[:limit]


async def _recent_order_strategy_map(db=None, limit: int = 500) -> dict[str, dict]:
    if db is None:
        return {}

    try:
        rows = await db.fetch_all(
            """
            SELECT exchange_order_id, strategy_name, side, type, symbol, created_at
            FROM orders
            WHERE exchange_order_id IS NOT NULL AND exchange_order_id != ''
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    except Exception:
        return {}

    mapping: dict[str, dict] = {}
    for row in rows:
        exchange_order_id = str(row.get("exchange_order_id", "") or "").strip()
        if not exchange_order_id or exchange_order_id in mapping:
            continue
        mapping[exchange_order_id] = dict(row)
    return mapping


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
        "trade_count_1d": 0,
        "trade_count_7d": 0,
        "trade_count_30d": 0,
        "winning_trades_1d": 0,
        "losing_trades_1d": 0,
        "winning_trades_7d": 0,
        "losing_trades_7d": 0,
        "winning_trades_30d": 0,
        "losing_trades_30d": 0,
        "symbols_traded": set(),
        "total_events": len(all_incomes),
    }

    cutoff_1d = now - 86400
    cutoff_7d = now - 7 * 86400
    cutoff_30d = now - 30 * 86400

    for i in all_incomes:
        t = i.time / 1000
        if i.income_type == "REALIZED_PNL":
            is_win = i.income > 0
            is_loss = i.income < 0
            result["total_realized_pnl"] += i.income
            if t >= cutoff_30d:
                result["realized_pnl_30d"] += i.income
                result["net_pnl_30d"] += i.income
                if i.symbol:
                    result["symbols_traded"].add(i.symbol)
                result["trade_count_30d"] += 1
                if is_win:
                    result["winning_trades_30d"] += 1
                elif is_loss:
                    result["losing_trades_30d"] += 1
            if t >= cutoff_7d:
                result["realized_pnl_7d"] += i.income
                result["net_pnl_7d"] += i.income
                result["trade_count_7d"] += 1
                if is_win:
                    result["winning_trades_7d"] += 1
                elif is_loss:
                    result["losing_trades_7d"] += 1
            if t >= cutoff_1d:
                result["realized_pnl_1d"] += i.income
                result["net_pnl_1d"] += i.income
                result["trade_count_1d"] += 1
                if is_win:
                    result["winning_trades_1d"] += 1
                elif is_loss:
                    result["losing_trades_1d"] += 1
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

    # ---- 合并未实现盈亏 (Unrealized PnL) 与百分比 ----
    # 币安官网显示的是 已实现+未实现 的总盈亏，而 income API 只有已实现
    try:
        acct = await order_executor.get_account_info()
        unrealized = acct.unrealized_pnl or 0.0
        wallet_balance = acct.total_balance or 0.0
        total_equity = wallet_balance + unrealized  # 当前总权益
    except Exception:
        unrealized = 0.0
        wallet_balance = 0.0
        total_equity = 0.0

    result["unrealized_pnl"] = round(unrealized, 4)
    result["wallet_balance"] = round(wallet_balance, 2)
    result["total_equity"] = round(total_equity, 2)

    # 含未实现的总净盈亏 (与币安官网对齐)
    total_net = result["net_pnl_total"] + unrealized
    result["total_net_pnl"] = round(total_net, 4)

    # 百分比: net / (当前权益 - net) ≈ 相对期间初资金的回报率
    # 累计: 含未实现盈亏 (币安官网标准)
    # 7d/30d/1d: 仅已实现 (无法拆分历史未实现盈亏)
    def _pct(net: float) -> float | None:
        denom = total_equity - net
        if denom and abs(denom) > 0.001:
            return round(net / denom * 100, 2)
        return None

    result["net_pnl_1d_pct"] = _pct(result["net_pnl_1d"])
    result["net_pnl_7d_pct"] = _pct(result["net_pnl_7d"])
    result["net_pnl_30d_pct"] = _pct(result["net_pnl_30d"])
    result["net_pnl_total_pct"] = _pct(total_net)
    result["win_rate_1d"] = round(
        result["winning_trades_1d"] / (result["winning_trades_1d"] + result["losing_trades_1d"]) * 100,
        1,
    ) if (result["winning_trades_1d"] + result["losing_trades_1d"]) > 0 else 0.0
    result["win_rate_7d"] = round(
        result["winning_trades_7d"] / (result["winning_trades_7d"] + result["losing_trades_7d"]) * 100,
        1,
    ) if (result["winning_trades_7d"] + result["losing_trades_7d"]) > 0 else 0.0
    result["win_rate_30d"] = round(
        result["winning_trades_30d"] / (result["winning_trades_30d"] + result["losing_trades_30d"]) * 100,
        1,
    ) if (result["winning_trades_30d"] + result["losing_trades_30d"]) > 0 else 0.0

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
    scanner=None,
    preset_name: str = "composite",
    preset_configs: dict | None = None,
    signal_queue=None,          # 测试开单用
    cache=None,                 # 市场数据缓存 (测试开单用)
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

    @app.get("/health/strategy")
    async def health_strategy():
        """Return current multi-strategy preset status and scoring summaries."""
        result = {
            "preset": preset_name,
            "enabled_presets": list((preset_configs or {}).keys()),
            "buy_threshold": None,
            "sell_threshold": None,
            "factor_weights": [],
            "preset_details": {},
            "max_symbols_to_scan": 0,
        }
        if isinstance(scoring_engine, dict) and scoring_engine:
            primary_name = preset_name if preset_name in scoring_engine else next(iter(scoring_engine.keys()))
            primary_engine = scoring_engine.get(primary_name)
            result["preset"] = primary_name
            result["buy_threshold"] = getattr(primary_engine, "_buy_threshold", None)
            result["sell_threshold"] = getattr(primary_engine, "_sell_threshold", None)
            factors = getattr(primary_engine, "_factors", [])
            result["factor_weights"] = [
                {"name": f.name, "weight": round(f.weight, 3)}
                for f in factors
            ]
            for name, engine in scoring_engine.items():
                runtime = (preset_configs or {}).get(name, {})
                result["preset_details"][name] = {
                    "enabled": True,
                    "buy_threshold": getattr(engine, "_buy_threshold", None),
                    "sell_threshold": getattr(engine, "_sell_threshold", None),
                    "risk_budget": runtime.get("risk_budget"),
                    "max_concurrent": runtime.get("max_concurrent"),
                    "exit_template": runtime.get("exit_template"),
                    "stop_loss_pct": runtime.get("stop_loss_pct"),
                    "tp1_pct": runtime.get("tp1_pct"),
                    "tp2_pct": runtime.get("tp2_pct"),
                    "tp3_pct": runtime.get("tp3_pct"),
                    "tp1_ratio": runtime.get("tp1_ratio"),
                    "tp2_ratio": runtime.get("tp2_ratio"),
                    "tp3_ratio": runtime.get("tp3_ratio"),
                    "breakeven_offset_pct": runtime.get("breakeven_offset_pct"),
                    "trail_distance_pct": runtime.get("trail_distance_pct"),
                    "trail_activation_pct": runtime.get("trail_activation_pct"),
                    "sideways_defense_minutes": runtime.get("sideways_defense_minutes"),
                    "sideways_exit_minutes": runtime.get("sideways_exit_minutes"),
                    "sideways_range_pct": runtime.get("sideways_range_pct"),
                    "pre_tp_guard_enabled": runtime.get("pre_tp_guard_enabled"),
                    "pre_tp_guard_min_roi_pct": runtime.get("pre_tp_guard_min_roi_pct"),
                    "factor_weights": [
                        {"name": f.name, "weight": round(f.weight, 3)}
                        for f in getattr(engine, "_factors", [])
                    ],
                }
        elif scoring_engine is not None:
            result["buy_threshold"] = getattr(scoring_engine, "_buy_threshold", None)
            result["sell_threshold"] = getattr(scoring_engine, "_sell_threshold", None)
            factors = getattr(scoring_engine, "_factors", [])
            result["factor_weights"] = [
                {"name": f.name, "weight": round(f.weight, 3)}
                for f in factors
            ]
        if scanner is not None:
            result["max_symbols_to_scan"] = getattr(scanner, "_max_scan", 0)
            result["scanner_running"] = getattr(scanner, "_running", False)
        return result

    @app.get("/health/positions")
    async def health_positions():
        """Return current open positions with enhanced data (SL/TP prices)."""
        if position_manager is None:
            return {"error": "Position manager not available"}
        positions = position_manager.get_all_positions()
        if position_manager is not None:
            for pos in positions:
                try:
                    inferred = position_manager.infer_strategy_from_metadata(pos)
                    pos["strategy_id"] = pos.get("strategy_id") or inferred.get("strategy_id", "")
                    pos["strategy_preset"] = pos.get("strategy_preset") or inferred.get("strategy_preset", "")
                    pos["support_presets"] = pos.get("support_presets") or inferred.get("support_presets", "")
                except Exception:
                    pass

        # 增强: 获取实时标记价、杠杆、保证金类型、强平价、名义价值
        try:
            if order_executor:
                exchange_positions = await order_executor.get_position_info()
                # 用交易所最新数据增强
                for pos in positions:
                    sym = pos.get("symbol", "")
                    # 确保默认值
                    pos.setdefault("leverage", 1)
                    pos.setdefault("margin_type", "cross")
                    pos.setdefault("liquidation_price", 0.0)
                    pos.setdefault("notional", 0.0)
                    pos.setdefault("sl_price", 0.0)
                    pos.setdefault("tp_price", 0.0)
                    created_at = _parse_iso_ts(pos.get("created_at", ""))
                    if created_at is not None:
                        hold_seconds = max((datetime.now(tz=timezone.utc) - created_at).total_seconds(), 0.0)
                        pos["opened_at"] = created_at.isoformat()
                        pos["hold_seconds"] = int(hold_seconds)
                    else:
                        pos.setdefault("opened_at", "")
                        pos.setdefault("hold_seconds", 0)
                    for ep in exchange_positions:
                        if ep.symbol == sym:
                            pos["mark_price"] = ep.mark_price
                            pos["unrealized_pnl"] = round(ep.unrealized_pnl, 4)
                            pos["leverage"] = ep.leverage
                            pos["margin_type"] = ep.margin_type or "cross"
                            pos["liquidation_price"] = ep.liquidation_price
                            # 计算 ROI%
                            if ep.entry_price > 0:
                                pnl_pct = (ep.mark_price - ep.entry_price) / ep.entry_price * 100
                                if (ep.position_side or "").upper() == "SHORT" or ep.quantity < 0:
                                    pnl_pct = -pnl_pct
                                pos["roi_pct"] = round(
                                    pnl_pct * ep.leverage, 2
                                )
                            pos["notional"] = round(abs(ep.quantity) * ep.mark_price, 2)
                            break

                # 获取所有挂单 (含 algo) 以提取 SL/TP 价格
                try:
                    all_orders = await order_executor.get_open_orders()
                    algo_orders = await order_executor.get_open_algo_orders()
                except Exception:
                    all_orders = []
                    algo_orders = []

                for pos in positions:
                    sym = pos.get("symbol", "")
                    sl_price = 0.0
                    tp_price = 0.0
                    # 遍历普通挂单
                    for o in all_orders:
                        if o.symbol != sym:
                            continue
                        if o.order_type in ("STOP_MARKET", "STOP", "STOP_LOSS"):
                            if sl_price == 0.0:
                                sl_price = float(o.stop_price or o.price or 0)
                        elif o.order_type in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT"):
                            if tp_price == 0.0:
                                tp_price = float(o.price or o.stop_price or 0)
                    # 遍历 algo orders (Binance 返回 triggerPrice, 不是 stopPrice)
                    for ao in algo_orders:
                        if ao.get("symbol", "") != sym:
                            continue
                        otype = ao.get("type", ao.get("orderType", ""))
                        if otype in ("STOP_MARKET", "STOP"):
                            # Binance algo orders use "triggerPrice" field, not "stopPrice"
                            sp = float(ao.get("triggerPrice", ao.get("stopPrice", 0)) or 0)
                            if sl_price == 0.0 and sp > 0:
                                sl_price = sp
                        elif otype in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT"):
                            tp = float(ao.get("triggerPrice", ao.get("price", ao.get("stopPrice", 0))) or 0)
                            if tp_price == 0.0 and tp > 0:
                                tp_price = tp
                    # TP 可能以 LIMIT 挂单形式存在 (三层止盈 LIMIT 单)
                    # LONG: 找 SELL 方向的最高 LIMIT 价格 (离 entry 最远 = 最高止盈层级)
                    # SHORT: 找 BUY 方向的最低 LIMIT 价格 (离 entry 最远 = 最低止盈层级)
                    if tp_price == 0.0:
                        pos_side = pos.get("side", "")
                        entry = float(pos.get("entry_price", 0))
                        tp_limit_prices: list[float] = []
                        for o in all_orders:
                            if o.symbol != sym:
                                continue
                            if o.order_type != "LIMIT":
                                continue
                            oprice = float(o.price or 0)
                            if oprice <= 0:
                                continue
                            # 根据仓位方向筛选
                            if pos_side == "LONG":
                                if o.side == "SELL" and (entry == 0 or oprice > entry):
                                    tp_limit_prices.append(oprice)
                            elif pos_side == "SHORT":
                                if o.side == "BUY" and (entry == 0 or oprice < entry):
                                    tp_limit_prices.append(oprice)
                        if tp_limit_prices:
                            if pos_side == "LONG":
                                tp_price = max(tp_limit_prices)
                            elif pos_side == "SHORT":
                                tp_price = min(tp_limit_prices)
                    pos["sl_price"] = round(sl_price, 5) if sl_price > 0 else 0.0
                    pos["tp_price"] = round(tp_price, 5) if tp_price > 0 else 0.0
        except Exception:
            pass

        return {
            "count": position_manager.position_count,
            "positions": positions,
        }

    @app.get("/health/orders")
    @_cached(30)
    async def health_orders():
        """返回当前挂单状态 (含 SL/TP 保护单统计 + algo orders)."""
        if order_executor is None:
            return {"error": "订单执行器不可用"}

        # 获取活跃持仓的币种集合 (用于过滤无持仓的僵尸保护单)
        active_symbols: set[str] = set()
        if position_manager is not None:
            try:
                active_positions = position_manager.get_all_positions()
                active_symbols = {p.get("symbol", "") for p in active_positions}
            except Exception:
                pass

        try:
            open_orders = await order_executor.get_open_orders()
            # 按币种分组统计保护单
            by_symbol: dict[str, dict] = {}
            for o in open_orders:
                sym = o.symbol
                if sym not in by_symbol:
                    by_symbol[sym] = {
                        "symbol": sym,
                        "total": 0, "stop_orders": 0, "tp_orders": 0,
                        "orders": [],
                    }
                info = by_symbol[sym]
                info["total"] += 1
                if o.order_type in ("STOP_MARKET", "STOP", "STOP_LOSS"):
                    info["stop_orders"] += 1
                elif o.order_type in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT", "LIMIT"):
                    info["tp_orders"] += 1
                info["orders"].append({
                    "type": o.order_type,
                    "side": o.side,
                    "price": o.price,
                    "stop_price": getattr(o, "stop_price", 0),
                    "qty": o.orig_qty,
                    "status": o.status,
                })

            # 同时查询 algo orders (Binance 条件单)
            total_algo_orders = 0
            stale_count = 0
            try:
                algo_orders = await order_executor.get_open_algo_orders()
                for ao in algo_orders:
                    sym = ao.get("symbol", "")
                    # 过滤无持仓的僵尸保护单
                    if active_symbols and sym not in active_symbols:
                        stale_count += 1
                        continue
                    if sym not in by_symbol:
                        by_symbol[sym] = {
                            "symbol": sym,
                            "total": 0, "stop_orders": 0, "tp_orders": 0,
                            "orders": [],
                        }
                    info = by_symbol[sym]
                    otype = ao.get("type", ao.get("orderType", ""))
                    if otype in ("STOP_MARKET", "STOP"):
                        info["stop_orders"] += 1
                        info["total"] += 1
                    elif otype in ("TAKE_PROFIT_MARKET", "TAKE_PROFIT", "LIMIT"):
                        info["tp_orders"] += 1
                        info["total"] += 1
                    total_algo_orders += 1
                    # Binance algo orders use "triggerPrice" (not "stopPrice")
                    trigger_price = float(ao.get("triggerPrice", ao.get("stopPrice", 0)) or 0)
                    order_price = float(ao.get("price", 0) or 0)
                    info["orders"].append({
                        "type": otype,
                        "side": ao.get("side", ""),
                        "price": order_price,
                        "stop_price": trigger_price,
                        "qty": float(ao.get("origQty", ao.get("quantity", 0)) or 0),
                        "status": ao.get("algoStatus", ao.get("status", "")),
                        "algo": True,
                    })
            except Exception:
                logger.debug("Algo orders fetch skipped")

            if stale_count > 0:
                logger.debug(f"已过滤 {stale_count} 个无持仓的僵尸保护单")

            return {
                "total": len(open_orders) + total_algo_orders,
                "by_symbol": list(by_symbol.values()),
                "total_algo_orders": total_algo_orders,
            }
        except Exception as exc:
            logger.exception("health endpoint failed")
            return {"error": "Internal server error"}

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
            "avg_hold_time_seconds": round(report.avg_hold_time_seconds, 1),
            "profit_factor": round(report.profit_factor, 2) if report.profit_factor != float("inf") else None,
            "max_drawdown_pct": round(report.max_drawdown_pct, 1),
            "sharpe_ratio": round(report.sharpe_ratio, 2),
            "start_balance": round(report.start_balance, 2),
            "current_balance": round(report.current_balance, 2),
            "strategies": report.strategies,
            "trades": [
                {
                    "symbol": t.symbol,
                    "side": t.side,
                    "strategy": t.strategy,
                    "entry_price": round(t.entry_price, 4),
                    "exit_price": round(t.exit_price, 4),
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 2),
                    "opened_at": t.opened_at,
                    "closed_at": t.closed_at,
                    "hold_seconds": round(t.hold_seconds, 1),
                    "exit_reason": t.exit_reason,
                    "tp_tiers_hit": t.tp_tiers_hit,
                }
                for t in report.trades[-20:]  # Last 20 trades
            ],
            "daily_pnl": report.daily_pnl[-30:],
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
                    "scanner_score": round(c.scanner_score, 1),
                    "composite_score": round(c.composite_score, 1),
                    "preset_scores": getattr(c, "preset_scores", {}),
                    "strategy_scores": getattr(c, "strategy_scores", {}),
                    "direction": c.direction,
                    "confidence": c.confidence,
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

    @app.get("/health/volume")
    async def health_volume():
        """交易量统计 (总成交额, 按周期)."""
        if order_executor is None:
            return {"error": "订单执行器不可用"}
        try:
            import time as _time
            now = _time.time()
            # 从 income API 获取 REALIZED_PNL 记录来推算成交量
            # (每笔 REALIZED_PNL 对应一次平仓, 但我们更需要总成交额)
            # 改用 DB fills 表来计算真实成交量
            if db is None:
                return {"error": "数据库不可用"}

            cutoff_1d = (now - 86400) * 1000
            cutoff_7d = (now - 7 * 86400) * 1000
            cutoff_30d = (now - 30 * 86400) * 1000

            rows = await db.fetch_all("""
                SELECT f.price, f.qty, f.filled_at, o.symbol
                FROM fills f JOIN orders o ON o.id = f.order_id
                ORDER BY f.filled_at DESC
            """)

            vol_total = 0.0
            vol_1d = 0.0
            vol_7d = 0.0
            vol_30d = 0.0
            trades_total = len(rows)
            trades_1d = 0
            trades_7d = 0
            trades_30d = 0

            for r in rows:
                price = float(r.get("price", 0) or 0)
                qty = float(r.get("qty", 0) or 0)
                notional = abs(price * qty)
                vol_total += notional

                filled_at = r.get("filled_at", "")
                if filled_at:
                    try:
                        from datetime import datetime
                        ts = datetime.fromisoformat(str(filled_at).replace("Z", "+00:00")).timestamp() * 1000
                        if ts >= cutoff_1d:
                            vol_1d += notional
                            trades_1d += 1
                        if ts >= cutoff_7d:
                            vol_7d += notional
                            trades_7d += 1
                        if ts >= cutoff_30d:
                            vol_30d += notional
                            trades_30d += 1
                    except Exception:
                        pass

            return {
                "volume_total": round(vol_total, 2),
                "volume_1d": round(vol_1d, 2),
                "volume_7d": round(vol_7d, 2),
                "volume_30d": round(vol_30d, 2),
                "trades_total": trades_total,
                "trades_1d": trades_1d,
                "trades_7d": trades_7d,
                "trades_30d": trades_30d,
            }
        except Exception as exc:
            logger.exception("volume endpoint failed")
            return {"error": str(exc)}

    @app.get("/health/account")
    @_cached(30)
    async def health_account():
        """实时账户数据."""
        if order_executor is None:
            return {"error": "订单执行器不可用"}
        try:
            acct = await order_executor.get_account_info()
            mr = acct.margin_ratio or 0
            margin_balance = acct.total_balance + acct.unrealized_pnl
            # margin_display: V1 风格 — USDT 全仓 X.XX%
            if mr <= 0.0001:
                margin_ratio_str = "全仓(共享)"
            else:
                margin_ratio_str = f"{mr * 100:.2f}%"
            mm = acct.maintenance_margin
            margin_display = f"USDT 全仓 {margin_ratio_str}"
            return {
                "total_balance": round(acct.total_balance, 2),
                "available_balance": round(acct.available_balance, 2),
                "unrealized_pnl": round(acct.unrealized_pnl, 2),
                "margin_ratio": round(acct.margin_ratio, 4),
                "margin_ratio_str": margin_ratio_str,
                "margin_display": margin_display,
                "maintenance_margin": round(mm, 4),
                "margin_balance": round(margin_balance, 2),
                "margin_type": acct.margin_type or "cross",
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
            logger.exception("health endpoint failed")
            return {"error": "Internal server error"}

    @app.get("/health/trades")
    @_cached(20)
    async def health_trades():
        """Return recent trades, preferring Binance userTrades over local fills."""
        try:
            if order_executor is not None:
                symbols = await _recent_trade_symbols(
                    db=db,
                    position_manager=position_manager,
                    limit=8,
                )
                strategy_map = await _recent_order_strategy_map(db=db, limit=600)
                if symbols:
                    import time as _time

                    start_ms = int((_time.time() - 7 * 86400) * 1000)
                    exchange_items: list[dict] = []
                    seen_trade_ids: set[tuple[str, int]] = set()

                    for symbol in symbols:
                        try:
                            history = await order_executor.get_trade_history(
                                symbol,
                                start_time=start_ms,
                                limit=80,
                            )
                        except Exception:
                            logger.debug(f"trade history fetch skipped: {symbol}", exc_info=True)
                            continue

                        for trade in history:
                            trade_key = (trade.symbol, trade.trade_id)
                            if trade_key in seen_trade_ids:
                                continue
                            seen_trade_ids.add(trade_key)

                            order_meta = strategy_map.get(str(trade.order_id), {})
                            strategy_name = str(order_meta.get("strategy_name", "") or "")
                            preset = strategy_name.split("_", 1)[0] if strategy_name else ""
                            exchange_items.append({
                                "symbol": trade.symbol,
                                "side": trade.side or ("BUY" if trade.buyer else "SELL"),
                                "type": order_meta.get("type", ""),
                                "price": round(trade.price, 8),
                                "qty": round(trade.qty, 8),
                                "commission": round(trade.commission, 8),
                                "commission_asset": trade.commission_asset,
                                "filled_at": datetime.fromtimestamp(
                                    trade.time / 1000,
                                    tz=timezone.utc,
                                ).isoformat(),
                                "time": trade.time,
                                "order_id": trade.order_id,
                                "trade_id": trade.trade_id,
                                "realized_pnl": round(trade.realized_pnl, 8),
                                "position_side": trade.position_side,
                                "strategy_name": strategy_name,
                                "strategy_id": strategy_name,
                                "preset": preset,
                                "source": "exchange",
                            })

                    if exchange_items:
                        exchange_items.sort(key=lambda item: item.get("time", 0), reverse=True)
                        trimmed = exchange_items[:50]
                        return {
                            "total": len(trimmed),
                            "trades": trimmed,
                            "source": "exchange",
                        }
        except Exception:
            logger.exception("exchange trade endpoint failed")

        if db is None:
            return {"error": "数据库不可用"}
        try:
            rows = await db.fetch_all("""
                SELECT o.symbol, o.side, o.type, o.pos_side, o.strategy_name,
                       f.price, f.qty, f.commission, f.commission_asset, f.filled_at
                FROM fills f
                JOIN orders o ON o.id = f.order_id
                ORDER BY f.filled_at DESC
                LIMIT 50
            """)
            trades = []
            for row in rows:
                item = dict(row)
                item["strategy_id"] = item.get("strategy_name", "")
                item["preset"] = str(item.get("strategy_name", "") or "").split("_", 1)[0]
                item["source"] = "database"
                trades.append(item)
            return {"total": len(trades), "trades": trades, "source": "database"}
        except Exception:
            logger.exception("health endpoint failed")
            return {"error": "Internal server error"}

    @app.post("/health/test-trade")
    async def health_test_trade(symbol: str = "", side: str = "LONG"):
        """测试开单: 注入一条合成信号到信号队列.

        可选 query params:
          - symbol: 币种 (如 BTCUSDT), 不填则自动选候选池最强
          - side: LONG 或 SHORT (默认 LONG)
        """
        from cryptopilot.strategy.base import Signal
        from loguru import logger
        import traceback

        try:
            if signal_queue is None:
                return JSONResponse({"error": "信号队列未注入, 无法测试"}, status_code=400)

            # 选币: 未指定则自动从候选池或行情中取
            target_symbol = (symbol or "").upper().strip()
            if not target_symbol:
                if candidate_pool is not None:
                    try:
                        all_cands = await candidate_pool.get_all()
                        if all_cands:
                            target_symbol = max(all_cands, key=lambda c: c.scanner_score).symbol
                    except Exception as e:
                        logger.warning(f"候选池获取失败: {e}")
                if not target_symbol and cache is not None:
                    try:
                        syms = [s for s in cache.all_symbols() if s.endswith("USDT")]
                        if syms:
                            target_symbol = syms[0]
                    except Exception as e:
                        logger.warning(f"缓存获取币种失败: {e}")
                if not target_symbol:
                    target_symbol = "BTCUSDT"

            # 取当前价 — 优先 REST API (更可靠)
            price = 0.0
            if order_executor is not None:
                try:
                    tick = await order_executor.get_ticker_price(target_symbol)
                    if tick:
                        price = float(tick)
                except Exception:
                    pass
            if price <= 0 and cache is not None:
                try:
                    t = cache.get_ticker(target_symbol)
                    if t:
                        price = t.last_price
                except Exception:
                    pass

            side_upper = side.upper()
            action = "OPEN_LONG" if side_upper == "LONG" else "OPEN_SHORT"

            signal = Signal(
                strategy_id=f"test_{target_symbol}",
                symbol=target_symbol,
                action=action,
                order_type="MARKET",
                price=price,
                stop_loss_pct=3.0,
                take_profit_pct=6.0,
                comment=f"🧪 测试开单: {target_symbol} {side_upper}",
                score=60.0,
                top_factors=[("test", "LONG" if side_upper == "LONG" else "SHORT", 1.0)],
                preset="manual_test",
            )

            await signal_queue.put(signal)
            return {
                "ok": True,
                "message": f"测试信号已注入: {action} {target_symbol} @ {price}",
                "signal": {
                    "symbol": target_symbol,
                    "action": action,
                    "price": price,
                    "score": 60.0,
                },
            }
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error(f"测试开单失败: {exc}\n{tb}")
            return JSONResponse({"error": str(exc), "traceback": tb[-500:]}, status_code=500)

    @app.get("/health/signals")
    async def health_signals():
        """返回最近信号日志."""
        signals = []
        for item in list(_signal_log[-50:]):
            entry = dict(item)
            entry.setdefault("preset", "")
            entry.setdefault("strategy_id", "")
            entry.setdefault("supporting_presets", [])
            entry.setdefault("opportunity_type", "")
            signals.append(entry)
        return {"total": len(_signal_log), "signals": signals}

    @app.get("/health/scoring-detail")
    async def health_scoring_detail():
        """返回候选池 Top-K 的因子评分明细 (含中文因子标签)."""
        if candidate_pool is None:
            return {"error": "候选池不可用"}
        candidates = await candidate_pool.get_all()
        if not candidates:
            return {"candidates": [], "preset": preset_name}

        result = []
        for cand in sorted(candidates, key=lambda c: c.scanner_score, reverse=True)[:5]:
            factors_info = []
            factor_labels_cn = []
            composite_score = 0.0
            direction = "HOLD"
            confidence = 0.0
            if scoring_engine:
                try:
                    from cryptopilot.strategy.scoring import FACTOR_CN
                    sr = scoring_engine.score(cand)
                    composite_score = round(sr.total_score, 1)
                    direction = sr.direction
                    confidence = round(sr.confidence, 2)
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
                    factor_labels_cn = [FACTOR_CN.get(fs.name, fs.name) for fs in sr.factors]
                except Exception:
                    pass
            result.append({
                "symbol": cand.symbol,
                "price": round(cand.current_price, 4),
                "change_24h": round(cand.change_24h_pct, 2),
                "scanner_score": round(cand.scanner_score, 1),
                "composite_score": composite_score,
                "direction": direction,
                "confidence": confidence,
                "factors": factors_info,
                "factor_labels_cn": factor_labels_cn,
            })
        return {"candidates": result, "preset": preset_name, "factor_labels_cn": {}}

    @app.get("/health/logs")
    async def health_logs(lines: int = 50):
        """返回最近 N 行日志 (供仪表盘实时监控)."""
        import glob, os
        log_pattern = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "logs", "cryptopilot_*.log"
        )
        log_files = sorted(glob.glob(os.path.abspath(log_pattern)), reverse=True)
        if not log_files:
            return {"lines": [], "message": "无日志文件"}
        try:
            with open(log_files[0], "r") as f:
                all_lines = f.readlines()
            recent = all_lines[-lines:]
            # 解析日志格式: 时间 | 级别 | 模块:函数:行号 | 消息
            parsed = []
            for line in recent:
                line = line.rstrip("\n")
                # 简化为前端友好格式: 去掉冗长模块路径
                if " | " in line:
                    parts = line.split(" | ", 3)
                    if len(parts) >= 4:
                        # parts[0]=时间, parts[1]=级别, parts[2]=位置, parts[3]=消息
                        level = parts[1].strip()
                        msg = parts[3]
                        # 简短时间
                        ts = parts[0].split(" ")[-1].split(".")[0] if " " in parts[0] else parts[0][:8]
                        parsed.append({"time": ts, "level": level, "msg": msg})
                    else:
                        parsed.append({"time": "", "level": "INFO", "msg": line})
                else:
                    parsed.append({"time": "", "level": "INFO", "msg": line})
            return {"lines": parsed, "file": os.path.basename(log_files[0])}
        except Exception as e:
            return {"lines": [], "error": str(e)}

    @app.exception_handler(Exception)
    async def generic_handler(request, exc):
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)},
        )

    return app
