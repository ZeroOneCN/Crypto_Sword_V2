"""CryptoPilot — Main application entry point.

Wires all modules together and runs the main event loop.
"""

from __future__ import annotations

import asyncio
import signal
import sys

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
        logger.info(f"已启用代理: {proxy_url}")

    # 读取数据源配置
    md_cfg = raw_cfg.get("market_data", {})
    data_source = md_cfg.get("source", "auto")
    poll_interval = md_cfg.get("rest_poll_interval", 3)

    ws_manager = None
    use_rest_poller = False

    if data_source == "rest":
        use_rest_poller = True
    elif data_source == "websocket":
        pass  # use ws_manager
    else:  # auto
        # 尝试 WebSocket, 10s 无数据则降级 REST
        from cryptopilot.market.websocket_manager import BinanceWebSocketManager as BWM
        ws_manager = BinanceWebSocketManager(cfg, data_cache)
        ws_task_test = asyncio.create_task(ws_manager.start(), name="ws_test")

        logger.info("正在检测 WebSocket 连通性 (最多等待 10s)...")
        for _ in range(20):  # 20 × 0.5s = 10s
            await asyncio.sleep(0.5)
            if len(data_cache.all_tickers()) > 10:
                break

        ticker_count = len(data_cache.all_tickers())
        if ticker_count > 10:
            logger.info(f"WebSocket 正常: {ticker_count} 个币种已就绪")
        else:
            logger.warning("WebSocket 无数据, 降级为 REST 轮询")
            use_rest_poller = True
            await ws_manager.stop()
            ws_task_test.cancel()
            try:
                await ws_task_test
            except Exception:
                pass
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

        async def _on_order_update(event: dict):
            """WS 推送的订单状态变更 → 更新本地订单簿."""
            try:
                o = event.get("o", event)
                cid = o.get("c", "")  # clientOrderId
                status = o.get("X", "")
                executed = float(o.get("z", 0))
                if cid:
                    await order_manager.update_order(cid, status, executed)
            except Exception:
                logger.exception("WS 订单更新处理异常")

        async def _on_account_update(event: dict):
            """WS 推送的账户/仓位变动 → 同步持仓."""
            try:
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

    telegram.set_callbacks(
        status_func=get_status_text,
        pause_func=strategy_engine.pause_all,
        resume_func=strategy_engine.resume_all,
        close_all_func=lambda: signal_queue.put(("EMERGENCY_CLOSE_ALL", {})),
    )

    if cfg.notification.telegram_enabled:
        await telegram.start()
        notifier.register(Events.ORDER_FILLED, telegram.on_event)
        notifier.register(Events.POSITION_OPENED, telegram.on_event)
        notifier.register(Events.POSITION_CLOSED, telegram.on_event)
        notifier.register(Events.CIRCUIT_BREAKER_ACTIVATED, telegram.on_event)
        notifier.register(Events.STRATEGY_ERROR, telegram.on_event)

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

            except Exception:
                logger.exception(f"信号处理错误: {item}")
            finally:
                signal_queue.task_done()

    asyncio.create_task(signal_processor())
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

    daily_task = asyncio.create_task(daily_report_loop(), name="daily_report")

    # ---- Start all services ----
    ws_task = asyncio.create_task(ws_manager.start(), name="rest_poller")
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
    if '_user_data_task' in dir():
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
            pass  # May already be set or not supported (spot)

        stop_loss_pct = signal.stop_loss_pct or risk.get("stop_loss_pct", 2.0)
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

    # 下单: WS 优先, REST 兜底
    if getattr(_execute_signal, 'use_ws', False) and _execute_signal.ws_trader:
        try:
            raw = await _execute_signal.ws_trader.place_order(
                symbol=req.symbol, side=req.side, type=req.order_type,
                quantity=req.quantity, price=req.price if req.price > 0 else None,
                stopPrice=req.stop_price if req.stop_price > 0 else None,
                reduceOnly=req.reduce_only, positionSide=req.position_side,
                newClientOrderId=req.client_order_id,
            )
            result = _ws_to_order_result(raw)
        except Exception:
            logger.warning("WS 下单失败, 降级 REST")
            result = await executor.create_order(req)
    else:
        result = await executor.create_order(req)

    await order_manager.record_order(result, signal.strategy_id)

    # Get actual fill price
    fill_price = result.avg_price or result.price or entry_price

    # Notify
    if signal.action.startswith("OPEN"):
        notifier.position_opened(signal.symbol, pos_side, fill_price, qty)

        # ---- Place exchange-native Stop-Loss and Take-Profit ----
        risk = risk_config or {}
        sl_pct = signal.stop_loss_pct or risk.get("stop_loss_pct", 2.0)
        tp_pct = signal.take_profit_pct or risk.get("take_profit_pct", 5.0)

        if signal.stop_loss > 0:
            sl_price = signal.stop_loss
        elif sl_pct > 0 and fill_price > 0:
            if pos_side == "LONG":
                sl_price = fill_price * (1 - sl_pct / 100)
            else:
                sl_price = fill_price * (1 + sl_pct / 100)
        else:
            sl_price = 0

        if signal.take_profit > 0:
            tp_price = signal.take_profit
        elif tp_pct > 0 and fill_price > 0:
            if pos_side == "LONG":
                tp_price = fill_price * (1 + tp_pct / 100)
            else:
                tp_price = fill_price * (1 - tp_pct / 100)
        else:
            tp_price = 0

        if sl_price > 0:
            try:
                # 止损单: 全量 STOP_MARKET
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
                sl_result = await executor.create_order(sl_req)
                await order_manager.record_order(sl_result, signal.strategy_id)

                # 三级分批止盈: TP1(30%) / TP2(30%) / TP3(40%)
                tp_results = await executor.create_three_tier_tp(
                    symbol=signal.symbol,
                    position_side=pos_side,
                    total_qty=qty,
                    entry_price=fill_price,
                    tp1_pct=float(risk.get("tp1_pct", 3.0)),
                    tp2_pct=float(risk.get("tp2_pct", 6.0)),
                    tp3_pct=float(risk.get("tp3_pct", 10.0)),
                )
                for r in tp_results:
                    await order_manager.record_order(r, signal.strategy_id)

                logger.info(
                    f"保护单已提交: SL={sl_price:.4f} + TP1/2/3 共 {len(tp_results)} 个"
                )
            except Exception:
                logger.exception(f"提交 {signal.symbol} 保护单失败")
    else:
        pnl = _calc_pnl(position_manager, signal.symbol, fill_price, qty)
        notifier.position_closed(signal.symbol, pos_side, fill_price, pnl)

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


async def _ws_to_order_result(raw: dict):
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
