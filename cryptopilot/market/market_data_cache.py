"""Thread-safe async cache for latest market data with O(1) lookups."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Callable, Awaitable

from cryptopilot.market.types import (
    KlineData,
    TickerData,
    DepthData,
    MarkPriceData,
    OpenInterestData,
    LiquidationData,
    StreamMessage,
)

MAX_KLINES = 500
MAX_LIQUIDATIONS = 200

Callback = Callable[[StreamMessage], Awaitable[None]]


class MarketDataCache:
    """In-memory cache for all market data types per symbol."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

        # symbol -> TickerData
        self._tickers: dict[str, TickerData] = {}
        self._ticker_logged = False  # 首次收到行情记日志

        # symbol -> interval -> KlineData (latest)
        self._klines: dict[str, dict[str, KlineData]] = {}

        # symbol -> interval -> deque[KlineData] (history, max 500)
        self._kline_history: dict[str, dict[str, deque[KlineData]]] = {}

        # symbol -> DepthData
        self._depth: dict[str, DepthData] = {}

        # ---- 新增 ----
        # symbol -> MarkPriceData
        self._mark_prices: dict[str, MarkPriceData] = {}

        # symbol -> OpenInterestData
        self._open_interest: dict[str, OpenInterestData] = {}

        # symbol -> deque[(timestamp, oi_value)]  OI 历史, 用于计算变化率
        self._oi_history: dict[str, deque[tuple[float, float]]] = {}

        # symbol -> dict{ side -> count }  强平统计 (最近 N 条汇总)
        self._liquidation_counts: dict[str, dict[str, int]] = {}

        # global -> deque[LiquidationData]  最近 200 条强平记录
        self._liquidations: deque[LiquidationData] = deque(maxlen=MAX_LIQUIDATIONS)

        # list of async callbacks
        self._listeners: list[Callback] = []

    async def update(self, msg: StreamMessage) -> None:
        """Store incoming data and notify listeners."""
        async with self._lock:
            data = msg.data
            if isinstance(data, TickerData):
                self._tickers[data.symbol] = data
                if not self._ticker_logged and len(self._tickers) > 10:
                    self._ticker_logged = True
                    from loguru import logger
                    logger.info(f"行情数据已就绪: {len(self._tickers)} 个币种")
            elif isinstance(data, KlineData):
                sym = data.symbol
                interval = data.interval
                self._klines.setdefault(sym, {})[interval] = data
                hist = self._kline_history.setdefault(sym, {}).setdefault(
                    interval, deque(maxlen=MAX_KLINES)
                )
                if hist and hist[-1].open_time == data.open_time:
                    hist[-1] = data
                else:
                    hist.append(data)
            elif isinstance(data, DepthData):
                self._depth[data.symbol] = data
            elif isinstance(data, MarkPriceData):
                self._mark_prices[data.symbol] = data
            elif isinstance(data, OpenInterestData):
                self._open_interest[data.symbol] = data
                sym = data.symbol
                hist = self._oi_history.setdefault(
                    sym, deque(maxlen=120)
                )
                hist.append((time.time(), data.open_interest))
            elif isinstance(data, LiquidationData):
                self._liquidations.append(data)
                sym = data.symbol
                cnt = self._liquidation_counts.setdefault(sym, {"BUY": 0, "SELL": 0})
                cnt[data.side] = cnt.get(data.side, 0) + 1

        for cb in self._listeners[:]:
            try:
                await cb(msg)
            except Exception:
                pass

    def subscribe(self, callback: Callback) -> None:
        self._listeners.append(callback)

    def unsubscribe(self, callback: Callback) -> None:
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    # ---- Synchronous read access ----

    def get_ticker(self, symbol: str) -> TickerData | None:
        return self._tickers.get(symbol)

    def get_kline(self, symbol: str, interval: str) -> KlineData | None:
        return self._klines.get(symbol, {}).get(interval)

    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[KlineData]:
        hist = self._kline_history.get(symbol, {}).get(interval)
        if hist is None:
            return []
        items = list(hist)
        return items[-limit:] if limit else items

    def get_depth(self, symbol: str) -> DepthData | None:
        return self._depth.get(symbol)

    # ---- 新增 getters ----

    def get_mark_price(self, symbol: str) -> MarkPriceData | None:
        return self._mark_prices.get(symbol)

    def get_funding_rate(self, symbol: str) -> float:
        mp = self._mark_prices.get(symbol)
        return mp.funding_rate if mp else 0.0

    def get_open_interest(self, symbol: str) -> OpenInterestData | None:
        return self._open_interest.get(symbol)

    def get_oi_change_pct(self, symbol: str, lookback_seconds: float = 3600.0) -> float:
        """计算 OI 在指定时间窗口内的变化率 (%)。"""
        hist = self._oi_history.get(symbol)
        if not hist or len(hist) < 2:
            return 0.0
        now = time.time()
        cutoff = now - lookback_seconds
        oldest = None
        for ts, oi in hist:
            if ts >= cutoff:
                if oldest is None:
                    oldest = oi
                break
        else:
            oldest = hist[0][1]
        if oldest is None or oldest == 0:
            return 0.0
        latest = hist[-1][1]
        return (latest - oldest) / oldest * 100

    def get_liquidation_count(self, symbol: str) -> dict[str, int]:
        """返回 {BUY: N, SELL: N} 强平统计。"""
        return self._liquidation_counts.get(symbol, {"BUY": 0, "SELL": 0})

    def get_recent_liquidations(self, limit: int = 50) -> list[LiquidationData]:
        items = list(self._liquidations)
        return items[-limit:]

    def get_liquidation_ratio(self, symbol: str) -> float:
        """多空强平比。>1 表示多方被强平更多, <1 表示空方更多。"""
        cnt = self._liquidation_counts.get(symbol, {})
        buy = cnt.get("BUY", 0)
        sell = cnt.get("SELL", 0)
        if buy + sell == 0:
            return 1.0
        if sell == 0:
            return 2.0
        return buy / sell

    @property
    def all_symbols(self) -> list[str]:
        symbols = set(self._tickers.keys())
        symbols.update(self._klines.keys())
        symbols.update(self._depth.keys())
        symbols.update(self._mark_prices.keys())
        symbols.update(self._open_interest.keys())
        return sorted(symbols)

    def tickers(self) -> dict[str, TickerData]:
        return dict(self._tickers)

    def all_tickers(self) -> list[TickerData]:
        return list(self._tickers.values())

    def mark_prices(self) -> dict[str, MarkPriceData]:
        return dict(self._mark_prices)
