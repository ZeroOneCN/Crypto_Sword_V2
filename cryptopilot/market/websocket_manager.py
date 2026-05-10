"""Binance WebSocket manager with automatic reconnection and stream routing."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

import websockets
from loguru import logger

from cryptopilot.core.config import AppConfig
from cryptopilot.core.exceptions import MarketDataError
from cryptopilot.market.market_data_cache import MarketDataCache
from cryptopilot.market.types import (
    KlineData,
    TickerData,
    DepthData,
    MarkPriceData,
    OpenInterestData,
    LiquidationData,
    StreamMessage,
)

# Binance WS base URLs
FUTURES_WS = "wss://fstream.binance.com"
FUTURES_WS_TESTNET = "wss://stream.binancefuture.com"
SPOT_WS = "wss://stream.binance.com:9443"
SPOT_WS_TESTNET = "wss://testnet.binance.vision"

MAX_RECONNECT_DELAY = 60


class BinanceWebSocketManager:
    """Manages a combined WebSocket stream to Binance.

    Subscribes to specified streams for configured symbols, parses
    incoming messages into StreamMessage objects, and pushes them
    to a MarketDataCache. Handles disconnects with exponential
    backoff reconnection.
    """

    def __init__(
        self,
        config: AppConfig,
        data_cache: MarketDataCache,
    ) -> None:
        self._config = config
        self._cache = data_cache
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_count = 0
        self._shutdown_event = asyncio.Event()
        self._mini_ticker_logged = False

        self._base_url = self._build_base_url()
        self._stream_url = self._build_global_stream_url()

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and not (self._ws.close_code is not None) if self._ws else False

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """Connect and enter the listen loop. Blocks until stop() is called."""
        self._running = True
        self._shutdown_event.clear()
        self._reconnect_count = 0

        try:
            await self._connect_loop()
        except asyncio.CancelledError:
            logger.info("WebSocket 任务已取消")
        finally:
            await self._disconnect()

    async def stop(self) -> None:
        """Signal the manager to shut down."""
        self._running = False
        self._shutdown_event.set()
        await self._disconnect()

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _build_base_url(self) -> str:
        """Determine the WebSocket base URL from config."""
        ex = self._config.exchange
        if ex.trading_type == "futures":
            return FUTURES_WS_TESTNET if ex.testnet else FUTURES_WS
        return SPOT_WS_TESTNET if ex.testnet else SPOT_WS

    def _build_global_stream_url(self) -> str:
        """构建纯全市场流 URL — 不订阅任何 per-symbol 流.

        !miniTicker@arr: 全币种 24h 迷你行情 (每 1s 推送一次)
        !forceOrder@arr: 全市场强平订单
        """
        streams = ["!miniTicker@arr", "!forceOrder@arr"]
        return f"{self._base_url}/stream?streams={'/'.join(streams)}"

    async def _connect_loop(self) -> None:
        """Main connection loop with exponential backoff reconnection."""
        attempt = 0
        max_attempts = self._config.websocket.reconnect_max_attempts
        base_delay = self._config.websocket.reconnect_base_delay

        while self._running:
            try:
                await self._connect_and_listen()
            except (websockets.ConnectionClosed, OSError) as exc:
                attempt += 1
                self._reconnect_count = attempt

                if attempt > max_attempts:
                    raise MarketDataError(
                        f"WebSocket reconnection failed after {max_attempts} attempts"
                    ) from exc

                delay = min(base_delay * (2 ** (attempt - 1)), MAX_RECONNECT_DELAY)
                logger.warning(
                    f"WebSocket 断开 (第 {attempt}/{max_attempts} 次重试)，"
                    f"{delay:.1f} 秒后重连..."
                )
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=delay
                    )
                    # Shutdown requested during wait
                    return
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                return

    async def _connect_and_listen(self) -> None:
        """Open a connection and process messages."""
        logger.info(f"正在连接 WebSocket: {self._stream_url[:100]}...")
        self._ws = await websockets.connect(
            self._stream_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
            max_size=2**23,  # 8 MB
        )
        logger.info("WebSocket 已连接")
        await self._listen()

    async def _listen(self) -> None:
        """Read messages from the WebSocket and dispatch to cache."""
        while self._running and self._ws and self._ws.close_code is None:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=60)
            except asyncio.TimeoutError:
                continue

            messages = self._parse_message(raw)
            for msg in messages:
                if msg is not None:
                    await self._cache.update(msg)

    def _parse_message(self, raw: str | bytes) -> list[StreamMessage | None]:
        """Parse a raw WebSocket message into typed StreamMessages."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"WebSocket 收到无效 JSON: {raw[:200]}")
            return []

        if "stream" in data:
            stream_name = data["stream"]
            payload = data["data"]

            # !miniTicker@arr: data 是数组
            if stream_name == "!miniTicker@arr" and isinstance(payload, list):
                results = []
                for item in payload:
                    ticker = TickerData.from_ws(item)
                    results.append(StreamMessage(stream=stream_name, data=ticker))
                # 首条日志
                if not self._mini_ticker_logged:
                    self._mini_ticker_logged = True
                    logger.info(f"全市场行情就绪: {len(results)} 个币种 (!miniTicker@arr)")
                return results

            return [self._parse_single(stream_name, payload)]

        # forceOrder 可能以 {"e":"forceOrder", ...} 直接到达 (非组合模式)
        if "e" in data and data["e"] == "forceOrder":
            return [self._parse_force_order(data)]

        return []

    def _parse_single(self, stream: str, payload: dict) -> StreamMessage | None:
        """Parse a single stream message by type."""
        try:
            # 全市场强平流: stream = "!forceOrder@arr"
            if stream.startswith("!"):
                return self._parse_force_order(payload)

            parts = stream.split("@")
            if len(parts) < 2:
                return None

            symbol = parts[0].upper()
            stream_type = parts[1]

            if stream_type.startswith("kline"):
                interval = stream_type.split("_", 1)[1]
                kline = KlineData.from_ws(symbol, interval, payload["k"])
                return StreamMessage(stream=stream, data=kline)

            if stream_type == "ticker":
                ticker = TickerData.from_ws(payload)
                return StreamMessage(stream=stream, data=ticker)

            if stream_type.startswith("depth"):
                depth = DepthData.from_ws(payload)
                return StreamMessage(stream=stream, data=depth)

            # 新增: markPrice@1s
            if stream_type.startswith("markPrice"):
                mark = MarkPriceData.from_ws(payload)
                return StreamMessage(stream=stream, data=mark)

            # 新增: openInterest
            if stream_type.startswith("openInterest"):
                oi = OpenInterestData.from_ws(payload)
                return StreamMessage(stream=stream, data=oi)

        except (KeyError, ValueError, IndexError) as exc:
            logger.warning(f"解析数据流 '{stream}' 失败: {exc}")

        return None

    def _parse_force_order(self, payload: dict) -> StreamMessage | None:
        """Parse !forceOrder@arr message."""
        try:
            liq = LiquidationData.from_ws(payload)
            return StreamMessage(stream="!forceOrder@arr", data=liq)
        except (KeyError, ValueError) as exc:
            logger.warning(f"解析强平数据失败: {exc}")
            return None

    async def _disconnect(self) -> None:
        """Close the WebSocket connection if open."""
        if self._ws and not (self._ws.close_code is not None):
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
            logger.info("WebSocket 已断开")
