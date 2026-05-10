"""REST API 按需数据拉取 — 评分时动态获取 K线/OI/标记价.

避免为全市场所有币种订阅 per-symbol WS 流,
只在候选进入评分时, 通过 REST API 按需拉取深度数据.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

import httpx
from loguru import logger

from cryptopilot.market.types import KlineData, MarkPriceData, OpenInterestData

FUTURES_REST = "https://fapi.binance.com"
CACHE_TTL_SHORT = 30     # 30秒 — 评分数据缓存
CACHE_TTL_LONG = 300     # 5分钟 — 历史数据缓存
MAX_KLINES_CACHE = 200


class RestDataFetcher:
    """通过 Binance REST API 按需拉取 K 线 / OI / 标记价.

    内置 TTL 缓存避免重复请求.
    """

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy
        self._klines_cache: dict[str, tuple[float, list[KlineData]]] = {}
        self._oi_cache: dict[str, tuple[float, list[dict]]] = {}
        self._mark_price_cache: dict[str, tuple[float, MarkPriceData]] = {}
        self._lock = asyncio.Lock()

    def _client_kwargs(self) -> dict:
        kw = {"base_url": FUTURES_REST, "timeout": 15.0}
        if self._proxy:
            kw["proxy"] = self._proxy
        return kw

    # ---- K 线 ----

    async def fetch_klines(
        self, symbol: str, interval: str = "5m", limit: int = 50
    ) -> list[KlineData]:
        """拉取 K 线历史."""
        cache_key = f"{symbol}_{interval}_{limit}"
        now = time.time()
        cached = self._klines_cache.get(cache_key)
        if cached and (now - cached[0]) < CACHE_TTL_SHORT:
            return cached[1]

        try:
            async with httpx.AsyncClient(**self._client_kwargs()) as client:
                resp = await client.get("/fapi/v1/klines", params={
                    "symbol": symbol, "interval": interval, "limit": limit,
                })
                raw = resp.json()
        except Exception as exc:
            logger.warning(f"K线拉取失败 {symbol}: {exc}")
            return cached[1] if cached else []

        if not isinstance(raw, list):
            return cached[1] if cached else []

        klines = []
        for k in raw:
            try:
                klines.append(KlineData(
                    symbol=symbol, interval=interval,
                    open_time=k[0], close_time=k[6],
                    open=float(k[1]), high=float(k[2]),
                    low=float(k[3]), close=float(k[4]),
                    volume=float(k[5]), quote_volume=float(k[7]),
                    taker_buy_volume=float(k[9]),
                    taker_buy_quote_volume=float(k[10]),
                    is_final=True,
                ))
            except (IndexError, ValueError):
                continue

        self._klines_cache[cache_key] = (now, klines)
        return klines

    # ---- OI 历史 ----

    async def fetch_open_interest_hist(
        self, symbol: str, period: str = "5m", limit: int = 30
    ) -> list[dict]:
        """拉取 OI 历史变化."""
        cache_key = f"oi_{symbol}_{period}_{limit}"
        now = time.time()
        cached = self._oi_cache.get(cache_key)
        if cached and (now - cached[0]) < CACHE_TTL_LONG:
            return cached[1]

        try:
            async with httpx.AsyncClient(**self._client_kwargs()) as client:
                resp = await client.get("/futures/data/openInterestHist", params={
                    "symbol": symbol, "period": period, "limit": limit,
                })
                raw = resp.json()
        except Exception as exc:
            logger.debug(f"OI历史拉取失败 {symbol}: {exc}")
            return cached[1] if cached else []

        if not isinstance(raw, list):
            return cached[1] if cached else []

        result = []
        for item in raw:
            try:
                result.append({
                    "symbol": item["symbol"],
                    "open_interest": float(item["sumOpenInterest"]),
                    "timestamp": item["timestamp"],
                })
            except (KeyError, ValueError):
                continue

        self._oi_cache[cache_key] = (now, result)
        return result

    # ---- 标记价 + 资金费率 ----

    async def fetch_mark_price(self, symbol: str) -> MarkPriceData | None:
        """拉取当前标记价和资金费率."""
        cache_key = f"mp_{symbol}"
        now = time.time()
        cached = self._mark_price_cache.get(cache_key)
        if cached and (now - cached[0]) < CACHE_TTL_SHORT:
            return cached[1]

        try:
            async with httpx.AsyncClient(**self._client_kwargs()) as client:
                resp = await client.get("/fapi/v1/premiumIndex", params={
                    "symbol": symbol,
                })
                raw = resp.json()
        except Exception as exc:
            logger.debug(f"标记价拉取失败 {symbol}: {exc}")
            return cached[1] if cached else None

        try:
            mp = MarkPriceData(
                symbol=raw["symbol"],
                mark_price=float(raw["markPrice"]),
                index_price=float(raw["indexPrice"]),
                funding_rate=float(raw.get("lastFundingRate", 0)),
                next_funding_time=raw.get("nextFundingTime", 0),
                event_time=0,
            )
        except (KeyError, ValueError):
            return cached[1] if cached else None

        self._mark_price_cache[cache_key] = (now, mp)
        return mp

    # ---- 计算 OI 变化率 ----

    async def calc_oi_change_pct(
        self, symbol: str, lookback_minutes: int = 60
    ) -> float:
        """计算 OI 在指定时间窗口内的变化率 (%)."""
        limit = max(lookback_minutes // 5 + 1, 3)
        hist = await self.fetch_open_interest_hist(symbol, period="5m", limit=limit)
        if len(hist) < 2:
            return 0.0
        first = hist[0]["open_interest"]
        last = hist[-1]["open_interest"]
        if first <= 0:
            return 0.0
        return (last - first) / first * 100
