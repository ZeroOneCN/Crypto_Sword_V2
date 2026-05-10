"""Binance User Data Stream client — listenKey lifecycle + private WS events.

Manages the full listenKey lifecycle (create, keepalive, delete) and
connects to the Binance private WebSocket endpoint to receive real-time
order and account updates. Dispatches parsed events to registered
callbacks.

Binance 2026 architecture:
  - REST:  POST   /fapi/v1/listenKey  → create listenKey
           PUT    /fapi/v1/listenKey  → keepalive (every 30 min)
           DELETE /fapi/v1/listenKey  → close stream
  - WS:    wss://fstream.binance.com/private/ws/{listenKey}
  - Events: ORDER_TRADE_UPDATE, ACCOUNT_UPDATE, MARGIN_CALL, listenKeyExpired

Usage::

    stream = UserDataStream(api_key="...", api_secret="...", testnet=False)

    @stream.on_order_update
    async def handle_order(event: dict) -> None:
        print(f"Order update: {event}")

    @stream.on_account_update
    async def handle_account(event: dict) -> None:
        print(f"Account update: {event}")

    await stream.start()
    # ... running ...
    await stream.stop()
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import httpx
import websockets
from loguru import logger

from cryptopilot.core.exceptions import MarketDataError
from cryptopilot.utils.time_utils import utc_timestamp_ms

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FUTURES_REST = "https://fapi.binance.com"
FUTURES_REST_TESTNET = "https://testnet.binancefuture.com"

FUTURES_WS_PRIVATE = "wss://fstream.binance.com/private"
FUTURES_WS_PRIVATE_TESTNET = "wss://stream.binancefuture.com/private"

LISTENKEY_PATH = "/fapi/v1/listenKey"

# Binance docs: keepalive at least every 60 min; we do 30 min for safety.
KEEPALIVE_INTERVAL_SEC = 30 * 60  # 30 minutes

# Reconnection backoff
MAX_RECONNECT_DELAY_SEC = 60.0
INITIAL_RECONNECT_DELAY_SEC = 1.0

# ---------------------------------------------------------------------------
# Typed aliases
# ---------------------------------------------------------------------------

OrderUpdateCallback = Callable[[dict[str, Any]], Awaitable[None]]
AccountUpdateCallback = Callable[[dict[str, Any]], Awaitable[None]]
MarginCallCallback = Callable[[dict[str, Any]], Awaitable[None]]


# ---------------------------------------------------------------------------
# Structured event dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OrderTradeUpdate:
    """Parsed ORDER_TRADE_UPDATE event.

    Mirrors the Binance futures user data stream payload for
    order and trade lifecycle events.
    """

    symbol: str
    client_order_id: str
    order_id: int
    side: str  # BUY / SELL
    order_type: str  # MARKET / LIMIT / STOP / TAKE_PROFIT / …
    order_status: str  # NEW / PARTIALLY_FILLED / FILLED / CANCELED / EXPIRED / …
    time_in_force: str
    orig_qty: float
    executed_qty: float
    avg_price: float
    stop_price: float
    position_side: str  # BOTH / LONG / SHORT
    reduce_only: bool
    last_filled_qty: float
    last_filled_price: float
    commission: float
    commission_asset: str
    trade_time: int  # ms
    realized_pnl: float
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_ws(cls, payload: dict[str, Any]) -> "OrderTradeUpdate":
        o = payload.get("o", {})
        return cls(
            symbol=o.get("s", ""),
            client_order_id=o.get("c", ""),
            order_id=int(o.get("i", 0) or 0),
            side=o.get("S", ""),
            order_type=o.get("o", ""),
            order_status=o.get("X", ""),
            time_in_force=o.get("f", ""),
            orig_qty=float(o.get("q", 0) or 0),
            executed_qty=float(o.get("z", 0) or 0),
            avg_price=float(o.get("ap", 0) or 0),
            stop_price=float(o.get("sp", 0) or 0),
            position_side=o.get("ps", "BOTH"),
            reduce_only=o.get("R", False) is True or o.get("R", "") == "true",
            last_filled_qty=float(o.get("l", 0) or 0),
            last_filled_price=float(o.get("L", 0) or 0),
            commission=float(o.get("n", 0) or 0),
            commission_asset=o.get("N", ""),
            trade_time=int(o.get("T", 0) or 0),
            realized_pnl=float(o.get("rp", 0) or 0),
            raw=payload,
        )


@dataclass
class AccountUpdate:
    """Parsed ACCOUNT_UPDATE event.

    Contains balance and position deltas pushed by the exchange.
    """

    event_time: int  # ms
    balances: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_ws(cls, payload: dict[str, Any]) -> "AccountUpdate":
        a = payload.get("a", {})
        return cls(
            event_time=int(payload.get("E", 0) or 0),
            balances=[
                {
                    "asset": b.get("a", ""),
                    "wallet_balance": float(b.get("wb", 0) or 0),
                    "cross_wallet_balance": float(b.get("cw", 0) or 0),
                    "balance_change": float(b.get("bc", 0) or 0),
                }
                for b in a.get("B", [])
            ],
            positions=[
                {
                    "symbol": p.get("s", ""),
                    "position_side": p.get("ps", "BOTH"),
                    "position_amount": float(p.get("pa", 0) or 0),
                    "entry_price": float(p.get("ep", 0) or 0),
                    "mark_price": float(p.get("mp", 0) or 0),
                    "unrealized_pnl": float(p.get("up", 0) or 0),
                    "margin_type": p.get("mt", ""),
                    "isolated_wallet": float(p.get("iw", 0) or 0),
                    "position_initial_margin": float(p.get("im", 0) or 0),
                    "maintenance_margin": float(p.get("mm", 0) or 0),
                }
                for p in a.get("P", [])
            ],
            raw=payload,
        )


@dataclass
class MarginCall:
    """Parsed MARGIN_CALL event."""

    symbol: str
    position_side: str
    margin_call_price: float
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_ws(cls, payload: dict[str, Any]) -> "MarginCall":
        p = payload.get("p", {})
        return cls(
            symbol=p.get("s", ""),
            position_side=p.get("ps", "BOTH"),
            margin_call_price=float(p.get("mp", 0) or 0),
            raw=payload,
        )


# ---------------------------------------------------------------------------
# UserDataStream
# ---------------------------------------------------------------------------


class UserDataStream:
    """Manages a Binance User Data Stream (listenKey-based private WS)."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        *,
        proxy: str | None = None,
        reconnect_max_attempts: int = 100,
        reconnect_base_delay: float = 1.0,
        keepalive_interval: float = KEEPALIVE_INTERVAL_SEC,
    ) -> None:
        """Initialise the user data stream client.

        Args:
            api_key: Binance API key.
            api_secret: Binance API secret.
            testnet: If True, use testnet endpoints.
            proxy: Optional HTTPS proxy URL for REST calls.
            reconnect_max_attempts: Max reconnection attempts before raising.
            reconnect_base_delay: Base delay in seconds for exponential backoff.
            keepalive_interval: Seconds between listenKey keepalive PUTs.
        """
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        self._proxy = proxy
        self._reconnect_max_attempts = reconnect_max_attempts
        self._reconnect_base_delay = reconnect_base_delay
        self._keepalive_interval = keepalive_interval

        # REST base URL
        self._rest_base = FUTURES_REST_TESTNET if testnet else FUTURES_REST

        # WebSocket URL template (listenKey appended at connect time)
        self._ws_base = FUTURES_WS_PRIVATE if not testnet else FUTURES_WS_PRIVATE_TESTNET

        # State
        self._listen_key: Optional[str] = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_count = 0
        self._shutdown_event = asyncio.Event()
        self._keepalive_task: Optional[asyncio.Task[None]] = None
        self._listen_task: Optional[asyncio.Task[None]] = None

        # HTTP client (created lazily)
        self._http: Optional[httpx.AsyncClient] = None

        # Callbacks — lists of coroutine functions
        self._order_callbacks: list[OrderUpdateCallback] = []
        self._account_callbacks: list[AccountUpdateCallback] = []
        self._margin_call_callbacks: list[MarginCallCallback] = []

    # ----------------------------------------------------------------
    # Callback registration (decorator style)
    # ----------------------------------------------------------------

    def on_order_update(self, cb: OrderUpdateCallback) -> OrderUpdateCallback:
        """Register a callback for ORDER_TRADE_UPDATE events.

        Can be used as a bare function or decorator::

            @stream.on_order_update
            async def handle(event): ...
        """
        self._order_callbacks.append(cb)
        return cb

    def on_account_update(self, cb: AccountUpdateCallback) -> AccountUpdateCallback:
        """Register a callback for ACCOUNT_UPDATE events."""
        self._account_callbacks.append(cb)
        return cb

    def on_margin_call(self, cb: MarginCallCallback) -> MarginCallCallback:
        """Register a callback for MARGIN_CALL events."""
        self._margin_call_callbacks.append(cb)
        return cb

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """Obtain a listenKey, connect to the private WS, start keepalive timer."""
        if self._running:
            logger.warning("UserDataStream 已在运行中，忽略重复 start()")
            return

        self._running = True
        self._shutdown_event.clear()
        self._reconnect_count = 0

        # Create HTTP client
        self._http = self._build_http_client()

        try:
            await self._connect_loop()
        except asyncio.CancelledError:
            logger.info("UserDataStream 任务已取消")
        finally:
            await self._cleanup()

    async def stop(self) -> None:
        """Signal shutdown and clean up resources."""
        self._running = False
        self._shutdown_event.set()
        await self._cleanup()

    @property
    def is_connected(self) -> bool:
        return (
            self._ws is not None
            and self._ws.close_code is None
        )

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def listen_key(self) -> Optional[str]:
        return self._listen_key

    # ----------------------------------------------------------------
    # Connection loop
    # ----------------------------------------------------------------

    async def _connect_loop(self) -> None:
        """Main connection loop with exponential backoff reconnection.

        On each reconnect, a fresh listenKey is obtained because the old
        one may have expired during the disconnection window.
        """
        attempt = 0

        while self._running:
            try:
                # Obtain a fresh listenKey on every connection attempt.
                await self._acquire_listen_key()
                await self._connect_and_listen()
            except (websockets.ConnectionClosed, OSError, httpx.HTTPError) as exc:
                attempt += 1
                self._reconnect_count = attempt

                if attempt > self._reconnect_max_attempts:
                    raise MarketDataError(
                        f"UserDataStream 重连失败，已达最大尝试次数 "
                        f"({self._reconnect_max_attempts})"
                    ) from exc

                delay = min(
                    self._reconnect_base_delay * (2 ** (attempt - 1)),
                    MAX_RECONNECT_DELAY_SEC,
                )
                logger.warning(
                    f"UserDataStream 断开 (第 {attempt}/{self._reconnect_max_attempts} 次重试)，"
                    f"{delay:.1f} 秒后重连… ({exc})"
                )
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=delay
                    )
                    return  # shutdown requested
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                return

    async def _connect_and_listen(self) -> None:
        """Open the private WebSocket and enter the message loop."""
        if not self._listen_key:
            raise MarketDataError("listenKey 未就绪，无法连接私有 WebSocket")

        url = f"{self._ws_base}/ws/{self._listen_key}"
        logger.info(f"正在连接用户数据流: {url[:80]}…")

        self._ws = await websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
            max_size=2**20,  # 1 MB — private events are small
        )
        logger.info("用户数据流 WebSocket 已连接")

        # Start keepalive background task
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        await self._listen()

    async def _listen(self) -> None:
        """Read messages and dispatch to callbacks."""
        try:
            async for raw in self._ws:
                if not self._running:
                    break
                await self._dispatch(raw)
        except websockets.ConnectionClosed:
            pass
        finally:
            # Cancel keepalive on disconnect
            if self._keepalive_task and not self._keepalive_task.done():
                self._keepalive_task.cancel()
                self._keepalive_task = None

    # ----------------------------------------------------------------
    # Message dispatch
    # ----------------------------------------------------------------

    async def _dispatch(self, raw: str | bytes) -> None:
        """Parse and dispatch a single WS message to registered callbacks."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"用户数据流收到无效 JSON: {str(raw)[:200]}")
            return

        event_type = data.get("e", "")

        if event_type == "ORDER_TRADE_UPDATE":
            parsed = OrderTradeUpdate.from_ws(data)
            logger.debug(
                f"订单更新 {parsed.symbol}: {parsed.client_order_id} → "
                f"{parsed.order_status} executed={parsed.executed_qty}/{parsed.orig_qty}"
            )
            for cb in self._order_callbacks:
                try:
                    await cb(parsed)  # type: ignore[arg-type]
                except Exception:
                    logger.exception("订单更新回调异常")

        elif event_type == "ACCOUNT_UPDATE":
            parsed = AccountUpdate.from_ws(data)
            logger.debug(
                f"账户更新: {len(parsed.balances)} 余额变更, "
                f"{len(parsed.positions)} 持仓变更"
            )
            for cb in self._account_callbacks:
                try:
                    await cb(parsed)  # type: ignore[arg-type]
                except Exception:
                    logger.exception("账户更新回调异常")

        elif event_type == "MARGIN_CALL":
            parsed = MarginCall.from_ws(data)
            logger.warning(
                f"保证金追缴警告! {parsed.symbol} {parsed.position_side} "
                f"价格={parsed.margin_call_price:.4f}"
            )
            for cb in self._margin_call_callbacks:
                try:
                    await cb(parsed)  # type: ignore[arg-type]
                except Exception:
                    logger.exception("保证金追缴回调异常")

        elif event_type == "listenKeyExpired":
            logger.warning("listenKey 已过期，将触发重连获取新 Key")
            # Force a disconnect so the main loop reconnects with a fresh key
            if self._ws:
                try:
                    await self._ws.close()
                except Exception:
                    pass

        else:
            logger.debug(f"未处理的事件类型: {event_type} data={str(data)[:200]}")

    # ----------------------------------------------------------------
    # REST — listenKey management
    # ----------------------------------------------------------------

    async def _acquire_listen_key(self) -> None:
        """POST /fapi/v1/listenKey to obtain a new listenKey."""
        # Clean up any previously held key
        if self._listen_key:
            try:
                await self._delete_listen_key(self._listen_key)
            except Exception:
                logger.warning("清理旧 listenKey 失败", exc_info=True)
            self._listen_key = None

        data = await self._signed_request("POST", LISTENKEY_PATH)
        self._listen_key = data.get("listenKey", "")
        if not self._listen_key:
            raise MarketDataError("Binance 返回的 listenKey 为空")
        logger.info(f"已获取 listenKey: {self._listen_key[:12]}…")

    async def _keepalive_loop(self) -> None:
        """Background task: PUT /fapi/v1/listenKey every KEEPALIVE_INTERVAL_SEC."""
        if not self._listen_key:
            return

        while self._running and self._listen_key:
            try:
                await asyncio.sleep(self._keepalive_interval)
                if not self._running or not self._listen_key:
                    break
                await self._signed_request("PUT", LISTENKEY_PATH)
                logger.debug("listenKey keepalive 成功")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("listenKey keepalive 失败", exc_info=True)
                # Don't break — keep trying on next interval

    async def _delete_listen_key(self, key: str | None = None) -> None:
        """DELETE /fapi/v1/listenKey to close the stream."""
        target = key or self._listen_key
        if not target:
            return
        try:
            await self._signed_request("DELETE", LISTENKEY_PATH)
            logger.info("listenKey 已删除")
        except Exception as exc:
            logger.warning(f"删除 listenKey 失败: {exc}")

    # ----------------------------------------------------------------
    # Internal — signed REST requests
    # ----------------------------------------------------------------

    async def _signed_request(
        self, method: str, path: str, extra_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a signed request to the Binance REST API.

        Uses the same HMAC-SHA256 signing scheme as OrderExecutor.
        """
        if self._http is None:
            self._http = self._build_http_client()

        params: dict[str, Any] = dict(extra_params or {})
        params["timestamp"] = utc_timestamp_ms()
        params["recvWindow"] = 5000

        # Build signature
        query = urllib.parse.urlencode(
            sorted(params.items()), quote_via=urllib.parse.quote
        )
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        query += f"&signature={signature}"

        url = f"{path}?{query}"

        try:
            if method == "GET":
                resp = await self._http.get(url)
            elif method == "POST":
                resp = await self._http.post(url)
            elif method == "PUT":
                resp = await self._http.put(url)
            elif method == "DELETE":
                resp = await self._http.delete(url)
            else:
                raise MarketDataError(f"Unsupported HTTP method: {method}")
        except httpx.RequestError as exc:
            raise MarketDataError(f"listenKey HTTP 请求失败: {exc}") from exc

        data = resp.json()
        if resp.status_code >= 400:
            code = data.get("code", resp.status_code)
            msg = data.get("msg", str(data))
            raise MarketDataError(f"Binance listenKey 错误 [{code}]: {msg}")

        return data

    # ----------------------------------------------------------------
    # Internal — HTTP client
    # ----------------------------------------------------------------

    def _build_http_client(self) -> httpx.AsyncClient:
        """Create a shared httpx.AsyncClient for REST calls."""
        kwargs: dict[str, Any] = {
            "base_url": self._rest_base,
            "timeout": httpx.Timeout(30.0),
            "headers": {"X-MBX-APIKEY": self._api_key},
        }
        if self._proxy:
            kwargs["proxy"] = self._proxy
        return httpx.AsyncClient(**kwargs)

    # ----------------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------------

    async def _cleanup(self) -> None:
        """Release all resources: cancel tasks, close WS, delete listenKey, close HTTP."""
        # Cancel keepalive
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        self._keepalive_task = None

        # Close WebSocket
        if self._ws and self._ws.close_code is None:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None

        # Delete listenKey (best-effort)
        if self._listen_key:
            try:
                await self._delete_listen_key()
            except Exception:
                pass
            self._listen_key = None

        # Close HTTP client
        if self._http:
            try:
                await self._http.aclose()
            except Exception:
                pass
            self._http = None

        logger.info("UserDataStream 已完全清理")


# ---------------------------------------------------------------------------
# Convenience: create a UserDataStream from config + env
# ---------------------------------------------------------------------------


def create_user_data_stream_from_config(
    api_key: str,
    api_secret: str,
    testnet: bool = False,
    *,
    proxy: str | None = None,
) -> UserDataStream:
    """Factory that builds a UserDataStream with sensible defaults.

    Args:
        api_key: Binance API key.
        api_secret: Binance API secret.
        testnet: Use testnet if True.
        proxy: Optional HTTPS proxy URL.

    Returns:
        Configured UserDataStream instance.
    """
    return UserDataStream(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        proxy=proxy,
        reconnect_max_attempts=100,
        reconnect_base_delay=1.0,
        keepalive_interval=KEEPALIVE_INTERVAL_SEC,
    )
