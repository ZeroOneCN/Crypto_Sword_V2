"""StrategyEngine — registers, dispatches, and manages strategy lifecycle."""

from __future__ import annotations

import asyncio
from loguru import logger

from cryptopilot.market.types import KlineData, TickerData
from cryptopilot.strategy.base import StrategyBase, Signal


class StrategyEngine:
    """Manages all strategy instances. Dispatches market data to matching strategies.

    Supports:
    - Register/unregister strategies
    - Dispatch ticker/klines to matching strategies (by symbol)
    - Isolated crash handling (one strategy failure doesn't affect others)
    - Pause/resume/stop per strategy
    """

    def __init__(
        self,
        signal_queue: asyncio.Queue,
        cache,  # MarketDataCache
        position_manager,
        order_manager,
    ) -> None:
        self._signal_queue = signal_queue
        self._cache = cache
        self._position_manager = position_manager
        self._order_manager = order_manager

        self._strategies: dict[str, StrategyBase] = {}
        self._by_symbol: dict[str, list[str]] = {}
        self._paused: set[str] = set()

    # ----------------------------------------------------------------
    # Registration
    # ----------------------------------------------------------------

    async def register(self, strategy: StrategyBase) -> str:
        """Register a strategy, call on_init, return its ID."""
        sid = strategy.strategy_id
        self._strategies[sid] = strategy
        self._by_symbol.setdefault(strategy.symbol, []).append(sid)

        try:
            await strategy.on_init()
            logger.info(f"策略 '{sid}' 已注册并初始化（交易对={strategy.symbol}）")
        except Exception:
            logger.exception(f"策略 '{sid}' 初始化失败，正在移除")
            self._strategies.pop(sid, None)
            raise

        return sid

    async def unregister(self, strategy_id: str) -> None:
        """Stop and remove a strategy."""
        strat = self._strategies.pop(strategy_id, None)
        if strat is None:
            return
        sym = strat.symbol
        try:
            await strat.on_stop()
        except Exception:
            logger.exception(f"策略 '{strategy_id}' 停止时出错")

        self._by_symbol.get(sym, []).remove(strategy_id)
        self._paused.discard(strategy_id)
        logger.info(f"策略 '{strategy_id}' 已注销")

    # ----------------------------------------------------------------
    # Dispatch
    # ----------------------------------------------------------------

    async def dispatch_tick(self, ticker: TickerData) -> None:
        """Route a ticker update to all strategies subscribed to its symbol."""
        sids = self._by_symbol.get(ticker.symbol, [])
        if not sids:
            return

        for sid in sids:
            if sid in self._paused:
                continue
            strat = self._strategies.get(sid)
            if strat is None or not strat.enabled:
                continue
            try:
                await strat.on_tick(ticker)
                signal = await strat.on_signal()
                if signal is not None:
                    await strat.emit_signal(signal)
            except Exception:
                logger.exception(f"策略 '{sid}' 在行情更新或信号处理中出错")

    async def dispatch_kline(self, kline: KlineData) -> None:
        """Route a kline update to all strategies subscribed to its symbol."""
        sids = self._by_symbol.get(kline.symbol, [])
        if not sids:
            return

        for sid in sids:
            if sid in self._paused:
                continue
            strat = self._strategies.get(sid)
            if strat is None or not strat.enabled:
                continue
            try:
                await strat.on_kline(kline)
                signal = await strat.on_signal()
                if signal is not None:
                    await strat.emit_signal(signal)
            except Exception:
                logger.exception(f"策略 '{sid}' 在K线更新或信号处理中出错")

    # ----------------------------------------------------------------
    # Control
    # ----------------------------------------------------------------

    async def pause(self, strategy_id: str) -> None:
        if strategy_id in self._strategies:
            self._strategies[strategy_id].paused = True
            self._paused.add(strategy_id)

    async def resume(self, strategy_id: str) -> None:
        if strategy_id in self._strategies:
            self._strategies[strategy_id].paused = False
            self._paused.discard(strategy_id)

    async def pause_all(self) -> None:
        for sid in self._strategies:
            self._strategies[sid].paused = True
            self._paused.add(sid)
        logger.info("所有策略已暂停")

    async def resume_all(self) -> None:
        for sid in list(self._paused):
            self._strategies[sid].paused = False
        self._paused.clear()
        logger.info("所有策略已恢复")

    async def stop_all(self) -> None:
        for sid in list(self._strategies.keys()):
            await self.unregister(sid)
        logger.info("所有策略已停止")

    # ----------------------------------------------------------------
    # Scanning Pipeline (Scanner → CandidatePool → Scoring)
    # ----------------------------------------------------------------

    async def start_scanning_pipeline(
        self,
        cache,       # MarketDataCache
        order_executor,
        factor_configs: list[dict] | None = None,
        notifier=None,
        market_cap_fetcher=None,
        rest_data=None,       # RestDataFetcher
        special_signals: dict | None = None,
        scan_interval: float = 5.0,
        top_k: int = 3,
        max_signals_per_cycle: int = 1,
        buy_threshold: float = 50.0,
        sell_threshold: float = -50.0,
        min_confidence: float = 0.5,
    ) -> tuple:
        """启动扫描→候选→多因子评分→信号全链路.

        factor_configs: 从 config.yaml scoring 传入的因子配置列表.
        market_cap_fetcher: 市值抓取器 (注入 market_cap 因子).
        special_signals: 特殊信号开关配置.
        返回 (scanner, pool, scoring, scan_task, score_task)
        """
        from cryptopilot.strategy.scanner import MarketScanner, Candidate
        from cryptopilot.strategy.candidate import CandidatePool
        from cryptopilot.strategy.scoring import ScoringEngine
        from cryptopilot.strategy.base import Signal as BaseSignal
        from cryptopilot.market.types import StreamMessage

        pool = CandidatePool(max_size=20, ttl_seconds=scan_interval * 2)
        scoring = ScoringEngine(
            cache=cache,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            min_confidence=min_confidence,
        )

        # 加载因子配置
        if factor_configs:
            scoring.configure(factor_configs)

        # 注入 market_cap_fetcher 到 market_cap 因子
        if market_cap_fetcher:
            for factor in scoring._factors:
                if factor.name == "market_cap" and hasattr(factor, "set_fetcher"):
                    factor.set_fetcher(market_cap_fetcher)

        logger.info(f"评分引擎已加载 {scoring.factor_count} 个因子: {scoring.factor_names()}")

        scanner = MarketScanner(
            cache=cache,
            candidate_pool=pool,
            scan_interval=scan_interval,
            min_change_pct=1.5,
            volume_mult=1.8,
            oi_change_threshold=3.0,
            min_score=25.0,
            max_symbols_to_scan=50,  # 对齐V1的Top-30扫描范围,减少REST调用
            rest_data=rest_data,
        )

        sig_cfg = special_signals or {}
        _signal_tracker: dict[str, set[str]] = {}
        _prev_funding: dict[str, float] = {}

        async def scoring_loop():
            """评分循环: 30s 取候选 → 评分 → 最强1信号."""
            score_heartbeat = 0
            while True:
                await asyncio.sleep(30)  # 高频轮询, 避免相位死锁
                score_heartbeat += 1
                try:
                    top = await pool.pop_top(top_k)
                    if score_heartbeat % 12 == 0:
                        logger.info(f"评分心跳: 候选池={pool.size}个, 本轮评分={len(top)}个")

                    best_signal = None
                    best_score = 0.0
                    signals_produced = 0

                    # 每 30s 输出一次候选评分明细 (方便调试)
                    if score_heartbeat % 6 == 0 and top:
                        for cand in top[:1]:
                            try:
                                if rest_data:
                                    klines = await rest_data.fetch_klines(cand.symbol, "1m", limit=10)
                                    for k in klines:
                                        await cache.update(StreamMessage(stream="rest", data=k))
                                r = scoring.score(cand)
                                active_factors = [f"{fs.name}({fs.direction},{fs.score:.0f})" for fs in r.factors if fs.direction != "NEUTRAL"]
                                logger.info(f"评分诊断 [{r.symbol}]: score={r.total_score:.1f}/{buy_threshold} 活跃因子={active_factors}")
                            except Exception:
                                pass

                    for cand in top:
                        # 跳过已有持仓的币种 (避免重复开仓)
                        if self._position_manager.get_position(cand.symbol):
                            continue

                        # REST 按需拉取: 先检查 WS 缓存是否已有数据，避免重复请求
                        # 1m K线优先从缓存取 (WS 实时推送已覆盖)
                        need_klines_rest = False
                        if cache.get_klines(cand.symbol, "1m", limit=50):
                            # WS 已推送足够数据，跳过 REST
                            pass
                        else:
                            need_klines_rest = True

                        if rest_data:
                            try:
                                if need_klines_rest:
                                    klines = await rest_data.fetch_klines(cand.symbol, "1m", limit=50)
                                    klines_5m = await rest_data.fetch_klines(cand.symbol, "5m", limit=50)
                                    for k in klines:
                                        await cache.update(StreamMessage(stream="rest", data=k))
                                    for k in klines_5m:
                                        k.interval = "5m"
                                        await cache.update(StreamMessage(stream="rest", data=k))

                                # 4h K线: 仅在缓存缺失时拉取 (量大，200根)
                                if not cache.get_klines(cand.symbol, "4h", limit=200):
                                    klines_4h = await rest_data.fetch_klines(cand.symbol, "4h", limit=200)
                                    for k in klines_4h:
                                        k.interval = "4h"
                                        await cache.update(StreamMessage(stream="rest", data=k))

                                oi_change = await rest_data.calc_oi_change_pct(cand.symbol, 60)
                                mp = await rest_data.fetch_mark_price(cand.symbol)
                                if mp:
                                    await cache.update(StreamMessage(stream="rest", data=mp))
                                if oi_change != 0:
                                    cand.oi_change_pct = oi_change
                                if mp:
                                    cand.funding_rate = mp.funding_rate
                                    cand.mark_price = mp.mark_price
                            except Exception:
                                logger.debug(f"REST 预取失败 {cand.symbol}")

                        result = scoring.score(cand)
                        sym = cand.symbol

                        # ---- 特殊信号检测 ----
                        dark_flow = False
                        funding_deterioration = False

                        # ⚡ 暗流涌动: OI涨 + 价不动
                        if sig_cfg.get("dark_flow") and abs(cand.change_24h_pct) < 1.0 and cand.oi_change_pct > 3.0:
                            dark_flow = True
                            msg = f"⚡暗流涌动: {sym} OI+{cand.oi_change_pct:.1f}% 价{cand.change_24h_pct:+.1f}% → 最佳埋伏时机"
                            logger.warning(msg)
                            if notifier:
                                from cryptopilot.notification.notifier import EventData, Events
                                notifier.notify(EventData(event=Events.WARNING, message=msg, symbol=sym))

                        # 🔥 费率加速恶化: 当前费率比上次更负
                        if sig_cfg.get("funding_deterioration"):
                            prev = _prev_funding.get(sym)
                            if prev is not None and cand.funding_rate < prev and cand.funding_rate < 0:
                                funding_deterioration = True
                                msg = f"🔥费率恶化: {sym} {prev*100:.4f}% → {cand.funding_rate*100:.4f}% → 轧空燃料堆积"
                                logger.warning(msg)
                                if notifier:
                                    from cryptopilot.notification.notifier import EventData, Events
                                    notifier.notify(EventData(event=Events.WARNING, message=msg, symbol=sym))
                        _prev_funding[sym] = cand.funding_rate

                        # ⭐ 双榜追踪: 同一币种在多个策略中上榜
                        if sig_cfg.get("double_rank"):
                            tracker = _signal_tracker.setdefault(sym, set())
                            tracker.add("scanner")
                            if len(tracker) >= 2:
                                msg = f"⭐双榜共振: {sym} 同时被 {', '.join(tracker)} 策略选中"
                                logger.warning(msg)
                                if notifier:
                                    from cryptopilot.notification.notifier import EventData, Events
                                    notifier.notify(EventData(event=Events.WARNING, message=msg, symbol=sym))

                        # 📦 收筹告警: 横盘>90天 + OI异动
                        if sig_cfg.get("accumulation_alert"):
                            from cryptopilot.strategy.detectors.sideways_detector import SidewaysDetector
                            sd = SidewaysDetector()
                            sr = sd.detect(sym, cache)
                            if sr.sideways_days >= 90 and abs(cand.oi_change_pct) > 3.0:
                                msg = f"📦收筹告警: {sym} 横盘{sr.sideways_days}天 + OI{cand.oi_change_pct:+.1f}% → 可能即将拉盘"
                                logger.warning(msg)
                                if notifier:
                                    from cryptopilot.notification.notifier import EventData, Events
                                    notifier.notify(EventData(event=Events.WARNING, message=msg, symbol=sym))

                        # 正常信号产出
                        if result.direction == "HOLD":
                            # 记录接近阈值的候选 (方便调试)
                            if abs(result.total_score) > buy_threshold * 0.6 and score_heartbeat % 3 == 0:
                                logger.info(f"评分接近阈值: {sym} score={result.total_score:.1f} (阈值={buy_threshold}) 因子投票: {[(fs.name, fs.direction, fs.score) for fs in result.factors[:5]]}")
                            continue
                        if result.confidence < min_confidence:
                            continue

                        # 暗流信号增强
                        abs_score = abs(result.total_score)
                        if dark_flow:
                            abs_score *= 1.2  # 暗流加成

                        # 追踪最强信号
                        if abs_score > best_score:
                            best_score = abs_score
                            # 提取前3贡献因子
                            top3 = sorted(
                                result.factors, key=lambda f: abs(f.score), reverse=True
                            )[:3]
                            best_signal = BaseSignal(
                                strategy_id=f"scanner_{result.symbol}",
                                symbol=result.symbol,
                                action=f"OPEN_{result.direction}",
                                order_type="MARKET",
                                price=cand.current_price,
                                stop_loss_pct=5.0,
                                take_profit_pct=6.0,
                                comment=result.detail,
                                score=result.total_score,
                                top_factors=[(f.name, f.direction, f.score) for f in top3],
                                preset=special_signals.get("_preset_name", "composite"),
                            )

                    # 每轮仅执行最强信号
                    if best_signal is not None and signals_produced < max_signals_per_cycle:
                        await self._signal_queue.put(best_signal)
                        signals_produced += 1
                        msg = f"雷达信号: {best_signal.comment}"
                        logger.info(msg)
                        if notifier:
                            from cryptopilot.notification.notifier import EventData, Events
                            notifier.notify(EventData(
                                event=Events.WARNING, message=msg, symbol=best_signal.symbol))

                        # 记录信号日志 (供 Web 展示)
                        try:
                            from cryptopilot.web.health import add_signal_log
                            from cryptopilot.strategy.scoring import FACTOR_CN
                            top_names = [f.name for f in top3] if top3 else []
                            factor_labels_cn = [FACTOR_CN.get(n, n) for n in top_names]
                            add_signal_log({
                                "time": __import__("datetime").datetime.now(
                                    __import__("datetime").timezone.utc).isoformat(),
                                "symbol": best_signal.symbol,
                                "action": best_signal.action,
                                "score": round(best_score, 1),
                                "detail": best_signal.comment,
                                "factor_labels_cn": factor_labels_cn,
                            })
                        except Exception:
                            pass

                except Exception:
                    logger.exception("评分循环异常")

        scan_task = asyncio.create_task(scanner.start(), name="market_scanner")
        score_task = asyncio.create_task(scoring_loop(), name="scoring_loop")
        strategy_type = special_signals.get("_preset_name", "custom") if special_signals else "custom"
        logger.info(
            f"统一扫描已启动: 间隔={scan_interval}s, TopK={top_k}, "
            f"每轮最多{max_signals_per_cycle}仓, 策略={strategy_type}"
        )

        return scanner, pool, scoring, scan_task, score_task

    # ----------------------------------------------------------------
    # Status
    # ----------------------------------------------------------------

    def get_status(self, strategy_id: str | None = None) -> list[dict]:
        """Return status info for all strategies (or one)."""
        sids = [strategy_id] if strategy_id else list(self._strategies.keys())
        result = []
        for sid in sids:
            s = self._strategies.get(sid)
            if s:
                result.append({
                    "strategy_id": sid,
                    "symbol": s.symbol,
                    "enabled": s.enabled,
                    "paused": s.paused,
                    "has_position": s.has_position(),
                    "has_open_order": s.has_open_order(),
                })
        return result

    @property
    def active_count(self) -> int:
        return len([s for s in self._strategies.values() if s.enabled and not s.paused])

    @property
    def total_count(self) -> int:
        return len(self._strategies)
