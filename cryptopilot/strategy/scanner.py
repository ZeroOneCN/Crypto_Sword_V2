"""实时扫描器 — 遍历全币种 ticker，初筛后写入候选池."""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass, field

from loguru import logger


@dataclass(order=True)
class Candidate:
    """初筛候选币种，按 scanner_score 降序排列."""
    sort_key: float = field(init=False, compare=True)
    symbol: str = field(compare=False)
    current_price: float = field(compare=False, default=0.0)
    change_24h_pct: float = field(compare=False, default=0.0)
    volume_ratio: float = field(compare=False, default=1.0)
    oi_change_pct: float = field(compare=False, default=0.0)
    funding_rate: float = field(compare=False, default=0.0)
    mark_price: float = field(compare=False, default=0.0)
    scanner_score: float = field(compare=False, default=0.0)
    direction: str = field(compare=False, default="HOLD")
    confidence: float = field(compare=False, default=0.0)
    composite_score: float = field(compare=False, default=0.0)
    scrape_reasons: list[str] = field(compare=False, default_factory=list)
    scraped_at: float = field(compare=False, default_factory=time.time)

    def __post_init__(self) -> None:
        self.sort_key = -self.scanner_score  # 负号使 PriorityQueue 降序


class MarketScanner:
    """全币种遍历初筛器.

    每 `scan_interval` 秒遍历所有 ticker,
    通过涨跌幅、量比、OI变化、布林带偏离四条件打分,
    满足阈值的写入候选池.
    """

    def __init__(
        self,
        cache,  # MarketDataCache
        candidate_pool,  # CandidatePool
        scan_interval: float = 300.0,  # 默认对齐V1深度扫描间隔
        min_change_pct: float = 1.5,
        volume_mult: float = 1.5,
        oi_change_threshold: float = 3.0,
        min_score: float = 40.0,
        max_symbols_to_scan: int = 100,
        rest_data=None,  # RestDataFetcher (注入以预取K线/OI)
    ) -> None:
        self._cache = cache
        self._pool = candidate_pool
        self._interval = scan_interval
        self._min_change = min_change_pct
        self._vol_mult = volume_mult
        self._oi_threshold = oi_change_threshold
        self._min_score = min_score
        self._max_scan = max_symbols_to_scan
        self._rest_data = rest_data
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info(
            f"扫描器已启动 (间隔={self._interval}s, 最低分={self._min_score}, "
            f"最大扫描数={self._max_scan})"
        )
        # 等待行情数据就绪 (WebSocket 可能尚未连接)
        for wait_i in range(30):
            if len(self._cache.all_tickers()) > 10:
                logger.info(f"行情数据就绪: {len(self._cache.all_tickers())} 币种, 开始扫描")
                break
            await asyncio.sleep(2)
        else:
            logger.warning("等待行情数据超时 (60s), 继续启动")
        heartbeat = 0
        while self._running:
            try:
                await self._scan_round()
            except Exception:
                logger.exception("扫描轮次异常")
            heartbeat += 1
            if heartbeat % 10 == 0:
                ticker_count = len(self._cache.all_tickers())
                pool_count = self._pool.size
                logger.info(f"扫描心跳: 行情={ticker_count}币种, 候选池={pool_count}个")
            await asyncio.sleep(self._interval)

    async def stop(self) -> None:
        self._running = False

    async def _scan_round(self) -> None:
        tickers = self._cache.all_tickers()
        scanned = 0
        passed = 0

        for ticker in tickers:
            if scanned >= self._max_scan:
                break
            scanned += 1

            sym = ticker.symbol
            price = ticker.price
            if price <= 0:
                continue

            # ---- REST 预取 K线 + OI (注入 MarketDataCache 供因子使用) ----
            if self._rest_data:
                try:
                    klines = await self._rest_data.fetch_klines(sym, "1m", limit=30)
                    from cryptopilot.market.types import StreamMessage
                    for k in klines:
                        await self._cache.update(StreamMessage(stream="rest", data=k))
                    oi = await self._rest_data.calc_oi_change_pct(sym, 60)
                    if oi != 0:
                        self._cache._oi_cache[sym] = oi  # 临时注入
                except Exception:
                    pass

            change = abs(ticker.price_change_pct)
            vol_ratio = 1.0
            avg_vol = ticker.volume_24h / 1440.0  # 24h 均量(每分钟)
            if avg_vol > 0:
                # 最近一根 1m kline 的成交量 / 分钟均量
                kline_1m = self._cache.get_kline(sym, "1m")
                recent_vol = kline_1m.volume if kline_1m else 0
                vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

            oi_change = self._cache.get_oi_change_pct(sym, 3600.0)
            funding = self._cache.get_funding_rate(sym)
            mark = self._cache.get_mark_price(sym)

            # BBand proximity
            bband_score = self._bollinger_proximity_score(sym, price)

            # 综合初筛评分 (0-100)
            scores = []
            reasons = []

            # 涨跌幅因子 (max 30)
            change_score = min(abs(ticker.price_change_pct) / self._min_change * 30, 30)
            if change_score > 10:
                scores.append(change_score)
                reasons.append(f"涨跌{change:.1f}%")

            # 量比因子 (max 25)
            vol_score = min(vol_ratio / self._vol_mult * 25, 25)
            if vol_score > 10:
                scores.append(vol_score)
                reasons.append(f"量比{vol_ratio:.1f}x")

            # OI 变化因子 (max 20)
            oi_abs = abs(oi_change)
            oi_score = min(oi_abs / self._oi_threshold * 20, 20)
            if oi_score > 5:
                scores.append(oi_score)
                reasons.append(f"OI变化{oi_change:+.1f}%")

            # 布林带临近因子 (max 25)
            if bband_score > 10:
                scores.append(bband_score)
                reasons.append(f"布林带{bband_score:.0f}分")

            total = sum(scores)
            if total < self._min_score:
                continue

            candidate = Candidate(
                symbol=sym,
                current_price=price,
                change_24h_pct=ticker.price_change_pct,
                volume_ratio=vol_ratio,
                oi_change_pct=oi_change,
                funding_rate=funding,
                mark_price=mark.mark_price if mark else 0,
                scanner_score=total,
                scrape_reasons=reasons,
            )
            await self._pool.push(candidate)
            passed += 1

        if passed > 0:
            logger.debug(f"扫描: {scanned} 个 → {passed} 个候选入选")

    def _bollinger_proximity_score(self, symbol: str, price: float) -> float:
        """价格距布林带边界的接近程度 (0-25)."""
        klines = self._cache.get_klines(symbol, "1m", limit=30)
        if len(klines) < 20:
            return 0.0
        closes = [k.close for k in klines]
        mean = sum(closes) / len(closes)
        variance = sum((c - mean) ** 2 for c in closes) / len(closes)
        std = math.sqrt(variance)
        upper = mean + 2.0 * std
        lower = mean - 2.0 * std
        bw = upper - lower
        if bw <= 0:
            return 0.0
        # 距上轨距离 (归一化)
        dist_upper = (upper - price) / bw
        dist_lower = (price - lower) / bw
        # 越靠近边界得分越高
        proximity = 1.0 - min(dist_upper, dist_lower) * 2.0
        return max(0.0, min(proximity, 1.0)) * 25.0
