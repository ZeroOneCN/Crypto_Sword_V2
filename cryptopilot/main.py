"""CryptoPilot — Main application entry point.

Wires all modules together and runs the main event loop.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from datetime import datetime, timezone

from loguru import logger



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
                    is_sl = event.order_type == "STOP_MARKET"
                    is_tp = cid.startswith("tp")  # TP 单是 LIMIT 类型, 靠 client_order_id 识别
                    if is_sl or is_tp:
                        pnl = float(event.realized_pnl or 0)
                        if is_sl:
                            notifier.sl_triggered(
                                symbol=event.symbol,
                                price=float(event.avg_price or 0),
                                pnl=pnl,
                                pnl_pct=0.0,
                            )
                        elif is_tp:
                            tier = 1
                            if "tp2" in cid:
                                tier = 2
                            elif "tp3" in cid:
                                tier = 3
                            positions = position_manager.get_all_positions()
                            remaining = 0.0
                            for p in positions:
                                if p.get("symbol") == event.symbol:
                                    remaining = abs(float(p.get("qty", 0) or 0))
                                    break
                            notifier.tp_triggered(
                                symbol=event.symbol,
                                tier=tier,
                                price=float(event.avg_price or 0),
                                pnl=pnl,
                                remaining_qty=remaining,
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

    # Sync initial state from exchange
    await position_manager.sync_from_exchange(order_executor)
    await order_manager.sync_with_exchange(order_executor)
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
    scan_task = None
    score_task = None

    # 从 config.yaml 读取评分配置 (支持预设)
    scoring_cfg = raw_cfg.get("scoring", {})

    # 解析预设: active_preset → presets.xxx.factors
    active_preset = scoring_cfg.get("active_preset", "composite")
    presets = scoring_cfg.get("presets", {})
    preset_cfg = presets.get(active_preset, {})
    factor_configs = preset_cfg.get("factors", scoring_cfg.get("factors", []))
    buy_threshold = preset_cfg.get("buy_threshold", scoring_cfg.get("buy_threshold", 50))
    sell_threshold = preset_cfg.get("sell_threshold", scoring_cfg.get("sell_threshold", -50))
    min_confidence = scoring_cfg.get("min_confidence", 0.5)
    special_signals = scoring_cfg.get("special_signals", {})
    special_signals["_preset_name"] = active_preset

    logger.info(f"当前策略预设: {active_preset} (阈值={buy_threshold}/{sell_threshold})")

    if factor_configs:
        scanner_obj, candidate_pool, scoring_engine, scan_task, score_task = (
            await strategy_engine.start_scanning_pipeline(
                cache=data_cache,
                order_executor=order_executor,
                factor_configs=factor_configs,
                notifier=None,
                market_cap_fetcher=mcap_fetcher,
                rest_data=rest_data,
                special_signals=special_signals,
                scan_interval=5.0,
                top_k=3,
                max_signals_per_cycle=1,  # 每轮仅最强信号
                buy_threshold=buy_threshold,
                sell_threshold=sell_threshold,
                min_confidence=min_confidence,
            )
        )
    else:
        logger.warning("未配置评分因子, 扫描链路未启动")

    # ---- Notification ----
    from cryptopilot.notification.notifier import Notifier, Events, EventData
    from cryptopilot.notification.telegram_bot import TelegramBot

    notifier = Notifier()

    telegram = TelegramBot(
        token=env.telegram_bot_token,
        chat_id=env.telegram_chat_id,
        allowed_users=[u.strip() for u in env.telegram_allowed_users.split(",") if u.strip()] if env.telegram_allowed_users else [],
    )

    # Wire Telegram commands to strategy engine
    async def get_status_text() -> str:
        statuses = strategy_engine.get_status()
        lines = [
            f"Strategies ({strategy_engine.active_count}/{strategy_engine.total_count} active):"
        ]
        for s in statuses:
            lines.append(
                f"  {s['strategy_id']} — {s['symbol']} "
                f"{'[PAUSED]' if s['paused'] else '[RUNNING]'} "
                f"{'[POS]' if s['has_position'] else ''}"
            )
        return "\n".join(lines)

    async def get_positions_text() -> str:
        """V2 持仓明细 (用于 Telegram /positions 命令)."""
        positions = position_manager.get_all_positions()
        if not positions:
            return "📭 当前无持仓"
        lines = [f"📊 <b>持仓明细</b> ({len(positions)} 个)\n"]
        for p in positions:
            sym = p.get("symbol", "?")
            side = "📈 LONG" if p.get("side") == "LONG" else "📉 SHORT"
            qty = abs(p.get("qty", 0))
            entry = float(p.get("entry_price", 0) or 0)
            mark = float(p.get("mark_price", 0) or 0)
            pnl = float(p.get("unrealized_pnl", 0) or 0)
            roi = ((mark - entry) / entry * 100) if entry > 0 else 0
            if side == "📉 SHORT":
                roi = -roi
            lines.append(
                f"<b>{sym}</b> {side}  {qty}\n"
                f"  入场: {entry:.5f} | 标记: {mark:.5f}\n"
                f"  浮动: ${pnl:+.2f} ({roi:+.2f}%)"
            )
            # 保护单状态
            orders = order_manager.get_open_orders(sym)
            if orders:
                sls = [o for o in orders if o.get("type") == "STOP_MARKET"]
                tps = [o for o in orders if o.get("type") in ("TAKE_PROFIT_MARKET", "LIMIT")]
                if sls:
                    lines.append(f"  🛑 SL: {sls[0].get('stop_price', '?'):.5f}")
                if tps:
                    tp_str = " ".join([f"TP{o.get('client_order_id','?')[-3:]}:{o.get('price') or o.get('stop_price'):.5f}" for o in tps[:3]])
                    lines.append(f"  🎯 {tp_str}")
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
                        continue

                    # 2. 同币种重复开仓检查
                    existing = position_manager.get_position(signal.symbol)
                    if existing and abs(existing.get("qty", 0)) > 0:
                        logger.info(
                            f"信号跳过 — {signal.symbol} 已有持仓 "
                            f"({existing.get('side', '')} {existing.get('qty', 0)})"
                        )
                        continue

                # Look up strategy-specific risk config
                strat_risk = {}
                for sc in cfg.strategies:
                    sid = f"{sc.name}_{sc.symbol}"
                    if signal.strategy_id.startswith(sid):
                        strat_risk = sc.risk
                        break

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

    profit_locker = ProfitLocker(
        activation_pct=3.0,
        lock_fraction=0.5,
        breakeven_after_pct=2.0,
    )

    async def profit_lock_loop():
        """Periodically check open positions for profit locking opportunities."""
        while True:
            await asyncio.sleep(15)
            try:
                positions = position_manager.get_all_positions()
                for pos in positions:
                    sym = pos.get("symbol", "")
                    if not sym or abs(pos.get("qty", 0)) <= 0:
                        profit_locker.reset(sym)
                        continue

                    entry = pos.get("entry_price", 0)
                    mark = pos.get("mark_price", 0)
                    side = pos.get("side", "LONG")
                    qty = abs(pos.get("qty", 0))

                    if entry <= 0 or mark <= 0 or qty <= 0:
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
                summary = await report_generator.generate_summary()
                positions = position_manager.get_all_positions()
                acct = await order_executor.get_account_info()

                lines = [
                    f"每日报告 — {today}",
                    "",
                    f"总余额: ${acct.total_balance:.2f}",
                    f"可用余额: ${acct.available_balance:.2f}",
                    f"未实现盈亏: ${acct.unrealized_pnl:.2f}",
                    f"当前持仓: {len(positions)} 个",
                    "",
                    f"今日交易: {summary['total_trades']} 笔",
                    f"胜率: {summary['win_rate']}%",
                    f"总盈亏: ${summary['total_pnl']}",
                    f"最大回撤: {summary['max_drawdown_pct']}%",
                    f"夏普比率: {summary['sharpe_ratio']}",
                ]
                msg = "\n".join(lines)
                logger.info(f"每日报告已生成:\n{msg}")
                await telegram.send_message(msg)
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

    # For CLOSE signals: cancel any open SL/TP orders first
    if signal.action.startswith("CLOSE"):
        await executor.cancel_all_orders(signal.symbol)
        logger.info(f"已撤销 {signal.symbol} 的挂单，准备平仓")

    # Check if we already have an open order (skip duplicate entries)
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
            await executor.set_margin_type(signal.symbol, "ISOLATED")
        except Exception:
            logger.debug(f"杠杆/保证金设置跳过 {signal.symbol} (可能已设置或不支持)", exc_info=True)

        stop_loss_pct = signal.stop_loss_pct or risk.get("stop_loss_pct", 5.0)  # 山寨币波动大, 3%太窄
        qty = position_sizer.calculate(
            balance=acct.available_balance,
            entry_price=entry_price,
            stop_loss_pct=stop_loss_pct,
            leverage=default_leverage,
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
        position_side=pos_side,
        reduce_only=signal.action.startswith("CLOSE"),
    )

    # 下单: REST 直连 (WS 连接不稳定, 直接走 REST 更可靠)
    try:
        result = await executor.create_order(req)
    except BaseException:
        logger.exception("REST 下单失败, 信号丢弃")
        return

    await order_manager.record_order(result, signal.strategy_id)

    # 获取实际成交价 — Market 单异步成交, 需轮询确认
    actual_fill_price = result.avg_price if result.avg_price > 0 else 0.0

    # Notify
    if signal.action.startswith("OPEN"):
        # 等待 Market 单成交 (avg_price > 0 表示已成交)
        if actual_fill_price <= 0:
            logger.info(f"等待 {signal.symbol} Market 单成交...")
            for attempt in range(20):  # 最多等 10 秒
                await asyncio.sleep(0.5)
                try:
                    updated = await executor.get_order(
                        signal.symbol, result.client_order_id or ""
                    )
                    if updated and updated.avg_price > 0:
                        actual_fill_price = updated.avg_price
                        result = updated
                        logger.info(f"{signal.symbol} 已成交 @{actual_fill_price:.5f}")
                        break
                except Exception:
                    logger.debug(f"成交确认查询跳过 {signal.symbol} (attempt {attempt+1})", exc_info=True)
            else:
                actual_fill_price = entry_price  # 兜底
                logger.warning(f"{signal.symbol} 成交确认超时, 用信号价兜底")

        # 同步持仓确保仓位存在
        await position_manager.sync_from_exchange(executor)

        # 检查仓位是否真的存在
        pos_check = position_manager.get_position(signal.symbol)
        if not pos_check or abs(pos_check.get("qty", 0)) <= 0:
            logger.error(f"{signal.symbol} 仓位不存在, 无法放置 SL/TP — 撤单")
            await executor.cancel_all_orders(signal.symbol)
            # Try to close if somehow partially filled
            try:
                await executor.create_order(OrderRequest(
                    symbol=signal.symbol,
                    side="SELL" if pos_side == "LONG" else "BUY",
                    order_type="MARKET", quantity=qty,
                    reduce_only=True, position_side=pos_side,
                ))
            except Exception:
                logger.debug("紧急平仓降级尝试失败", exc_info=True)
            return

        fill_price = actual_fill_price if actual_fill_price > 0 else entry_price

        # 🆕 V2 多因子开仓通知
        factor_labels = [f"{name}" for name, direction, s in (signal.top_factors or [])]
        notifier.position_opened(
            symbol=signal.symbol,
            side=pos_side,
            price=fill_price,
            qty=qty,
            leverage=default_leverage,
            score=signal.score,
            top_factors=factor_labels,
            sl_price=0.0,  # 后面填
            tp_tiers=[],   # 后面填
            margin_type="ISOLATED",
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
            if pos_side == "LONG":
                sl_price = fill_price * (1 - sl_pct / 100)
            else:
                sl_price = fill_price * (1 + sl_pct / 100)

            if sl_price > 0:
                try:
                    sl_req = OrderRequest(
                        symbol=signal.symbol,
                        side="SELL" if pos_side == "LONG" else "BUY",
                        order_type="STOP_MARKET",
                        quantity=qty,
                        stop_price=sl_price,
                        reduce_only=True,
                        position_side=pos_side,
                        client_order_id=_make_client_id("sl"),
                    )
                    sl_r = await executor.create_algo_order(sl_req)
                    sl_success = sl_r.order_id > 0
                    logger.info(f"SL 已挂单: {signal.symbol} @{sl_price:.5f} algoId={sl_r.order_id}")
                except Exception as exc:
                    logger.error(f"SL 挂单失败: {signal.symbol} {exc}")
        tp_count = 0
        try:

            # 精确计算 TP 价格
            risk = risk_config or {}
            tp1_pct = float(risk.get("tp1_pct", 3.0))
            tp2_pct = float(risk.get("tp2_pct", 6.0))
            tp3_pct = float(risk.get("tp3_pct", 10.0))
            if pos_side == "LONG":
                tp1 = fill_price * (1 + tp1_pct / 100)
                tp2 = fill_price * (1 + tp2_pct / 100)
                tp3 = fill_price * (1 + tp3_pct / 100)
            else:
                tp1 = fill_price * (1 - tp1_pct / 100)
                tp2 = fill_price * (1 - tp2_pct / 100)
                tp3 = fill_price * (1 - tp3_pct / 100)

            tp_reqs = []
            close_side = "SELL" if pos_side == "LONG" else "BUY"
            for tp_price, tp_qty_ratio, label in [
                (tp1, 0.30, "TP1"), (tp2, 0.30, "TP2"), (tp3, 0.40, "TP3")
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
                        price=tp_price_c, reduce_only=False,
                        position_side=pos_side,
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

            sl_tp_placed = sl_success and tp_count > 0
            logger.info(
                f"保护单: {signal.symbol} SL={sl_price:.5f} "
                f"TP1={tp1:.5f}(30%) TP2={tp2:.5f}(30%) TP3={tp3:.5f}(40%) "
                f"[{tp_count}/3 个TP已放置]"
            )

            # 🆕 V2 保护单通知
            if sl_tp_placed:
                sl_pct_val = abs(sl_price - fill_price) / fill_price * 100
                tp_placed = []
                tp_defs = [(tp1, tp1_pct, 0.30, 1), (tp2, tp2_pct, 0.30, 2), (tp3, tp3_pct, 0.40, 3)]
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
            elif sl_price <= 0:
                logger.warning(f"{signal.symbol} 止损价无效, SL={sl_price}")
            else:
                logger.warning(f"{signal.symbol} TP 未放置 (SL=本地跟踪)")
        except Exception:
            logger.exception(f"{signal.symbol} TP 提交异常")
    else:
        close_fill_price = result.avg_price if result.avg_price > 0 else 0.0
        pnl = _calc_pnl(position_manager, signal.symbol, close_fill_price, qty)

        # 🆕 V2 平仓通知 — 带持仓时长和退出原因
        pos = position_manager.get_position(signal.symbol)
        entry_px = pos.get("entry_price", 0) if pos else 0
        pnl_pct = ((close_fill_price - entry_px) / entry_px * 100) if entry_px > 0 else 0
        if pos_side == "SHORT":
            pnl_pct = -pnl_pct

        # 计算持仓时长
        open_times = getattr(_execute_signal, '_position_open_time', {})
        open_ts = open_times.pop(signal.symbol, None)
        hold_dur = ""
        if open_ts:
            dur_sec = time.time() - open_ts
            m, s = divmod(int(dur_sec), 60)
            if m < 60:
                hold_dur = f"{m}m{s}s"
            else:
                h, m = divmod(m, 60)
                hold_dur = f"{h}h{m:02d}m"

        # 推断退出原因
        exit_reason = "SIGNAL"  # 默认
        if signal.action in ("CLOSE_LONG", "CLOSE_SHORT"):
            exit_reason = "MANUAL" if "manual" in (signal.comment or "").lower() else "SIGNAL"

        notifier.position_closed(
            symbol=signal.symbol,
            side=pos_side,
            exit_price=close_fill_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            hold_duration=hold_dur,
        )

    logger.info(f"订单已执行: {result.status} {side} {qty} {signal.symbol} [id={result.order_id}]")

    # Sync positions
    await position_manager.sync_from_exchange(executor)


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
