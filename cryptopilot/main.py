"""CryptoPilot — Main application entry point.

Wires all modules together and runs the main event loop.
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
import time
from datetime import datetime, timezone

from loguru import logger


def _parse_iso_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _confirm_filled_order(executor, symbol: str, result, fallback_price: float = 0.0):
    """Poll order status until a usable average fill price is available."""
    fill_price = result.avg_price if result.avg_price > 0 else 0.0
    if fill_price > 0 or not result.client_order_id:
        return result, fill_price

    logger.info(f"Waiting for fill confirmation: {symbol}")
    for attempt in range(20):
        await asyncio.sleep(0.5)
        try:
            updated = await executor.get_order(symbol, result.client_order_id)
        except Exception:
            logger.debug(f"Fill confirmation skipped for {symbol} (attempt {attempt + 1})", exc_info=True)
            continue
        if updated.avg_price > 0:
            logger.info(f"{symbol} fill confirmed @{updated.avg_price:.5f}")
            return updated, updated.avg_price

    if fallback_price > 0:
        logger.warning(f"{symbol} fill confirmation timed out, fallback price {fallback_price:.5f}")
        return result, fallback_price

    logger.warning(f"{symbol} fill confirmation timed out without usable avg price")
    return result, 0.0


def _get_position_open_ts(position: dict | None, open_times: dict, symbol: str) -> float | None:
    open_ts = open_times.pop(symbol, None)
    if open_ts:
        return open_ts
    if position:
        created_at = _parse_iso_ts(str(position.get("created_at", "")))
        if created_at is not None:
            return created_at.timestamp()
    return None


def _format_hold_duration(seconds: float) -> str:
    seconds = max(float(seconds or 0.0), 0.0)
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h"


async def _record_strategy_event(
    event_repo,
    strategy_id: str,
    event_type: str,
    symbol: str,
    details: dict | None = None,
) -> None:
    """Persist structured activity for replay/dashboard use."""

    if event_repo is None:
        return
    from cryptopilot.persistence.models import StrategyEvent

    await event_repo.create(
        StrategyEvent(
            strategy_id=strategy_id or symbol,
            event_type=event_type,
            symbol=symbol,
            details=json.dumps(details or {}, ensure_ascii=False, separators=(",", ":")),
        )
    )


def _parse_filled_tp_tiers(raw: str) -> set[int]:
    tiers: set[int] = set()
    for item in str(raw or "").split(","):
        text = item.strip()
        if text.isdigit():
            tiers.add(int(text))
    return tiers


def _build_tp_targets(entry_price: float, side: str, runtime_cfg: dict) -> dict[int, dict]:
    tp_specs = [
        (1, float(runtime_cfg.get("tp1_pct", 3.0)), float(runtime_cfg.get("tp1_ratio", 0.30))),
        (2, float(runtime_cfg.get("tp2_pct", 6.0)), float(runtime_cfg.get("tp2_ratio", 0.30))),
        (3, float(runtime_cfg.get("tp3_pct", 10.0)), float(runtime_cfg.get("tp3_ratio", 0.40))),
    ]
    targets: dict[int, dict] = {}
    is_long = side == "LONG"
    for tier, pct, ratio in tp_specs:
        price = entry_price * (1 + pct / 100) if is_long else entry_price * (1 - pct / 100)
        targets[tier] = {"price": price, "pct": pct, "ratio": ratio}
    return targets


async def _recover_missing_protection_orders(
    *,
    executor,
    order_manager,
    position_manager,
    notifier,
    event_repo,
    preset_runtime_map: dict[str, dict],
    default_runtime_cfg: dict,
) -> None:
    """On startup, detect positions missing TP/SL orders and re-place only the missing protection."""

    from cryptopilot.notification.notifier import EventData, Events
    from cryptopilot.trading.order_executor import OrderRequest, _make_client_id
    from cryptopilot.trading.precision import clamp_price, clamp_qty

    positions = position_manager.get_all_positions()
    if not positions:
        return

    is_hedge = await executor.get_position_mode()
    open_orders = await executor.get_open_orders()
    open_algo_orders = await executor.get_open_algo_orders()

    regular_by_symbol: dict[str, list] = {}
    for order in open_orders:
        regular_by_symbol.setdefault(order.symbol, []).append(order)

    algo_by_symbol: dict[str, list[dict]] = {}
    for order in open_algo_orders:
        symbol = str(order.get("symbol", "") or "")
        if symbol:
            algo_by_symbol.setdefault(symbol, []).append(order)

    recovered_symbols: list[str] = []

    for pos in positions:
        symbol = str(pos.get("symbol", "") or "")
        side = str(pos.get("side", "") or "").upper()
        if not symbol or side not in {"LONG", "SHORT"}:
            continue

        qty = abs(float(pos.get("qty", 0) or 0))
        entry_price = float(pos.get("entry_price", 0) or 0)
        if qty <= 0 or entry_price <= 0:
            continue

        preset_name = str(pos.get("strategy_preset", "") or "")
        runtime_cfg = dict(preset_runtime_map.get(preset_name, default_runtime_cfg))
        tp_targets = _build_tp_targets(entry_price, side, runtime_cfg)
        stop_price = float(pos.get("current_stop", 0) or pos.get("stop_loss_price", 0) or 0)
        filled_tiers = _parse_filled_tp_tiers(str(pos.get("tp_tiers_filled", "") or ""))
        remaining_tiers = [tier for tier in (1, 2, 3) if tier not in filled_tiers]
        close_side = "SELL" if side == "LONG" else "BUY"
        exchange_pos_side = side if is_hedge else ""

        regular_orders = regular_by_symbol.get(symbol, [])
        algo_orders = algo_by_symbol.get(symbol, [])

        tp_orders = [
            order for order in regular_orders
            if str(order.side or "").upper() == close_side and str(order.order_type or "").upper() == "LIMIT"
        ]
        sl_orders = [
            order for order in algo_orders
            if str(order.get("side", "") or "").upper() == close_side
            and "STOP" in str(order.get("type", "") or "").upper()
        ]

        existing_tp_tiers: set[int] = set()
        for order in tp_orders:
            order_price = float(getattr(order, "price", 0) or 0)
            if order_price <= 0:
                continue
            closest_tier = min(
                remaining_tiers,
                key=lambda tier: abs(order_price - tp_targets[tier]["price"]),
                default=None,
            )
            if closest_tier is not None:
                existing_tp_tiers.add(closest_tier)

        missing_sl = stop_price > 0 and len(sl_orders) == 0
        tiers_to_place = [tier for tier in remaining_tiers if tier not in existing_tp_tiers]
        if not missing_sl and not tiers_to_place:
            continue

        filters = executor.get_symbol_filters(symbol)
        recovered_parts: list[str] = []

        if missing_sl:
            sl_req = OrderRequest(
                symbol=symbol,
                side=close_side,
                order_type="STOP_MARKET",
                quantity=qty,
                stop_price=stop_price,
                reduce_only=True,
                position_side=exchange_pos_side,
                client_order_id=_make_client_id("sl_recover"),
            )
            try:
                sl_result = await executor.create_order(sl_req)
                await order_manager.record_order(sl_result, str(pos.get("strategy_id", "") or symbol))
                recovered_parts.append(f"SL @{stop_price:.5f}")
            except Exception as exc:
                logger.error(f"重启补挂 SL 失败: {symbol} {exc}")

        if tiers_to_place:
            open_tp_qty = sum(abs(float(getattr(order, "orig_qty", 0) or 0)) for order in tp_orders)
            uncovered_qty = max(qty - open_tp_qty, 0.0)
            remaining_ratio_total = sum(tp_targets[tier]["ratio"] for tier in tiers_to_place)
            for tier in tiers_to_place:
                tier_cfg = tp_targets[tier]
                tp_qty = (
                    uncovered_qty * (tier_cfg["ratio"] / remaining_ratio_total)
                    if remaining_ratio_total > 0 else 0.0
                )
                tp_price = tier_cfg["price"]
                if filters:
                    tp_qty = clamp_qty(
                        tp_qty,
                        filters["step_size"],
                        filters.get("min_qty", 0),
                        filters["max_qty"],
                    )
                    tp_price = clamp_price(tp_price, filters["tick_size"])
                if tp_qty <= 0:
                    continue
                tp_req = OrderRequest(
                    symbol=symbol,
                    side=close_side,
                    order_type="LIMIT",
                    quantity=tp_qty,
                    price=tp_price,
                    reduce_only=True,
                    position_side=exchange_pos_side,
                    client_order_id=_make_client_id(f"tp{tier}_recover"),
                    time_in_force="GTC",
                )
                try:
                    tp_result = await executor.create_order(tp_req)
                    await order_manager.record_order(tp_result, str(pos.get("strategy_id", "") or symbol))
                    recovered_parts.append(f"TP{tier} @{tp_price:.5f}")
                except Exception as exc:
                    logger.error(f"重启补挂 TP{tier} 失败: {symbol} {exc}")

        if not recovered_parts:
            continue

        recovered_symbols.append(symbol)
        message = f"重启补挂保护单 {symbol}: " + " | ".join(recovered_parts)
        notifier.notify(EventData(event=Events.WARNING, message=message, symbol=symbol))
        await _record_strategy_event(
            event_repo,
            str(pos.get("strategy_id", "") or symbol),
            "protection_recovered",
            symbol,
            {
                "preset": preset_name or "default",
                "recovered": recovered_parts,
                "filled_tiers": ",".join(str(tier) for tier in sorted(filled_tiers)),
                "stop_price": f"{stop_price:.8f}" if stop_price > 0 else "",
            },
        )

    if recovered_symbols:
        logger.warning(f"启动补挂保护单完成: {', '.join(recovered_symbols)}")


async def main() -> None:
    """Application bootstrap and main event loop."""
    # ---- Config ----
    from cryptopilot.core.config import load_config, get_config, get_env, ROOT_DIR

    cfg = load_config()
    env = get_env()

    # ---- Logging ----
    from cryptopilot.core.logger import setup_logging

    setup_logging(level=cfg.logging.level, retention_days=cfg.logging.retention_days)
    logger.info("=" * 60)
    logger.info("CryptoPilot 启动中...")
    logger.info(f"交易所: {'测试网' if cfg.exchange.testnet else '实盘'}, {cfg.exchange.trading_type}")
    logger.info("=" * 60)

    # 启动冷却: 避免继承前次 IP 封禁的残留限流
    import time as _time
    _time.sleep(5)
    logger.info("启动冷却完成 (5s)")

    # ---- Security ----
    from cryptopilot.security.encryptor import Encryptor, KEY_FILE

    encryptor = Encryptor(env.encryption_password, env.encryption_salt)

    # 判断是否需要重新加密: keys.enc 不存在 或 .env 中有新密钥
    need_rekey = not KEY_FILE.exists()
    if not need_rekey and env.binance_api_key and env.binance_api_secret:
        try:
            encryptor.load()
            # 比较 .env 中的密钥是否与加密存储的不同
            if (env.binance_api_key != encryptor.get_api_key() or
                    env.binance_api_secret != encryptor.get_api_secret()):
                need_rekey = True
                logger.info("检测到 .env 中的 API 密钥已更新，将重新加密")
        except Exception:
            need_rekey = True
            logger.warning("加密文件解密失败，将使用 .env 中的新密钥重新加密")

    if need_rekey:
        if not env.binance_api_key or not env.binance_api_secret:
            logger.error("未找到 API 密钥，请在 .env 中设置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
            # 注意: 此时 db 尚未连接, 安全退出
            return
        encryptor.initialize(env.binance_api_key, env.binance_api_secret)
        logger.info(f"API 密钥已加密保存到 {KEY_FILE}")
    else:
        logger.info("API 密钥已从加密存储中加载 (与 .env 一致)")

    api_key = encryptor.get_api_key()
    api_secret = encryptor.get_api_secret()

    # ---- Database ----
    from cryptopilot.persistence.database import Database
    from cryptopilot.persistence.repositories import (
        OrderRepository,
        FillRepository,
        PositionRepository,
        AccountRepository,
        StrategyEventRepository,
    )

    db = Database()
    await db.connect()

    order_repo = OrderRepository(db)
    fill_repo = FillRepository(db)
    position_repo = PositionRepository(db)
    account_repo = AccountRepository(db)
    event_repo = StrategyEventRepository(db)

    # ---- Market Data (WebSocket 优先, 10s 无数据自动降级 REST) ----
    from cryptopilot.market.market_data_cache import MarketDataCache
    from cryptopilot.market.websocket_manager import BinanceWebSocketManager
    from cryptopilot.market.rest_poller import RestMarketPoller
    from cryptopilot.market.rest_data import RestDataFetcher

    # 提前加载 raw YAML (供 market_data 配置读取)
    import yaml as _yaml
    with open(ROOT_DIR / "config.yaml", "r", encoding="utf-8") as _f:
        raw_cfg = _yaml.safe_load(_f) or {}

    data_cache = MarketDataCache()

    # 代理配置
    proxy_url = None
    if cfg.proxy.enabled and cfg.proxy.https:
        proxy_url = cfg.proxy.https
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        safe_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}" if parsed.hostname else "***"
        logger.info(f"已启用代理: {safe_url}")

    # 读取数据源配置
    md_cfg = raw_cfg.get("market_data", {})
    data_source = md_cfg.get("source", "auto")
    poll_interval = md_cfg.get("rest_poll_interval", 3)

    ws_manager = None
    use_rest_poller = False
    ws_already_started = False

    if data_source == "rest":
        use_rest_poller = True
    elif data_source == "websocket":
        from cryptopilot.market.websocket_manager import BinanceWebSocketManager as BWM
        ws_manager = BWM(cfg, data_cache)
    else:  # auto
        # 尝试 WebSocket, 10s 无数据则降级 REST
        from cryptopilot.market.websocket_manager import BinanceWebSocketManager as BWM
        ws_manager = BWM(cfg, data_cache)
        ws_task_test = asyncio.create_task(ws_manager.start(), name="ws_test")

        logger.info("正在检测 WebSocket 连通性 (最多等待 10s)...")
        for _ in range(20):  # 20 × 0.5s = 10s
            await asyncio.sleep(0.5)
            if len(data_cache.all_tickers()) > 10:
                break

        ticker_count = len(data_cache.all_tickers())
        if ticker_count > 10:
            logger.info(f"WebSocket 正常: {ticker_count} 个币种已就绪")
            ws_already_started = True
        else:
            logger.warning("WebSocket 无数据, 降级为 REST 轮询")
            use_rest_poller = True
            await ws_manager.stop()
            ws_task_test.cancel()
            try:
                await ws_task_test
            except Exception:
                logger.debug("WS 测试任务取消失败", exc_info=True)
            ws_manager = None

    if use_rest_poller:
        ws_manager = RestMarketPoller(
            cache=data_cache,
            proxy=proxy_url,
            poll_interval=float(poll_interval),
        )

    # REST 按需数据拉取器
    rest_data = RestDataFetcher(proxy=proxy_url)

    # ---- Trading ----
    from cryptopilot.trading.rate_limiter import RateLimiter
    from cryptopilot.trading.order_executor import OrderExecutor
    from cryptopilot.trading.order_manager import OrderManager
    from cryptopilot.trading.position_manager import PositionManager

    rate_limiter = RateLimiter(
        max_weight=cfg.order.rate_limit_weight_per_minute
    )
    order_executor = OrderExecutor(cfg, api_key, api_secret, rate_limiter)
    await order_executor.initialize()
    await asyncio.sleep(2.0)  # 启动节流: 避免密集 REST 触发限流

    order_manager = OrderManager(db)
    position_manager = PositionManager(db)

    # ---- WS 交易客户端 (0 权重下单, 替代 REST) ----
    from cryptopilot.trading.ws_trading_client import WSTradingClient
    from cryptopilot.market.user_data_stream import UserDataStream

    ws_trader: WSTradingClient | None = None
    user_data: UserDataStream | None = None
    _user_data_task: asyncio.Task | None = None
    history_sync_task: asyncio.Task | None = None
    signal_processor_task: asyncio.Task | None = None
    ws_trader_connected = False

    try:
        ws_trader = WSTradingClient(
            api_key=api_key,
            api_secret=api_secret,
            testnet=cfg.exchange.testnet,
        )
        await ws_trader.connect()
        ws_trader_connected = True
        logger.info("WS 交易客户端已连接 (0 权重下单)")

        # 用户数据流: 实时监听成交/仓位/账户变动
        user_data = UserDataStream(
            api_key=api_key,
            api_secret=api_secret,
            testnet=cfg.exchange.testnet,
            proxy=proxy_url,
        )

        async def _on_order_update(event):
            """WS 推送的订单状态变更 → 更新本地订单簿 + 写入成交 + 同步持仓."""
            try:
                cid = event.client_order_id
                status = event.order_status
                executed = event.executed_qty
                position_before = position_manager.get_position_context(event.symbol) or {}
                prev_qty = abs(float(position_before.get("qty", 0) or 0))
                if cid:
                    await order_manager.update_order(cid, status, executed)

                # 有成交 (PARTIALLY_FILLED / FILLED) → 记录 fill
                if event.last_filled_qty > 0:
                    try:
                        row = await order_repo.get_by_client_id(cid)
                    except Exception:
                        row = None
                    order_db_id = row["id"] if row else 0
                    if order_db_id > 0:
                        await order_manager.record_fill(
                            order_db_id=order_db_id,
                            price=event.last_filled_price,
                            qty=event.last_filled_qty,
                            commission=event.commission,
                            asset=event.commission_asset,
                        )

                # 订单完全成交 → 异步同步持仓/账户 (限流: 3s 内最多一次)
                if status == "FILLED":
                    now = time.time()
                    if now - getattr(_on_order_update, "_last_sync", 0) > 3.0:
                        _on_order_update._last_sync = now
                        await position_manager.sync_from_exchange(order_executor)
                        # 记一笔账户快照
                        try:
                            acct = await order_executor.get_account_info()
                            from cryptopilot.persistence.models import AccountSnapshot
                            await account_repo.create(AccountSnapshot(
                                total_balance=acct.total_balance,
                                available_balance=acct.available_balance,
                                unrealized_pnl=acct.unrealized_pnl,
                                margin_ratio=acct.margin_ratio,
                            ))
                        except Exception:
                            logger.debug("账户快照写入失败")
                    # 成交写入信号日志
                    from cryptopilot.web.health import add_signal_log
                    add_signal_log({
                        "time": datetime.now(tz=timezone.utc).isoformat(),
                        "symbol": event.symbol,
                        "action": f"FILLED_{event.side}",
                        "score": round(event.executed_qty, 4),
                        "detail": f"成交 {event.executed_qty}/{event.orig_qty} @{event.avg_price:.4f} PnL={event.realized_pnl:.2f}",
                    })

                    # 🆕 TP/SL 触发检测
                    cid = event.client_order_id or ""
                    cid_lower = cid.lower()
                    is_sl = event.order_type == "STOP_MARKET"
                    is_tp = cid.startswith("tp")  # TP 单是 LIMIT 类型, 靠 client_order_id 识别
                    is_tp = is_tp or any(token in cid_lower for token in ("tp1", "tp2", "tp3"))
                    close_event_reason = ""
                    if is_sl or is_tp:
                        pnl = float(event.realized_pnl or 0)
                        if is_sl:
                            close_event_reason = "SL_HIT"
                            notifier.sl_triggered(
                                symbol=event.symbol,
                                price=float(event.avg_price or 0),
                                pnl=pnl,
                                pnl_pct=0.0,
                            )
                        elif is_tp:
                            tier = 1
                            if "tp2" in cid_lower:
                                tier = 2
                            elif "tp3" in cid_lower:
                                tier = 3
                            close_event_reason = f"TP{tier}"
                            remaining = max(prev_qty - float(event.last_filled_qty or 0), 0.0)
                            notifier.tp_triggered(
                                symbol=event.symbol,
                                tier=tier,
                                price=float(event.avg_price or 0),
                                pnl=pnl,
                                remaining_qty=remaining,
                            )
                            pos_ctx = position_manager.get_position_context(event.symbol) or {}
                            existing = str(pos_ctx.get("tp_tiers_filled", "") or "")
                            tiers = [item.strip() for item in existing.split(",") if item.strip()]
                            tier_text = str(tier)
                            if tier_text not in tiers:
                                tiers.append(tier_text)
                            await position_manager.update_risk_state(
                                event.symbol,
                                tp_tiers_filled=",".join(tiers),
                                partial_tp_count=len(tiers),
                            )
                            pos_ctx = position_manager.get_position_context(event.symbol) or position_before
                            await _record_strategy_event(
                                event_repo,
                                str(pos_ctx.get("strategy_id", "") or event.symbol),
                                "partial_take_profit",
                                event.symbol,
                                {
                                    "preset": str(pos_ctx.get("strategy_preset", "") or ""),
                                    "entry_reason": str(pos_ctx.get("entry_reason", "") or ""),
                                    "exit_reason": f"TP{tier}",
                                    "reason": f"TP{tier} filled",
                                    "filled_price": float(event.avg_price or 0),
                                    "realized_pnl": pnl,
                                    "remaining_qty": remaining,
                                    "tp_tiers_filled": ",".join(tiers),
                                },
                            )
                        await position_manager.sync_from_exchange(order_executor)
                        position_after = position_manager.get_position(event.symbol)
                        remaining_after = abs(float(position_after.get("qty", 0) or 0)) if position_after else 0.0
                        if prev_qty > 0 and remaining_after <= 1e-8:
                            pos_ctx = position_manager.get_position_context(event.symbol) or position_before
                            entry_px = float(pos_ctx.get("entry_price", 0) or 0)
                            exit_px = float(event.avg_price or event.last_filled_price or event.price or 0)
                            side = str(pos_ctx.get("side", "") or event.position_side or "LONG")
                            pnl_pct = 0.0
                            if entry_px > 0 and exit_px > 0:
                                pnl_pct = (exit_px - entry_px) / entry_px * 100
                                if side.upper() == "SHORT":
                                    pnl_pct = -pnl_pct
                            open_times = getattr(_execute_signal, "_position_open_time", {})
                            open_ts = _get_position_open_ts(pos_ctx, open_times, event.symbol)
                            hold_seconds = max(time.time() - open_ts, 0.0) if open_ts else 0.0
                            hold_duration = _format_hold_duration(hold_seconds) if hold_seconds else ""
                            exit_reason = close_event_reason or ("TP_HIT" if is_tp else "SL_HIT")
                            await position_manager.mark_closed(
                                event.symbol,
                                side=side,
                                exit_reason=exit_reason,
                                exit_price=exit_px,
                                exit_time=datetime.now(tz=timezone.utc).isoformat(),
                                pnl=float(event.realized_pnl or 0),
                                pnl_pct=pnl_pct,
                            )
                            await _record_strategy_event(
                                event_repo,
                                str(pos_ctx.get("strategy_id", "") or event.symbol),
                                "position_closed",
                                event.symbol,
                                {
                                    "preset": str(pos_ctx.get("strategy_preset", "") or ""),
                                    "entry_reason": str(pos_ctx.get("entry_reason", "") or ""),
                                    "exit_reason": exit_reason,
                                    "pnl": round(float(event.realized_pnl or 0), 8),
                                    "exit_price": exit_px,
                                    "tp_tiers_filled": str(pos_ctx.get("tp_tiers_filled", "") or ""),
                                },
                            )
                            notifier.position_closed(
                                symbol=event.symbol,
                                side=side,
                                exit_price=exit_px,
                                pnl=float(event.realized_pnl or 0),
                                pnl_pct=pnl_pct,
                                exit_reason=exit_reason,
                                hold_duration=hold_duration,
                                entry_reason=str(pos_ctx.get("entry_reason", "") or ""),
                                strategy_id=str(pos_ctx.get("strategy_id", "") or ""),
                                strategy_preset=str(pos_ctx.get("strategy_preset", "") or ""),
                                support_presets=[
                                    item.strip()
                                    for item in str(pos_ctx.get("support_presets", "") or "").split(",")
                                    if item.strip()
                                ],
                                opportunity_type=str(pos_ctx.get("strategy_preset", "") or ""),
                                entry_price=entry_px,
                                hold_seconds=hold_seconds,
                                leverage=int(pos_ctx.get("leverage", 0) or 0),
                            )
            except Exception:
                logger.exception("WS 订单更新处理异常")

        async def _on_account_update(event):
            """WS 推送的账户/仓位变动 → 同步持仓 (仅同步 WS 推送的仓位变化)."""
            try:
                if hasattr(event, "positions") and event.positions:
                    for pos_data in event.positions:
                        sym = pos_data.get("symbol", "")
                        if sym:
                            logger.debug(f"WS 仓位变动: {sym} {pos_data.get('ps', '')}")
                    # 全量同步 (轻量, 因为账户更新本身不频繁)
                    await position_manager.sync_from_exchange(order_executor)
            except Exception:
                logger.exception("WS 账户更新处理异常")

        user_data.on_order_update(_on_order_update)
        user_data.on_account_update(_on_account_update)
        _user_data_task = asyncio.create_task(user_data.start(), name="user_data_stream")
        logger.info("用户数据流已启动 (实时成交/仓位推送)")
    except Exception as exc:
        logger.warning(f"WS 交易客户端不可用, 降级为纯 REST 下单: {exc}")
        ws_trader_connected = False

    # Sync initial state from exchange (加节流延迟避免触发限流)
    await asyncio.sleep(1.5)
    await position_manager.sync_from_exchange(order_executor)
    await asyncio.sleep(1.5)
    await order_manager.sync_with_exchange(order_executor)
    await _recover_missing_protection_orders(
        executor=order_executor,
        order_manager=order_manager,
        position_manager=position_manager,
        notifier=notifier,
        event_repo=event_repo,
        preset_runtime_map=preset_runtime_map,
        default_runtime_cfg=default_runtime_cfg,
    )
    logger.info(
        f"初始状态已加载: {position_manager.position_count} 个持仓, "
        f"{len(await order_manager.get_open_orders())} 个挂单"
    )

    # ---- 历史数据同步 (从 Binance 拉取历史成交) ----
    from cryptopilot.trading.order_executor import HistoryTrade

    async def sync_trade_history():
        """从 Binance 拉取近 90 天历史成交, 回填 fills + orders 表."""
        try:
            existing_count_row = await db.fetch_all("SELECT COUNT(*) as cnt FROM fills", ())
            existing_count = existing_count_row[0].get("cnt", 0) if existing_count_row else 0

            end_time = int(time.time() * 1000)
            start_time = end_time - 90 * 86400 * 1000

            # Step 1: 先拉取 income history (REALIZED_PNL) — 不需要知道币种
            if existing_count < 10:
                logger.info("从 Binance 拉取盈亏流水...")
                try:
                    incomes = await order_executor.get_income_history(
                        start_time=start_time, end_time=end_time, limit=1000,
                    )
                    realized = [i for i in incomes if i.income_type == "REALIZED_PNL" and i.income != 0]
                    commission = [i for i in incomes if i.income_type == "COMMISSION"]
                    funding = [i for i in incomes if i.income_type == "FUNDING_FEE"]
                    logger.info(
                        f"盈亏流水: {len(realized)} 笔 PnL, "
                        f"{len(commission)} 笔手续费, {len(funding)} 笔资金费率"
                    )
                except Exception:
                    incomes = []

            # Step 2: 收集要同步的币种
            symbols_to_sync: set[str] = set()
            for pos in position_manager.get_all_positions():
                sym = pos.get("symbol", "")
                if sym:
                    symbols_to_sync.add(sym)

            # 从 income 获取历史交易过的币种
            try:
                for i in incomes:
                    if i.symbol and i.symbol not in symbols_to_sync:
                        symbols_to_sync.add(i.symbol)
            except Exception:
                logger.debug("income 币种收集跳过", exc_info=True)
            if not symbols_to_sync:
                recent_orders = await order_repo.get_history(limit=50)
                for o in recent_orders:
                    sym = o.get("symbol", "")
                    if sym:
                        symbols_to_sync.add(sym)

            if symbols_to_sync:
                logger.info(f"历史数据同步: {len(symbols_to_sync)} 个币种")

            total_fills = 0
            for sym in list(symbols_to_sync)[:30]:
                try:
                    trades = await order_executor.get_trade_history(
                        symbol=sym, start_time=start_time, end_time=end_time, limit=1000,
                    )
                    if not trades:
                        continue

                    for t in trades:
                        try:
                            created = datetime.fromtimestamp(
                                t.time / 1000, tz=timezone.utc
                            ).isoformat()
                            order_db_id = await order_repo.upsert_history_order(
                                symbol=t.symbol, side=t.side, order_type="MARKET",
                                exchange_order_id=str(t.order_id),
                                price=t.price, orig_qty=t.qty,
                                executed_qty=t.qty, avg_price=t.price,
                                pos_side=t.position_side, created_at=created,
                            )
                            existing_fills = await db.fetch_all(
                                "SELECT id FROM fills WHERE order_id = ? AND price = ? AND qty = ?",
                                (order_db_id, t.price, t.qty),
                            )
                            if not existing_fills:
                                await order_manager.record_fill(
                                    order_db_id=order_db_id,
                                    price=t.price, qty=t.qty,
                                    commission=t.commission,
                                    asset=t.commission_asset,
                                    filled_at=created,
                                )
                                total_fills += 1
                        except Exception:
                            logger.debug(f"历史成交写入跳过 {t.symbol}", exc_info=True)

                    logger.debug(f"历史同步: {sym} {len(trades)} 笔成交")
                except Exception:
                    logger.debug(f"历史同步跳过 {sym}")

            if total_fills > 0:
                logger.info(f"历史数据同步: 新增 {total_fills} 条成交 (fills 表总计 ~{existing_count + total_fills})")
            elif symbols_to_sync:
                logger.info("历史数据同步: 无新增成交 (fill 表已是最新)")
            else:
                logger.info("无历史交易数据可同步")
        except Exception:
            logger.exception("历史数据同步异常 (非致命)")

    # 启动后台同步 (不阻塞)
    history_sync_task = asyncio.create_task(sync_trade_history(), name="history_sync")

    # ---- 信号日志 (用于 Web 展示) ----
    from cryptopilot.web.health import add_signal_log

    # 把 WS 客户端注入 _execute_signal 全局引用
    _execute_signal.ws_trader = ws_trader
    _execute_signal.use_ws = ws_trader_connected

    # ---- Risk ----
    from cryptopilot.risk.position_sizer import PositionSizer
    from cryptopilot.risk.circuit_breaker import CircuitBreaker
    from cryptopilot.risk.trailing_stop import TrailingStop

    position_sizer = PositionSizer(cfg.risk.model_dump())
    circuit_breaker = CircuitBreaker(cfg.risk.max_daily_loss_pct)

    # Get initial account balance for circuit breaker
    try:
        acct = await order_executor.get_account_info()
        circuit_breaker.update(acct.total_balance)
        logger.info(f"账户: 总余额={acct.total_balance:.2f}, 可用={acct.available_balance:.2f}")
    except Exception:
        logger.warning("无法获取初始账户信息")

    # ---- Signal Queue + Strategy Engine ----
    signal_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

    from cryptopilot.strategy.engine import StrategyEngine
    from cryptopilot.strategy.examples.ma_crossover import MACrossoverStrategy
    from cryptopilot.strategy.examples.rsi_strategy import RSIStrategy
    from cryptopilot.strategy.examples.bollinger_breakout import BollingerBreakoutStrategy
    from cryptopilot.strategy.examples.volume_breakout import VolumeBreakoutStrategy

    available_strategies = {
        "ma_crossover": MACrossoverStrategy,
        "rsi": RSIStrategy,
        "bollinger_breakout": BollingerBreakoutStrategy,
        "volume_breakout": VolumeBreakoutStrategy,
    }

    strategy_engine = StrategyEngine(
        signal_queue, data_cache, position_manager, order_manager
    )

    # Register strategies from config
    trailing_stops: dict[str, TrailingStop] = {}

    for sc in cfg.strategies:
        if not sc.enabled:
            continue
        strategy_cls = available_strategies.get(sc.name)
        if not strategy_cls:
            logger.warning(f"未知策略类型: {sc.name}")
            continue

        sid = f"{sc.name}_{sc.symbol}_{len(trailing_stops)}"
        strategy = strategy_cls(
            strategy_id=sid,
            symbol=sc.symbol,
            parameters=sc.parameters,
            risk_config=sc.risk,
            signal_queue=signal_queue,
            cache=data_cache,
            position_manager=position_manager,
            order_manager=order_manager,
        )
        await strategy_engine.register(strategy)

        # Initialize trailing stop if configured
        if sc.risk.get("trailing_stop"):
            trailing_stops[sid] = TrailingStop(
                symbol=sc.symbol,
                side="LONG",  # will be updated on position open
                entry_price=0,
                initial_stop=0,
                trail_distance_pct=sc.risk.get("trailing_distance_pct", 1.5),
                activation_pct=sc.risk.get("trailing_activation_pct", 0.5),
            )

    # ---- 市值数据抓取器 ----
    from cryptopilot.market.market_cap import MarketCapFetcher

    mcap_fetcher = MarketCapFetcher(proxy=proxy_url)

    # 首次拉取市值数据
    try:
        await mcap_fetcher.fetch_all()
    except Exception:
        logger.warning("初始市值数据拉取失败, 稍后重试")

    # 后台定时刷新市值 (每小时)
    async def mcap_refresh_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                await mcap_fetcher.fetch_all()
            except Exception:
                logger.exception("市值刷新异常")

    mcap_task = asyncio.create_task(mcap_refresh_loop(), name="mcap_refresh")

    # ---- Scanning Pipeline (Scanner → CandidatePool → Scoring → Signals) ----
    scanner_obj = None
    candidate_pool = None
    scoring_engine = None
    enabled_presets: dict[str, dict] = {}
    scan_task = None
    score_task = None

    # 从 config.yaml 读取评分配置 (支持预设)
    scoring_cfg = raw_cfg.get("scoring", {})

    active_preset = scoring_cfg.get("active_preset", "composite")
    presets = scoring_cfg.get("presets", {})
    min_confidence = scoring_cfg.get("min_confidence", 0.5)
    top_k_per_preset = int(scoring_cfg.get("top_k_per_preset", 3) or 3)
    max_signals_per_cycle = int(scoring_cfg.get("max_signals_per_cycle", 1) or 1)
    special_signals = dict(scoring_cfg.get("special_signals", {}) or {})

    enabled_presets = {
        preset_name: preset_cfg
        for preset_name, preset_cfg in presets.items()
        if preset_cfg.get("enabled", True) and preset_cfg.get("factors")
    }

    if not enabled_presets and active_preset in presets:
        fallback_cfg = dict(presets.get(active_preset, {}) or {})
        if fallback_cfg.get("factors"):
            enabled_presets = {active_preset: fallback_cfg}

    logger.info(
        f"启用策略预设: {list(enabled_presets.keys()) or [active_preset]} "
        f"(候选TopK={top_k_per_preset}, 每轮最多信号={max_signals_per_cycle})"
    )

    if enabled_presets:
        scanner_obj, candidate_pool, scoring_engine, scan_task, score_task = (
            await strategy_engine.start_multi_scanning_pipeline(
                cache=data_cache,
                order_executor=order_executor,
                preset_definitions=enabled_presets,
                notifier=None,
                market_cap_fetcher=mcap_fetcher,
                rest_data=rest_data,
                special_signals=special_signals,
                scan_interval=300.0,
                top_k=top_k_per_preset,
                max_signals_per_cycle=max_signals_per_cycle,
                min_confidence=min_confidence,
                event_repo=event_repo,
            )
        )
    else:
        logger.warning("未配置启用的评分预设, 扫描链路未启动")

    # ---- Notification ----
    from cryptopilot.notification.notifier import Notifier, Events, EventData
    from cryptopilot.notification.telegram_bot import TelegramBot

    notifier = Notifier()
    preset_runtime_map = {
        preset_name: {
            "risk_budget": float(preset_cfg.get("risk_budget", 0.0) or 0.0),
            "max_concurrent": int(preset_cfg.get("max_concurrent", 1) or 1),
            "exit_template": preset_cfg.get("exit_template", preset_name),
            "buy_threshold": preset_cfg.get("buy_threshold"),
            "sell_threshold": preset_cfg.get("sell_threshold"),
            "stop_loss_pct": float(preset_cfg.get("stop_loss_pct", cfg.risk.stop_loss_pct)),
            "tp1_pct": float(preset_cfg.get("tp1_pct", cfg.scoring.tp_tiers.tp1_pct)),
            "tp2_pct": float(preset_cfg.get("tp2_pct", cfg.scoring.tp_tiers.tp2_pct)),
            "tp3_pct": float(preset_cfg.get("tp3_pct", cfg.scoring.tp_tiers.tp3_pct)),
            "tp1_ratio": float(preset_cfg.get("tp1_ratio", cfg.scoring.tp_tiers.tp1_ratio)),
            "tp2_ratio": float(preset_cfg.get("tp2_ratio", cfg.scoring.tp_tiers.tp2_ratio)),
            "tp3_ratio": float(preset_cfg.get("tp3_ratio", cfg.scoring.tp_tiers.tp3_ratio)),
            "breakeven_offset_pct": float(preset_cfg.get("breakeven_offset_pct", cfg.scoring.tp_tiers.breakeven_offset_pct)),
            "trail_distance_pct": float(preset_cfg.get("trail_distance_pct", cfg.risk.trailing_distance_pct)),
            "trail_activation_pct": float(preset_cfg.get("trail_activation_pct", cfg.risk.trailing_activation_pct)),
            "sideways_defense_minutes": float(preset_cfg.get("sideways_defense_minutes", cfg.scoring.tp_tiers.sideways_defense_minutes)),
            "sideways_exit_minutes": float(preset_cfg.get("sideways_exit_minutes", cfg.scoring.tp_tiers.sideways_exit_minutes)),
            "sideways_range_pct": float(preset_cfg.get("sideways_range_pct", cfg.scoring.tp_tiers.sideways_range_pct)),
            "pre_tp_guard_enabled": bool(preset_cfg.get("pre_tp_guard_enabled", cfg.scoring.tp_tiers.pre_tp_guard_enabled)),
            "pre_tp_guard_min_roi_pct": float(preset_cfg.get("pre_tp_guard_min_roi_pct", cfg.scoring.tp_tiers.pre_tp_guard_min_roi_pct)),
        }
        for preset_name, preset_cfg in enabled_presets.items()
    }

    telegram = TelegramBot(
        token=env.telegram_bot_token,
        chat_id=env.telegram_chat_id,
        allowed_users=[u.strip() for u in env.telegram_allowed_users.split(",") if u.strip()] if env.telegram_allowed_users else [],
    )
    default_runtime_cfg = {
        "stop_loss_pct": float(cfg.risk.stop_loss_pct),
        "tp1_pct": float(cfg.scoring.tp_tiers.tp1_pct),
        "tp2_pct": float(cfg.scoring.tp_tiers.tp2_pct),
        "tp3_pct": float(cfg.scoring.tp_tiers.tp3_pct),
        "tp1_ratio": float(cfg.scoring.tp_tiers.tp1_ratio),
        "tp2_ratio": float(cfg.scoring.tp_tiers.tp2_ratio),
        "tp3_ratio": float(cfg.scoring.tp_tiers.tp3_ratio),
    }

    # Wire Telegram commands to strategy engine
    SEP = "─────────────────────"
    async def get_status_text() -> str:
        """V1 风格系统状态."""
        from datetime import datetime, timezone
        now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        statuses = strategy_engine.get_status()
        ws = data_cache.all_tickers()
        pool_size = candidate_pool.size if candidate_pool else 0
        pos_count = position_manager.position_count
        cb_tripped = circuit_breaker.tripped if circuit_breaker else False
        margin_display = "全仓(共享)"
        total_balance = available_balance = unrealized_pnl = 0.0
        try:
            acct = await order_executor.get_account_info()
            total_balance = acct.total_balance
            available_balance = acct.available_balance
            unrealized_pnl = acct.unrealized_pnl
            if acct.margin_ratio > 0.0001:
                margin_display = f"{acct.margin_ratio * 100:.2f}%"
        except Exception:
            pass

        lines = [
            f"📊 <b>宙斯交易中枢 | 系统状态</b>",
            f"🕒 <code>{now_str} UTC</code>",
            SEP,
            f"💵 <b>余额</b>: {total_balance:.2f} USDT | 可用 {available_balance:.2f}",
            f"📈 <b>浮动盈亏</b>: {unrealized_pnl:+.2f} USDT",
            f"🛡️ <b>保证金</b>: {margin_display}",
            "",
            f"🔍 <b>行情</b>: {len(ws)} 币种 | 候选池 {pool_size}",
            f"📊 <b>持仓</b>: {pos_count} / {cfg.risk.max_positions}",
            f"⚡ <b>风控</b>: {'🟢 正常' if not cb_tripped else '🔴 已熔断'}",
            f"📡 <b>行情源</b>: {'WebSocket' if not use_rest_poller else 'REST'}",
            "",
            f"<b>活跃策略</b> ({strategy_engine.active_count}/{strategy_engine.total_count}):",
        ]
        for s in statuses[:8]:
            state = '⏸' if s.get('paused') else '▶'
            pos_tag = ' [持仓]' if s.get('has_position') else ''
            lines.append(f"  {state} <b>{s.get('strategy_id','?')}</b> — {s.get('symbol','?')}{pos_tag}")
        lines.append(SEP)
        lines.append("✅ 系统正常运行" if not cb_tripped else "⚠️ 熔断中，暂停开仓")
        return "\n".join(lines)

    async def get_positions_text() -> str:
        """V1 风格持仓明细."""
        positions = position_manager.get_all_positions()
        if not positions:
            return "📭 <b>宙斯交易中枢 | 持仓明细</b>\n" + SEP + "\n当前无持仓，系统待命。"
        lines = [f"📊 <b>宙斯交易中枢 | 持仓明细</b> ({len(positions)} 个)", SEP]
        for p in positions:
            sym = p.get("symbol", "?")
            side = "📈 LONG" if p.get("side") == "LONG" else "📉 SHORT"
            qty = abs(p.get("qty", 0))
            entry = float(p.get("entry_price", 0) or 0)
            mark = float(p.get("mark_price", 0) or 0)
            pnl = float(p.get("unrealized_pnl", 0) or 0)
            lev = p.get("leverage", 1)
            roi = ((mark - entry) / entry * 100 * lev) if entry > 0 else 0
            if side == "📉 SHORT":
                roi = -roi
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            strategy_preset = p.get("strategy_preset", "") or ""
            support_presets = p.get("support_presets", "") or ""
            lines.append(
                f"<b>{sym}</b> {side} · {lev}x\n"
                f"  入场: <code>{entry:.5f}</code> → 标记: <code>{mark:.5f}</code>\n"
                f"  数量: {qty} | 未实现: {pnl_emoji} <code>${pnl:+.2f}</code> ({roi:+.2f}% ROI)\n"
                f"  策略: <code>{strategy_preset or '--'}</code>"
                + (f" | 支持: <code>{support_presets}</code>\n" if support_presets else "\n")
            )
            # 保护单状态
            try:
                orders = order_manager.get_open_orders(sym)
            except Exception:
                orders = []
            if orders:
                sls = [o for o in orders if o.get("type") in ("STOP_MARKET", "STOP")]
                tps = [o for o in orders if o.get("type") in ("TAKE_PROFIT_MARKET", "LIMIT", "TAKE_PROFIT")]
                if sls:
                    sl_price = sls[0].get("stop_price") or sls[0].get("price", 0)
                    lines.append(f"  🛑 SL: <code>{float(sl_price):.5f}</code>")
                if tps:
                    tp_strs = []
                    for o in tps[:3]:
                        tp_price = o.get("price") or o.get("stop_price", 0)
                        tp_strs.append(f"TP{o.get('client_order_id','?')[-2:]}:<code>{float(tp_price):.5f}</code>")
                    lines.append(f"  🎯 {' · '.join(tp_strs)}")
            else:
                lines.append(f"  ⚠️ 无保护单")
            lines.append("")
        return "\n".join(lines)

    telegram.set_callbacks(
        status_func=get_status_text,
        pause_func=strategy_engine.pause_all,
        resume_func=strategy_engine.resume_all,
        close_all_func=lambda: signal_queue.put(("EMERGENCY_CLOSE_ALL", {})),
        positions_func=get_positions_text,
    )

    if cfg.notification.telegram_enabled:
        await telegram.start()
        notifier.register(Events.ORDER_FILLED, telegram.on_event)
        notifier.register(Events.POSITION_OPENED, telegram.on_event)
        notifier.register(Events.POSITION_CLOSED, telegram.on_event)
        notifier.register(Events.TAKE_PROFIT_TRIGGERED, telegram.on_event)
        notifier.register(Events.STOP_LOSS_TRIGGERED, telegram.on_event)
        notifier.register(Events.PROTECTION_PLACED, telegram.on_event)
        notifier.register(Events.CIRCUIT_BREAKER_ACTIVATED, telegram.on_event)
        notifier.register(Events.STRATEGY_ERROR, telegram.on_event)
        notifier.register(Events.WARNING, telegram.on_event)
        notifier.register(Events.DAILY_REPORT, telegram.on_event)

        # V1 风格启动通知
        from datetime import datetime, timezone
        now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        sc = cfg.scoring
        risk_cfg = cfg.risk
        preset = raw_cfg.get("scoring", {}).get("active_preset", "composite")
        enabled_preset_labels = ", ".join(enabled_presets.keys()) if enabled_presets else preset
        lev = risk_cfg.default_leverage
        risk_pct = risk_cfg.risk_per_trade
        max_pos = risk_cfg.max_positions
        rl = "进取" if risk_pct >= 1.0 else "稳健"
        src = "WebSocket 实时" if not use_rest_poller else f"REST {poll_interval}s"
        strategy_lines = []
        for preset_name, runtime_cfg in preset_runtime_map.items():
            strategy_lines.append(
                f"• <code>{preset_name}</code> | 风险 {float(runtime_cfg.get('risk_budget', 0.0)):.2f}% | "
                f"并发 {int(runtime_cfg.get('max_concurrent', 0) or 0)} | "
                f"模板 <code>{runtime_cfg.get('exit_template', preset_name)}</code>"
            )

        startup_msg = (
            f"🚀 <b>宙斯交易中枢 | 系统启动</b>\n"
            f"🕒 <code>{now_str}</code>\n"
            f"\n"
            f"🔥 <b>风险等级</b>: <code>{rl}</code>\n"
            f"\n"
            f"💵 <b>模式</b>: <code>{'🟢 LIVE' if not cfg.exchange.testnet else '🟡 TESTNET'}</code>\n"
            f"⚙️ <b>杠杆</b>: <code>{lev}x</code>\n"
            f"🎯 <b>单笔风险</b>: <code>{risk_pct:.2f}%</code>\n"
            f"\n"
            f"🛑 <b>止损</b>: <code>{risk_cfg.stop_loss_pct:.1f}%</code>\n"
            f"🧩 <b>启用策略</b>: <code>{enabled_preset_labels}</code>\n"
            f"\n"
            f"🔍 <b>扫描范围</b>: <code>{sc.scan_top_n}</code> 币种\n"
            f"⏱ <b>扫描间隔</b>: <code>{sc.scan_interval_sec}</code> 秒\n"
            f"📛 <b>最大持仓</b>: <code>{max_pos}</code>\n"
            f"📡 <b>行情源</b>: <code>{src}</code>\n"
            f"{SEP}\n"
            f"🧭 <b>策略与预算</b>\n"
            f"{chr(10).join(strategy_lines)}\n"
            f"{SEP}\n"
            f"✅ 系统已就绪"
        )
        await telegram.send_message(startup_msg)

    # ---- Market data -> Strategy dispatch ----
    # Subscribe the strategy engine to market data updates
    async def on_market_data(msg) -> None:
        from cryptopilot.market.types import StreamMessage, KlineData, TickerData

        if isinstance(msg.data, KlineData):
            await strategy_engine.dispatch_kline(msg.data)
        elif isinstance(msg.data, TickerData):
            await strategy_engine.dispatch_tick(msg.data)

    data_cache.subscribe(on_market_data)

    # ---- Signal Processor ----
    async def signal_processor() -> None:
        """Consume signals from the queue and execute orders."""
        from cryptopilot.strategy.base import Signal

        while True:
            item = await signal_queue.get()

            try:
                # Handle emergency close
                if isinstance(item, tuple) and item[0] == "EMERGENCY_CLOSE_ALL":
                    await _emergency_close(order_executor, position_manager)
                    continue

                signal: Signal = item

                # Circuit breaker check
                if circuit_breaker.tripped:
                    logger.warning(f"信号被拒绝 — 熔断已触发: {signal.action}")
                    continue

                # ---- 开仓风控检查 ----
                if signal.action in ("OPEN_LONG", "OPEN_SHORT"):
                    # 1. 最大持仓数检查
                    pos_count = position_manager.position_count
                    max_pos = cfg.risk.max_positions
                    if pos_count >= max_pos:
                        logger.warning(
                            f"信号被拒绝 — 已达最大持仓数 ({pos_count}/{max_pos}): "
                            f"{signal.symbol} {signal.action}"
                        )
                        if event_repo is not None:
                            from cryptopilot.persistence.models import StrategyEvent

                            await event_repo.create(StrategyEvent(
                                strategy_id=signal.strategy_id,
                                event_type="signal_rejected",
                                symbol=signal.symbol,
                                details='{"reason":"max_positions"}',
                            ))
                        continue

                    # 2. 同币种重复开仓检查
                    existing = position_manager.get_position(signal.symbol)
                    if existing and abs(existing.get("qty", 0)) > 0:
                        logger.info(
                            f"信号跳过 — {signal.symbol} 已有持仓 "
                            f"({existing.get('side', '')} {existing.get('qty', 0)})"
                        )
                        if event_repo is not None:
                            from cryptopilot.persistence.models import StrategyEvent

                            await event_repo.create(StrategyEvent(
                                strategy_id=signal.strategy_id,
                                event_type="signal_rejected",
                                symbol=signal.symbol,
                                details='{"reason":"existing_position"}',
                            ))
                        continue

                    # 3. 每策略最大并发数检查，第二阶段先使用 entry_reason 作为持仓回溯标记
                    preset_name = signal.preset or signal.strategy_id.split("_", 1)[0]
                    preset_runtime = preset_runtime_map.get(preset_name, {})
                    max_concurrent = int(preset_runtime.get("max_concurrent", 0) or 0)
                    if max_concurrent > 0:
                        same_preset_positions = 0
                        for pos in position_manager.get_all_positions():
                            entry_reason = str(pos.get("entry_reason", "") or "")
                            if entry_reason.startswith(f"preset:{preset_name}|"):
                                same_preset_positions += 1
                        if same_preset_positions >= max_concurrent:
                            logger.warning(
                                f"信号被拒绝 — {preset_name} 已达最大并发数 "
                                f"({same_preset_positions}/{max_concurrent}): {signal.symbol} {signal.action}"
                            )
                            if event_repo is not None:
                                from cryptopilot.persistence.models import StrategyEvent

                                await event_repo.create(StrategyEvent(
                                    strategy_id=signal.strategy_id,
                                    event_type="signal_rejected",
                                    symbol=signal.symbol,
                                    details='{"reason":"preset_max_concurrent"}',
                                ))
                            continue

                # Look up strategy-specific risk config
                preset_name = signal.preset or signal.strategy_id.split("_", 1)[0]
                preset_runtime = preset_runtime_map.get(preset_name, {})
                strat_risk = dict(preset_runtime)
                strat_risk.setdefault("risk_budget", 0.0)
                strat_risk.setdefault("max_concurrent", 1)
                strat_risk.setdefault("exit_template", preset_name)

                # Execute signal
                await _execute_signal(
                    signal,
                    order_executor,
                    order_manager,
                    position_manager,
                    position_sizer,
                    circuit_breaker,
                    notifier,
                    strat_risk.get("leverage", cfg.risk.default_leverage),
                    risk_config=strat_risk,
                    event_repo=event_repo,
                )

                # Update trailing stops
                _update_trailing_stops(
                    signal, trailing_stops, order_executor, data_cache
                )

            except BaseException:
                logger.exception(f"信号处理错误: {item}")
            finally:
                signal_queue.task_done()

    signal_processor_task = asyncio.create_task(signal_processor(), name="signal_processor")
    logger.info("信号处理器已启动")

    # ---- Report Generator ----
    from cryptopilot.persistence.reports import ReportGenerator

    report_generator = ReportGenerator(db)

    # ---- Margin Monitor ----
    from cryptopilot.risk.margin_monitor import MarginMonitor

    margin_monitor = MarginMonitor(
        check_interval=30.0,
        warning_threshold=0.80,
        critical_threshold=0.90,
    )

    # Wire margin alerts to the notifier
    def on_margin_alert(alert):
        notifier.notify(EventData(
            event=Events.WARNING if alert.level == "WARNING" else Events.ERROR,
            message=alert.message,
            symbol=alert.symbol,
        ))

    async def on_margin_emergency():
        """Emergency: reduce positions when margin is critical."""
        logger.error("保证金紧急状态 — 正在尝试减仓")
        all_pos = position_manager.get_all_positions()
        for pos_info in all_pos:
            sym = pos_info.get("symbol", "")
            if sym:
                await order_executor.cancel_all_orders(sym)
                # Close through signal queue to use proper flow
                await signal_queue.put(("EMERGENCY_CLOSE_ALL", {"symbol": sym}))

    margin_monitor.set_callbacks(
        alert_callback=on_margin_alert,
        emergency_callback=on_margin_emergency,
    )

    margin_task = asyncio.create_task(
        margin_monitor.start(order_executor, position_manager, notifier),
        name="margin_monitor",
    )

    # ---- Health check web server ----
    from cryptopilot.web.health import create_health_app
    from cryptopilot.web.dashboard import add_dashboard_route
    import uvicorn

    health_app = create_health_app(
        strategy_engine=strategy_engine,
        position_manager=position_manager,
        websocket_manager=ws_manager,
        circuit_breaker=circuit_breaker,
        notifier=notifier,
        db=db,
        report_generator=report_generator,
        margin_monitor=margin_monitor,
        candidate_pool=candidate_pool,
        scoring_engine=scoring_engine,
        order_executor=order_executor,
        scanner=scanner_obj,
        preset_name=active_preset,
        preset_configs=preset_runtime_map,
        signal_queue=signal_queue,
        cache=data_cache,
    )
    add_dashboard_route(health_app)

    uvicorn_config = uvicorn.Config(
        health_app,
        host=cfg.web.host,
        port=cfg.web.port,
        log_level="warning",
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)

    # ---- Profit Locker (background task) ----
    from cryptopilot.strategy.base import Signal as BaseSignal
    from cryptopilot.risk.profit_locker import ProfitLocker
    from cryptopilot.risk.exit_manager import build_exit_manager_from_runtime

    exit_managers = {
        preset_name: build_exit_manager_from_runtime(
            runtime_cfg,
            executor=order_executor,
            position_manager=position_manager,
            notifier=notifier,
            cache=data_cache,
        )
        for preset_name, runtime_cfg in preset_runtime_map.items()
    }
    profit_lockers = {
        preset_name: ProfitLocker(
            activation_pct=float(runtime_cfg.get("tp1_pct", 3.0)),
            lock_fraction=float(runtime_cfg.get("tp1_ratio", 0.30)),
            breakeven_after_pct=float(runtime_cfg.get("trail_activation_pct", 0.5)),
        )
        for preset_name, runtime_cfg in preset_runtime_map.items()
    }

    async def profit_lock_loop():
        """Periodically check open positions for profit locking opportunities."""
        while True:
            await asyncio.sleep(15)
            try:
                positions = position_manager.get_all_positions()
                for pos in positions:
                    sym = pos.get("symbol", "")
                    strategy_ctx = position_manager.get_position_context(sym) or {}
                    preset_name = strategy_ctx.get("strategy_preset") or "composite"
                    profit_locker = profit_lockers.get(preset_name)
                    if not sym or abs(pos.get("qty", 0)) <= 0:
                        if profit_locker is not None:
                            profit_locker.reset(sym)
                        continue

                    entry = pos.get("entry_price", 0)
                    mark = pos.get("mark_price", 0)
                    side = pos.get("side", "LONG")
                    qty = abs(pos.get("qty", 0))

                    if entry <= 0 or mark <= 0 or qty <= 0 or profit_locker is None:
                        continue

                    # Move stop to breakeven
                    if profit_locker.should_breakeven(sym, entry, mark, side):
                        profit_locker.mark_breakeven(sym)
                        logger.info(f"保本止损: {sym} 止损已移至开仓价 {entry:.4f}")
                        notifier.notify(EventData(
                            event=Events.WARNING,
                            message=f"{sym} 止损已移至保本位 {entry:.4f}",
                            symbol=sym,
                        ))
                        await event_repo.create(StrategyEvent(
                            strategy_id=strategy_ctx.get("strategy_id", sym),
                            event_type="move_stop",
                            symbol=sym,
                            details=(
                                '{"reason":"breakeven_after_profit_lock","preset":"'
                                + preset_name
                                + '"}'
                            ),
                        ))

                    # Partial profit lock
                    if profit_locker.should_lock(sym, entry, mark, side):
                        lock_qty = profit_locker.lock_quantity(qty)
                        profit_locker.mark_locked(sym)
                        # Cancel existing SL/TP, then place new partial close
                        await order_executor.cancel_all_orders(sym)
                        # Emit partial close signal
                        close_action = "CLOSE_LONG" if side == "LONG" else "CLOSE_SHORT"
                        partial_signal = BaseSignal(
                            strategy_id="profit_locker",
                            symbol=sym,
                            action=close_action,
                            order_type="MARKET",
                            price=mark,
                            comment=f"锁利: 浮盈达到 {profit_locker._activation}%，平仓 {profit_locker._lock_fraction*100:.0f}%",
                        )
                        # Reduce the order quantity for partial close
                        partial_signal.stop_loss = 0  # Don't set new SL/TP on close
                        partial_signal.take_profit = 0
                        await signal_queue.put(partial_signal)
                        await event_repo.create(StrategyEvent(
                            strategy_id=strategy_ctx.get("strategy_id", "profit_locker"),
                            event_type="partial_take_profit",
                            symbol=sym,
                            details=(
                                '{"reason":"profit_lock","preset":"'
                                + preset_name
                                + '","lock_fraction":"'
                                + f"{profit_locker._lock_fraction:.2f}"
                                + '"}'
                            ),
                        ))
                        logger.info(
                            f"锁利执行: {sym} 平仓 {lock_qty:.4f} "
                            f"({profit_locker._lock_fraction*100:.0f}%) 价格 {mark:.4f}"
                        )
            except Exception:
                logger.exception("锁利检查出错")

    profit_lock_task = asyncio.create_task(profit_lock_loop(), name="profit_locker")

    # ---- Daily Report Scheduler ----
    async def daily_report_loop():
        """Send a daily performance summary via Telegram at configured time."""
        from datetime import datetime, timezone

        report_hour = 8  # UTC (北京时间约16:00)
        report_minute = 0

        last_report_date = ""
        while True:
            now = datetime.now(tz=timezone.utc)
            today = now.strftime("%Y-%m-%d")
            await asyncio.sleep(60)  # Check every minute

            if today == last_report_date:
                continue
            if now.hour != report_hour or now.minute < report_minute or now.minute >= report_minute + 5:
                continue

            # Generate and send report
            try:
                summary = await report_generator.generate_summary(days=1)
                from cryptopilot.web.health import _fetch_income_pnl

                pnl_snapshot = await _fetch_income_pnl(order_executor) or {}
                positions = position_manager.get_all_positions()
                acct = await order_executor.get_account_info()
                trades_today = pnl_snapshot.get("trade_count_1d", summary["total_trades"])
                win_rate_today = pnl_snapshot.get("win_rate_1d", summary["win_rate"])
                total_pnl_today = pnl_snapshot.get("net_pnl_1d", summary["total_pnl"])
                local_metrics_match = summary["total_trades"] == trades_today
                strategy_breakdown = summary.get("strategies", {}) or {}

                lines = [
                    f"每日报告 — {today}",
                    "",
                    f"总余额: ${acct.total_balance:.2f}",
                    f"可用余额: ${acct.available_balance:.2f}",
                    f"未实现盈亏: ${acct.unrealized_pnl:.2f}",
                    f"当前持仓: {len(positions)} 个",
                    "",
                    f"今日交易: {trades_today} 笔",
                    f"胜率: {win_rate_today}%",
                    f"总盈亏: ${total_pnl_today}",
                    f"最大回撤: {summary['max_drawdown_pct']}%" if local_metrics_match else "最大回撤: --",
                    f"夏普比率: {summary['sharpe_ratio']}" if local_metrics_match else "夏普比率: --",
                ]
                if strategy_breakdown:
                    lines.extend(["", "分策略摘要"])
                    for preset_name, item in strategy_breakdown.items():
                        hold_label = _format_hold_duration(float(item.get("avg_hold_time_seconds", 0) or 0))
                        lines.append(
                            f"- {preset_name}: {int(item.get('trades', 0) or 0)} 笔 | "
                            f"PnL ${float(item.get('pnl', 0) or 0):+.2f} | "
                            f"胜率 {float(item.get('win_rate', 0) or 0):.1f}% | "
                            f"平均持仓 {hold_label}"
                        )
                msg = "\n".join(lines)
                logger.info(f"每日报告已生成:\n{msg}")
                notifier.notify(EventData(event=Events.DAILY_REPORT, message=msg))
                last_report_date = today
            except Exception:
                logger.exception("每日报告生成失败")

    # ---- Account Snapshot Logger ----
    async def account_snapshot_loop():
        while True:
            await asyncio.sleep(300)  # 5 分钟
            try:
                acct = await order_executor.get_account_info()
                await account_repo.create(AccountSnapshot(
                    total_balance=acct.total_balance,
                    available_balance=acct.available_balance,
                    unrealized_pnl=acct.unrealized_pnl,
                    margin_ratio=acct.margin_ratio,
                ))
            except Exception:
                logger.debug("账户快照写入失败", exc_info=True)

    snapshot_task = asyncio.create_task(account_snapshot_loop(), name="account_snapshot")

    daily_task = asyncio.create_task(daily_report_loop(), name="daily_report")

    # ---- Start all services ----
    if ws_already_started:
        ws_task = ws_task_test  # reuse already-started task
    else:
        ws_task = asyncio.create_task(ws_manager.start(), name="ws_manager")
    web_task = asyncio.create_task(uvicorn_server.serve(), name="health_web")

    logger.info(f"健康检查: http://{cfg.web.host}:{cfg.web.port}/health")
    source_name = "REST 轮询" if use_rest_poller else "WebSocket"
    logger.info(f"行情源: {source_name} (全市场, {'REST '+str(poll_interval)+'s' if use_rest_poller else '实时推送'})")
    logger.info(f"传统策略: {strategy_engine.total_count} 个已注册")
    logger.info("=" * 60)
    logger.info("CryptoPilot 运行中")
    logger.info("=" * 60)

    # ---- Shutdown handler ----
    shutdown_event = asyncio.Event()

    def _shutdown_signal(sig, frame):
        logger.info(f"收到信号 {sig}，正在关闭...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, _shutdown_signal)
    signal.signal(signal.SIGTERM, _shutdown_signal)

    # ---- Wait for shutdown ----
    await shutdown_event.wait()

    logger.info("正在关闭...")

    # Stop margin monitor
    await margin_monitor.stop()
    margin_task.cancel()
    try:
        await margin_task
    except (asyncio.CancelledError, Exception):
        pass

    # Stop profit locker
    profit_lock_task.cancel()
    try:
        await profit_lock_task
    except (asyncio.CancelledError, Exception):
        pass

    # Stop daily report
    daily_task.cancel()
    try:
        await daily_task
    except (asyncio.CancelledError, Exception):
        pass

    # Stop account snapshot
    snapshot_task.cancel()
    try:
        await snapshot_task
    except (asyncio.CancelledError, Exception):
        pass

    # 取消 history_sync 后台任务
    if history_sync_task is not None:
        history_sync_task.cancel()
        try:
            await history_sync_task
        except (asyncio.CancelledError, Exception):
            pass

    # 取消 signal_processor 任务
    if signal_processor_task is not None:
        signal_processor_task.cancel()
        try:
            await signal_processor_task
        except (asyncio.CancelledError, Exception):
            pass

    # Stop scanning pipeline
    if scanner_obj:
        await scanner_obj.stop()
    for t in [scan_task, score_task, mcap_task]:
        if t:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    # Stop strategies
    await strategy_engine.stop_all()

    # Stop WebSocket
    await ws_manager.stop()
    ws_task.cancel()
    try:
        await ws_task
    except (asyncio.CancelledError, Exception):
        pass

    # Stop web server
    web_task.cancel()
    try:
        await web_task
    except (asyncio.CancelledError, Exception):
        pass

    # Stop Telegram
    await telegram.stop()

    # Shutdown WS trading client + user data stream
    if user_data:
        await user_data.stop()
    if _user_data_task is not None:
        _user_data_task.cancel()
        try:
            await _user_data_task
        except (asyncio.CancelledError, Exception):
            pass
    if ws_trader:
        await ws_trader.disconnect()

    # Shutdown order executor
    await order_executor.shutdown()

    # Close database
    await db.close()

    logger.info("程序已关闭，期待下次对接")


# ----------------------------------------------------------------
# Signal execution
# ----------------------------------------------------------------

async def _execute_signal(
    signal,
    executor,
    order_manager,
    position_manager,
    position_sizer,
    circuit_breaker,
    notifier,
    default_leverage: int,
    risk_config: dict | None = None,
    event_repo=None,
) -> None:
    """Translate a Signal into exchange orders with risk checks.

    For OPEN signals: submits main order, then automatically places
    exchange-native stop-loss and take-profit orders.
    For CLOSE signals: cancels all open orders (including SL/TP) first.
    """
    from cryptopilot.trading.order_executor import OrderRequest, _make_client_id
    from cryptopilot.trading.precision import clamp_qty, clamp_price

    # Determine order side
    if signal.action == "OPEN_LONG":
        side = "BUY"
        pos_side = "LONG"
    elif signal.action == "OPEN_SHORT":
        side = "SELL"
        pos_side = "SHORT"
    elif signal.action == "CLOSE_LONG":
        side = "SELL"
        pos_side = "LONG"
    elif signal.action == "CLOSE_SHORT":
        side = "BUY"
        pos_side = "SHORT"
    else:
        logger.error(f"未知信号动作: {signal.action}")
        return

    logical_pos_side = pos_side

    # For CLOSE signals: cancel any open SL/TP orders first
    if signal.action.startswith("CLOSE"):
        await executor.cancel_all_orders(signal.symbol)
        logger.info(f"已撤销 {signal.symbol} 的挂单，准备平仓")

    # Check if we already have an open order (skip duplicate entries)
    if signal.action.startswith("OPEN"):
        await order_manager.sync_with_exchange(executor)
    if order_manager.has_open_order(signal.symbol) and signal.action.startswith("OPEN"):
        logger.info(f"信号跳过 — {signal.symbol} 已有挂单")
        return

    # Get account info for sizing
    acct = await executor.get_account_info()
    circuit_breaker.update(acct.total_balance)

    # 检测持仓模式: 单向模式不传 positionSide
    is_hedge = await executor.get_position_mode()
    if not is_hedge:
        pos_side = ""
    exchange_pos_side = pos_side

    if circuit_breaker.tripped:
        return

    # Use signal's price, or 0 (will be filled by market order)
    entry_price = signal.price

    # Size the position (for OPEN signals)
    if signal.action in ("OPEN_LONG", "OPEN_SHORT"):
        risk = risk_config or {}
        # Set leverage on exchange before opening
        try:
            await executor.set_leverage(signal.symbol, default_leverage)
            await executor.set_margin_type(signal.symbol, "CROSSED")
        except Exception:
            logger.debug(f"杠杆/保证金设置跳过 {signal.symbol} (可能已设置或不支持)", exc_info=True)

        stop_loss_pct = signal.stop_loss_pct or risk.get("stop_loss_pct", 5.0)  # 山寨币波动大, 3%太窄
        qty = position_sizer.calculate(
            balance=acct.available_balance,
            entry_price=entry_price,
            stop_loss_pct=stop_loss_pct,
            leverage=default_leverage,
            risk_pct=float(risk.get("risk_budget", 0.0) or cfg.risk.risk_per_trade or 1.5),
        )
    else:
        # Close position — use existing position quantity
        pos = position_manager.get_position(signal.symbol)
        qty = abs(pos["qty"]) if pos else 0

    if qty <= 0:
        logger.warning(f"计算出的数量为零: {signal.action} {signal.symbol}")
        return

    req = OrderRequest(
        symbol=signal.symbol,
        side=side,
        order_type=signal.order_type,
        quantity=qty,
        price=signal.price,
        position_side=exchange_pos_side,
        reduce_only=signal.action.startswith("CLOSE"),
    )

    # 下单: REST 直连 (WS 连接不稳定, 直接走 REST 更可靠)
    try:
        result = await executor.create_order(req)
    except BaseException:
        logger.exception("REST 下单失败, 信号丢弃")
        return

    await order_manager.record_order(result, signal.strategy_id or (signal.preset or ""))

    # Confirm the actual fill price, especially for async market closes.
    position_before_close = position_manager.get_position(signal.symbol) if signal.action.startswith("CLOSE") else None
    fallback_fill_price = entry_price
    if signal.action.startswith("CLOSE") and position_before_close is not None:
        fallback_fill_price = float(position_before_close.get("mark_price", 0) or signal.price or 0)
    result, actual_fill_price = await _confirm_filled_order(
        executor,
        signal.symbol,
        result,
        fallback_price=fallback_fill_price,
    )

    # Notify
    if signal.action.startswith("OPEN"):
        await position_manager.sync_from_exchange(executor)

        # Verify the position exists before placing protection orders.
        pos_check = position_manager.get_position(signal.symbol)
        if not pos_check or abs(pos_check.get("qty", 0)) <= 0:
            logger.error(f"{signal.symbol} 仓位不存在, 无法放置 SL/TP — 撤单")
            await executor.cancel_all_orders(signal.symbol)
            # Try to close if somehow partially filled
            try:
                await executor.create_order(OrderRequest(
                    symbol=signal.symbol,
                    side="SELL" if logical_pos_side == "LONG" else "BUY",
                    order_type="MARKET", quantity=qty,
                    reduce_only=True, position_side=exchange_pos_side,
                ))
            except Exception:
                logger.debug("紧急平仓降级尝试失败", exc_info=True)
            return

        fill_price = actual_fill_price if actual_fill_price > 0 else entry_price

        # 🆕 V2 多因子开仓通知
        factor_labels = [f"{name}" for name, direction, s in (signal.top_factors or [])]
        factor_reason = ",".join(label for label in factor_labels[:3]) if factor_labels else "SCORE_TRIGGER"
        preset_name = signal.preset or signal.strategy_id.split("_", 1)[0]
        entry_reason = f"preset:{preset_name}|{factor_reason}"
        support_presets = list(getattr(signal, "supporting_presets", []) or [])
        opportunity_type = getattr(signal, "opportunity_type", "") or preset_name
        await _record_strategy_event(
            event_repo,
            signal.strategy_id,
            "position_opened",
            signal.symbol,
            {
                "preset": preset_name,
                "support_presets": ",".join(support_presets),
                "entry_reason": entry_reason,
                "opportunity_type": opportunity_type,
            },
        )
        notifier.position_opened(
            symbol=signal.symbol,
            side=logical_pos_side,
            price=fill_price,
            qty=qty,
            leverage=default_leverage,
            score=signal.score,
            top_factors=factor_labels,
            sl_price=0.0,  # 后面填
            tp_tiers=[],   # 后面填
            margin_type="CROSSED",
            entry_reason=entry_reason,
            strategy_id=signal.strategy_id,
            strategy_preset=preset_name,
            support_presets=support_presets,
            opportunity_type=opportunity_type,
        )

        # 记录开仓时间 (用于平仓通知计算持仓时长)
        _execute_signal._position_open_time = getattr(_execute_signal, '_position_open_time', {})
        _execute_signal._position_open_time[signal.symbol] = time.time()

        # ---- Place Take-Profit orders (LIMIT, 交易所挂单) + SL via ALGO ORDER ----
        sl_success = False
        sl_price = 0.0
        if fill_price > 0:
            risk = risk_config or {}
            sl_pct = signal.stop_loss_pct or risk.get("stop_loss_pct", 5.0)
            if logical_pos_side == "LONG":
                sl_price = fill_price * (1 - sl_pct / 100)
            else:
                sl_price = fill_price * (1 + sl_pct / 100)

            if sl_price > 0:
                try:
                    sl_req = OrderRequest(
                        symbol=signal.symbol,
                        side="SELL" if logical_pos_side == "LONG" else "BUY",
                        order_type="STOP_MARKET",
                        quantity=qty,
                        stop_price=sl_price,
                        reduce_only=True,
                        position_side=exchange_pos_side,
                        client_order_id=_make_client_id("sl"),
                    )
                    sl_r = await executor.create_order(sl_req)
                    sl_success = sl_r.order_id > 0
                    logger.info(f"SL 已挂单: {signal.symbol} @{sl_price:.5f} orderId={sl_r.order_id}")
                except Exception as exc:
                    logger.error(f"SL 挂单失败: {signal.symbol} {exc}")
        tp_count = 0
        try:

            # 精确计算 TP 价格
            risk = risk_config or {}
            tp1_pct = float(risk.get("tp1_pct", 3.0))
            tp2_pct = float(risk.get("tp2_pct", 6.0))
            tp3_pct = float(risk.get("tp3_pct", 10.0))
            tp1_ratio = float(risk.get("tp1_ratio", 0.30))
            tp2_ratio = float(risk.get("tp2_ratio", 0.30))
            tp3_ratio = float(risk.get("tp3_ratio", 0.40))
            if logical_pos_side == "LONG":
                tp1 = fill_price * (1 + tp1_pct / 100)
                tp2 = fill_price * (1 + tp2_pct / 100)
                tp3 = fill_price * (1 + tp3_pct / 100)
            else:
                tp1 = fill_price * (1 - tp1_pct / 100)
                tp2 = fill_price * (1 - tp2_pct / 100)
                tp3 = fill_price * (1 - tp3_pct / 100)

            tp_reqs = []
            close_side = "SELL" if logical_pos_side == "LONG" else "BUY"
            for tp_price, tp_qty_ratio, label in [
                (tp1, tp1_ratio, "TP1"), (tp2, tp2_ratio, "TP2"), (tp3, tp3_ratio, "TP3")
            ]:
                tp_qty = qty * tp_qty_ratio
                # Precision clamping
                filters = executor.get_symbol_filters(signal.symbol)
                if filters:
                    tp_qty = clamp_qty(tp_qty, filters["step_size"],
                                      filters.get("min_qty", 0), filters["max_qty"])
                    tp_price_c = clamp_price(tp_price, filters["tick_size"])
                else:
                    tp_price_c = tp_price
                if tp_qty > 0:
                    tp_reqs.append(OrderRequest(
                        symbol=signal.symbol, side=close_side,
                        order_type="LIMIT", quantity=tp_qty,
                        price=tp_price_c, reduce_only=True,
                        position_side=exchange_pos_side,
                        client_order_id=_make_client_id(label.lower()),
                        time_in_force="GTC",
                    ))

            for tp_req in tp_reqs:
                try:
                    tp_r = await executor.create_order(tp_req)
                    await order_manager.record_order(tp_r, signal.strategy_id)
                    tp_count += 1
                except Exception as exc_tp:
                    logger.warning(f"TP 下单失败: {tp_req.symbol} {exc_tp}")

            sl_tp_placed = sl_success and tp_count == 3
            logger.info(
                f"保护单: {signal.symbol} SL={sl_price:.5f} "
                f"TP1={tp1:.5f}({tp1_ratio*100:.0f}%) TP2={tp2:.5f}({tp2_ratio*100:.0f}%) TP3={tp3:.5f}({tp3_ratio*100:.0f}%) "
                f"[{tp_count}/3 个TP已放置]"
            )

            # 🆕 V2 保护单通知
            if sl_tp_placed:
                sl_pct_val = abs(sl_price - fill_price) / fill_price * 100
                tp_placed = []
                tp_defs = [(tp1, tp1_pct, tp1_ratio, 1), (tp2, tp2_pct, tp2_ratio, 2), (tp3, tp3_pct, tp3_ratio, 3)]
                for tp_price_val, tp_pct_val, tp_ratio_val, tp_tier in tp_defs:
                    tp_placed.append({
                        "tier": tp_tier,
                        "price": tp_price_val,
                        "pct": tp_pct_val,
                        "qty_ratio": tp_ratio_val,
                    })
                notifier.protection_placed(
                    symbol=signal.symbol,
                    sl_price=sl_price,
                    sl_pct=sl_pct_val,
                    tp_tiers=tp_placed,
                )
                await _record_strategy_event(
                    event_repo,
                    signal.strategy_id,
                    "protection_placed",
                    signal.symbol,
                    {
                        "sl_price": f"{sl_price:.8f}",
                        "tp_tiers": ",".join(f"TP{item['tier']}" for item in tp_placed),
                        "tp1_price": f"{tp1:.8f}",
                        "tp2_price": f"{tp2:.8f}",
                        "tp3_price": f"{tp3:.8f}",
                        "tp1_ratio": f"{tp1_ratio:.4f}",
                        "tp2_ratio": f"{tp2_ratio:.4f}",
                        "tp3_ratio": f"{tp3_ratio:.4f}",
                        "preset": preset_name,
                    },
                )
            elif sl_price <= 0:
                logger.warning(f"{signal.symbol} 止损价无效, SL={sl_price}")
            else:
                logger.warning(f"{signal.symbol} TP 未放置 (SL=本地跟踪)")
        except Exception:
            logger.exception(f"{signal.symbol} TP 提交异常")
    else:
        close_fill_price = actual_fill_price if actual_fill_price > 0 else (result.avg_price if result.avg_price > 0 else 0.0)
        pnl = _calc_pnl(position_manager, signal.symbol, close_fill_price, qty)

        # 🆕 V2 平仓通知 — 带持仓时长和退出原因
        pos = position_before_close or position_manager.get_position_context(signal.symbol)
        entry_px = pos.get("entry_price", 0) if pos else 0
        pnl_pct = ((close_fill_price - entry_px) / entry_px * 100) if entry_px > 0 else 0
        if logical_pos_side == "SHORT":
            pnl_pct = -pnl_pct

        # Compute hold duration from in-memory open time or persisted position time.
        open_times = getattr(_execute_signal, '_position_open_time', {})
        open_ts = _get_position_open_ts(pos, open_times, signal.symbol)
        hold_dur = ""
        hold_seconds = 0.0
        if open_ts:
            dur_sec = max(time.time() - open_ts, 0.0)
            hold_seconds = dur_sec
            hold_dur = _format_hold_duration(dur_sec)

        # Infer the exit reason for the operator-facing close notification.
        if signal.action.startswith("CLOSE"):
            reason = signal.comment or ""
            if "sl" in reason.lower() or "stop" in reason.lower():
                exit_reason = "SL_HIT"
            elif "tp" in reason.lower() or "profit" in reason.lower():
                exit_reason = "TP_HIT"
            elif "manual" in reason.lower():
                exit_reason = "MANUAL"
            else:
                exit_reason = "SIGNAL_CLOSE"
        else:
            exit_reason = "MARKET_CLOSE"

        # Reuse the recorded entry reason when sending the close notification.
        pos_entry_reason = pos.get("entry_reason", "") if pos else ""
        position_strategy_id = pos.get("strategy_id", "") if pos else ""
        position_strategy_preset = pos.get("strategy_preset", "") if pos else ""
        position_support_presets = [
            item.strip() for item in str(pos.get("support_presets", "") if pos else "").split(",") if item.strip()
        ]
        position_opportunity = ""
        if pos_entry_reason.startswith("preset:"):
            _, _, factor_reason = pos_entry_reason.partition("|")
            position_opportunity = factor_reason or position_strategy_preset

        await position_manager.mark_closed(
            signal.symbol,
            side=pos.get("side", pos_side) if pos else pos_side,
            exit_reason=exit_reason,
            exit_price=close_fill_price,
            exit_time=datetime.now(tz=timezone.utc).isoformat(),
            pnl=pnl,
            pnl_pct=pnl_pct,
        )
        await _record_strategy_event(
            event_repo,
            position_strategy_id or signal.strategy_id,
            "position_closed",
            signal.symbol,
            {
                "preset": position_strategy_preset or (signal.preset or ""),
                "entry_reason": pos_entry_reason,
                "exit_reason": exit_reason,
                "pnl": f"{pnl:.8f}",
                "exit_price": close_fill_price,
                "tp_tiers_filled": str(pos.get("tp_tiers_filled", "") or "") if pos else "",
            },
        )

        notifier.position_closed(
            symbol=signal.symbol,
            side=logical_pos_side,
            exit_price=close_fill_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            hold_duration=hold_dur,
            entry_reason=pos_entry_reason,
            entry_price=entry_px,
            hold_seconds=hold_seconds,
            leverage=int(pos.get("leverage", 0) or 0) if pos else 0,
            strategy_id=position_strategy_id or signal.strategy_id,
            strategy_preset=position_strategy_preset or (signal.preset or ""),
            support_presets=position_support_presets,
            opportunity_type=position_opportunity,
        )

    logger.info(f"订单已执行: {result.status} {side} {qty} {signal.symbol} [id={result.order_id}]")

    # Sync positions — then stamp entry_reason for newly opened position
    await position_manager.sync_from_exchange(executor)
    # Save entry_reason to DB (sync_from_exchange clears metadata on new positions)
    if signal.action.startswith("OPEN") and entry_reason:
        try:
            await position_manager.set_strategy_context(
                signal.symbol,
                strategy_id=signal.strategy_id,
                strategy_preset=signal.preset or signal.strategy_id.split("_", 1)[0],
                support_presets=list(getattr(signal, "supporting_presets", []) or []),
                entry_reason=entry_reason,
                stop_loss_price=sl_price if signal.action.startswith("OPEN") else None,
                take_profit_price=tp3 if signal.action.startswith("OPEN") else None,
                current_stop=sl_price if signal.action.startswith("OPEN") else None,
                initial_qty=qty if signal.action.startswith("OPEN") else None,
            )
        except Exception:
            pass


def _calc_pnl(position_manager, symbol: str, close_price: float, qty: float) -> float:
    """Estimate P&L from a close."""
    pos = position_manager.get_position(symbol)
    if pos:
        entry = pos.get("entry_price", 0)
        side = pos.get("side", "LONG")
        if side == "LONG":
            return (close_price - entry) * qty
        else:
            return (entry - close_price) * qty
    return 0.0


def _update_trailing_stops(signal, trailing_stops, executor, cache) -> None:
    """Update trailing stops for positions affected by the signal."""
    from cryptopilot.risk.trailing_stop import TrailingStop

    ts = trailing_stops.get(signal.strategy_id)
    if ts is None:
        return

    ticker = cache.get_ticker(signal.symbol)
    if ticker is None:
        return

    new_stop = ts.update(ticker.price)
    if new_stop is not None:
        # Adjust existing exchange stop-loss orders here (future improvement)
        logger.info(f"移动止损已更新 {signal.symbol}: ${new_stop:.4f}")


def _ws_to_order_result(raw: dict):
    """将 WS 交易 API 返回的 dict 转为 OrderResult."""
    from cryptopilot.trading.order_executor import OrderResult
    return OrderResult(
        symbol=raw.get("symbol", ""),
        order_id=raw.get("orderId", 0),
        client_order_id=raw.get("clientOrderId", ""),
        price=float(raw.get("price", 0) or 0),
        orig_qty=float(raw.get("origQty", raw.get("qty", 0)) or 0),
        executed_qty=float(raw.get("executedQty", raw.get("z", 0)) or 0),
        status=raw.get("status", raw.get("X", "NEW")),
        side=raw.get("side", ""),
        order_type=raw.get("type", raw.get("o", "")),
        position_side=raw.get("positionSide", "BOTH"),
        avg_price=float(raw.get("avgPrice", raw.get("ap", 0)) or 0),
        update_time=raw.get("updateTime", raw.get("T", 0)),
    )


async def _emergency_close(order_executor, position_manager) -> None:
    """紧急平掉所有仓位并撤销全部挂单."""
    positions = position_manager.get_all_positions()
    for pos in positions:
        sym = pos.get("symbol", "")
        if sym:
            await order_executor.cancel_all_orders(sym)
    for pos in positions:
        sym = pos.get("symbol", "")
        side = pos.get("side", "")
        qty = abs(pos.get("qty", 0))
        if sym and qty > 0:
            try:
                close_side = "SELL" if side == "LONG" else "BUY"
                from cryptopilot.trading.order_executor import OrderRequest
                req = OrderRequest(
                    symbol=sym, side=close_side, order_type="MARKET",
                    quantity=qty, reduce_only=True, position_side=side,
                )
                await order_executor.create_order(req)
                logger.warning(f"紧急平仓: {sym} {side} {qty}")
            except Exception:
                logger.exception(f"紧急平仓失败: {sym}")
    logger.warning("紧急平仓完毕")


# ----------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------

if __name__ == "__main__":
    # Windows: 修复 websockets 接收数据超时的已知 bug
    import platform
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
