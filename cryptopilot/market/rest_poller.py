"""REST 行情轮询 — 替代 WebSocket, 每 N 秒拉取全币种 ticker + 强平数据."""

from __future__ import annotations

import asyncio
import time

import httpx
from loguru import logger

from cryptopilot.market.types import TickerData, LiquidationData, StreamMessage

FUTURES_REST = "https://fapi.binance.com"


class RestMarketPoller:
    """REST 轮询全币种 24hr ticker + 强平历史.

    WebSocket 在某些网络环境不可用时的替代方案.
    每 poll_interval 秒拉取一次全量数据并写入 MarketDataCache.
    """

    def __init__(
        self,
        cache,  # MarketDataCache
        proxy: str | None = None,
        poll_interval: float = 3.0,
    ) -> None:
        self._cache = cache
        self._proxy = proxy
        self._interval = poll_interval
        self._running = False
        self._liq_check_time: int = 0

    def _client(self) -> httpx.AsyncClient:
        kw: dict = {"base_url": FUTURES_REST, "timeout": 15.0}
        if self._proxy:
            kw["proxy"] = self._proxy
        return httpx.AsyncClient(**kw)

    async def start(self) -> None:
        """开始轮询. 阻塞直到 stop()."""
        self._running = True
        logger.info(f"REST 行情轮询已启动 (间隔={self._interval}s)")

        while self._running:
            try:
                await self._poll_tickers()
                await self._poll_liquidations()
            except Exception:
                logger.exception("REST 轮询异常")
            await asyncio.sleep(self._interval)

    async def stop(self) -> None:
        self._running = False

    @property
    def is_connected(self) -> bool:
        return self._running

    async def _poll_tickers(self) -> None:
        """拉取全币种 24hr ticker."""
        try:
            async with self._client() as c:
                resp = await c.get("/fapi/v1/ticker/24hr")
                if resp.status_code != 200:
                    return
                raw = resp.json()
        except Exception as exc:
            logger.debug(f"REST ticker 拉取失败: {exc}")
            return

        if not isinstance(raw, list):
            return

        count = 0
        for item in raw:
            try:
                sym = item.get("symbol", "")
                if not sym or "USDT" not in sym:
                    continue
                ticker = TickerData(
                    symbol=sym,
                    price=float(item["lastPrice"]),
                    price_change=float(item["priceChange"]),
                    price_change_pct=float(item["priceChangePercent"]),
                    high_24h=float(item["highPrice"]),
                    low_24h=float(item["lowPrice"]),
                    volume_24h=float(item["volume"]),
                    quote_volume_24h=float(item["quoteVolume"]),
                    event_time=item.get("closeTime", 0),
                )
                await self._cache.update(
                    StreamMessage(stream="rest_poller", data=ticker)
                )
                count += 1
            except (KeyError, ValueError):
                continue

        if count > 0 and not getattr(self, '_logged_first', False):
            self._logged_first = True
            logger.info(f"REST 行情就绪: {count} 个 USDT 合约对")

    async def _poll_liquidations(self) -> None:
        """拉取最近强平订单."""
        now = int(time.time() * 1000)
        if self._liq_check_time == 0:
            self._liq_check_time = now - 60_000  # 首次拉最近 1 分钟

        try:
            async with self._client() as c:
                resp = await c.get("/fapi/v1/allForceOrders", params={
                    "startTime": self._liq_check_time,
                    "endTime": now,
                    "limit": 50,
                })
                if resp.status_code != 200:
                    return
                raw = resp.json()
        except Exception:
            return

        self._liq_check_time = now

        if not isinstance(raw, list):
            return

        for item in raw:
            try:
                o = item.get("o", item)
                liq = LiquidationData(
                    symbol=o.get("s", ""),
                    side=o.get("S", ""),
                    quantity=float(o.get("q", 0)),
                    price=float(o.get("p", 0)),
                    order_type=o.get("o", ""),
                    event_time=item.get("E", 0),
                )
                await self._cache.update(
                    StreamMessage(stream="rest_poller", data=liq)
                )
            except (KeyError, ValueError):
                continue
