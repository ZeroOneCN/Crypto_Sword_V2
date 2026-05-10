"""Binance WebSocket Trading API client (futures).

Provides order.place, order.cancel, order.status, account.status,
position.information, and order.modify via Binance's JSON-RPC WebSocket
endpoint.  Zero request weight — no rate limits over WS.

Reference: Binance WebSocket Trading API (2026)
  Base (prod):   wss://ws-fapi.binance.com/ws-fapi/v1
  Base (testnet): wss://testnet.binancefuture.com/ws-fapi/v1

Key rules:
  - price and quantity MUST be strings, never floats
  - timestamp is an int (milliseconds)
  - params dict must include apiKey, timestamp, signature
  - signature: sort params alphabetically, join with &, HMAC-SHA256
  - server pings every 3 min; must pong within 10 min
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from loguru import logger

from cryptopilot.core.exceptions import OrderError, InsufficientBalance, RateLimitExceeded

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WS_FAPI_PROD = "wss://ws-fapi.binance.com/ws-fapi/v1"
WS_FAPI_TESTNET = "wss://testnet.binancefuture.com/ws-fapi/v1"

# JSON-RPC method strings (Binance WS Trading API)
METHOD_PLACE_ORDER = "order.place"
METHOD_CANCEL_ORDER = "order.cancel"
METHOD_QUERY_ORDER = "order.status"
METHOD_MODIFY_ORDER = "order.modify"
METHOD_ACCOUNT_STATUS = "account.status"
METHOD_POSITION_INFORMATION = "position.information"

# Connection constants
PING_INTERVAL = 180       # server sends ping every 3 min
PONG_TIMEOUT = 600        # must pong within 10 min
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 60.0
RECONNECT_JITTER = 0.5    # ±50 % jitter
REQUEST_TIMEOUT = 30.0    # seconds to wait for a response

# Binance error codes that map to known exceptions
ERROR_INSUFFICIENT_BALANCE = -2010
ERROR_RATE_LIMIT = -1015


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _sign_params(params: dict[str, Any], api_secret: str) -> str:
    """HMAC-SHA256 signature for Binance WS Trading API.

    Sorts param keys alphabetically, joins with ``&`` (no URL-encoding needed
    for WS — the spec says to use REST-style query string signing), then
    HMAC-SHA256 with the api_secret.
    """
    ordered = sorted(params.items())
    query_string = "&".join(f"{k}={v}" for k, v in ordered)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def _now_ms() -> int:
    """Current UTC timestamp in milliseconds."""
    return int(time.time() * 1000)


def _make_id() -> str:
    """Unique JSON-RPC request id (cryptographically random prefix)."""
    import secrets
    return secrets.token_hex(8)


def _build_params(
    api_key: str,
    api_secret: str,
    method_params: dict[str, Any],
) -> dict[str, Any]:
    """Merge apiKey + timestamp + signature into method_params and return the
    full params dict ready for the JSON-RPC ``params`` field."""
    params: dict[str, Any] = dict(method_params)
    params["apiKey"] = api_key
    params["timestamp"] = _now_ms()
    params["signature"] = _sign_params(params, api_secret)
    return params


def _serialise_params(params: dict[str, Any]) -> dict[str, Any]:
    """Ensure price/quantity values are strings (as required by Binance WS).

    Also converts bools to lowercase ``"true"`` / ``"false"`` strings.
    """
    out: dict[str, Any] = {}
    for k, v in params.items():
        if k in ("price", "quantity", "stopPrice", "activationPrice",
                 "callbackRate", "workingType"):
            out[k] = str(v)
        elif isinstance(v, bool):
            out[k] = "true" if v else "false"
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# WSTradingClient
# ---------------------------------------------------------------------------

class WSTradingClient:
    """Async WebSocket client for Binance Futures Trading API.

    Usage::

        client = WSTradingClient(api_key="...", api_secret="...", testnet=True)
        await client.connect()

        resp = await client.place_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT",
            quantity=0.001, price=50000.0,
        )

        await client.disconnect()

    Connection lifecycle:
        - ``connect()``  — open WS and start background reader
        - ``disconnect()`` — graceful close, cancel tasks
        - automatic reconnection with exponential backoff on drop
    """

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        *,
        request_timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._url = WS_FAPI_TESTNET if testnet else WS_FAPI_PROD
        self._request_timeout = request_timeout

        # Connection state
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._running = False

        # Lock for serialising sends (websocket isn't fully thread-safe)
        self._send_lock = asyncio.Lock()

        # Pending requests: id → asyncio.Future
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

        # Reconnection
        self._reconnect_attempt = 0
        self._should_reconnect = True

        # Log tag
        self._tag = f"WSTradingClient({self._url})"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the WebSocket connection and start the reader loop.

        Idempotent — calling connect on an already-connected client is a no-op.
        """
        if self._running:
            logger.debug(f"{self._tag} already connected")
            return

        self._should_reconnect = True
        self._reconnect_attempt = 0
        await self._connect_once()
        self._running = True
        logger.info(f"{self._tag} connected ✓")

    async def disconnect(self) -> None:
        """Gracefully close the WebSocket and cancel background tasks."""
        self._should_reconnect = False
        self._running = False

        # Cancel reader task
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._reader_task = None

        # Close websocket
        if self._ws is not None:
            try:
                await self._ws.close(reason="Client shutdown")
            except Exception:
                pass
            self._ws = None

        # Fail all pending futures so no caller hangs forever
        async with self._send_lock:
            pending = list(self._pending.items())
            self._pending.clear()
        for rid, fut in pending:
            if not fut.done():
                fut.set_exception(
                    OrderError("WebSocket client disconnected — request cancelled")
                )

        logger.info(f"{self._tag} disconnected")

    # ------------------------------------------------------------------
    # Public trading API
    # ------------------------------------------------------------------

    async def place_order(
        self,
        symbol: str,
        side: str,
        type: str,
        quantity: float,
        price: Optional[float] = None,
        stopPrice: Optional[float] = None,
        reduceOnly: bool = False,
        positionSide: str = "BOTH",
        timeInForce: str = "GTC",
        newClientOrderId: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        """Place a new order via ``order.place``.

        Args:
            symbol: Trading pair, e.g. ``"BTCUSDT"``.
            side: ``"BUY"`` or ``"SELL"``.
            type: ``"LIMIT"``, ``"MARKET"``, ``"STOP_MARKET"``, ``"TAKE_PROFIT_MARKET"``.
            quantity: Order quantity.
            price: Limit price (required for LIMIT orders).
            stopPrice: Trigger price for stop/take-profit orders.
            reduceOnly: Close-position-only flag.
            positionSide: ``"BOTH"``, ``"LONG"``, or ``"SHORT"``.
            timeInForce: ``"GTC"``, ``"IOC"``, ``"FOK"``.
            newClientOrderId: Custom client order id (auto-generated if empty).

        Returns:
            Parsed order response dict from Binance.
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
        }

        if price is not None:
            params["price"] = price
        if stopPrice is not None:
            params["stopPrice"] = stopPrice
        if reduceOnly:
            params["reduceOnly"] = reduceOnly
        if positionSide and positionSide != "BOTH":
            params["positionSide"] = positionSide
        if type == "LIMIT":
            params["timeInForce"] = timeInForce
        if newClientOrderId:
            params["newClientOrderId"] = newClientOrderId

        params.update(extra)

        logger.debug(f"{self._tag} place_order: {symbol} {side} {type} qty={quantity}")
        return await self._call(METHOD_PLACE_ORDER, params)

    async def cancel_order(
        self,
        symbol: str,
        orderId: Optional[int] = None,
        origClientOrderId: Optional[str] = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Cancel an open order via ``order.cancel``.

        Must provide at least one of ``orderId`` or ``origClientOrderId``.

        Args:
            symbol: Trading pair.
            orderId: Exchange-assigned order ID.
            origClientOrderId: Client-assigned order ID.

        Returns:
            Cancellation response dict.
        """
        if orderId is None and origClientOrderId is None:
            raise OrderError("cancel_order: must provide orderId or origClientOrderId")

        params: dict[str, Any] = {"symbol": symbol}
        if orderId is not None:
            params["orderId"] = orderId
        if origClientOrderId is not None:
            params["origClientOrderId"] = origClientOrderId
        params.update(extra)

        logger.debug(f"{self._tag} cancel_order: {symbol}")
        return await self._call(METHOD_CANCEL_ORDER, params)

    async def query_order(
        self,
        symbol: str,
        orderId: Optional[int] = None,
        origClientOrderId: Optional[str] = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Query order status via ``order.status``.

        Args:
            symbol: Trading pair.
            orderId: Exchange-assigned order ID.
            origClientOrderId: Client-assigned order ID.

        Returns:
            Order status dict.
        """
        if orderId is None and origClientOrderId is None:
            raise OrderError("query_order: must provide orderId or origClientOrderId")

        params: dict[str, Any] = {"symbol": symbol}
        if orderId is not None:
            params["orderId"] = orderId
        if origClientOrderId is not None:
            params["origClientOrderId"] = origClientOrderId
        params.update(extra)

        logger.debug(f"{self._tag} query_order: {symbol}")
        return await self._call(METHOD_QUERY_ORDER, params)

    async def modify_order(
        self,
        symbol: str,
        orderId: Optional[int] = None,
        origClientOrderId: Optional[str] = None,
        price: Optional[float] = None,
        quantity: Optional[float] = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Modify an open order via ``order.modify``.

        Args:
            symbol: Trading pair.
            orderId: Exchange-assigned order ID.
            origClientOrderId: Client-assigned order ID.
            price: New limit price.
            quantity: New quantity.

        Returns:
            Modify response dict.
        """
        if orderId is None and origClientOrderId is None:
            raise OrderError("modify_order: must provide orderId or origClientOrderId")

        params: dict[str, Any] = {"symbol": symbol}
        if orderId is not None:
            params["orderId"] = orderId
        if origClientOrderId is not None:
            params["origClientOrderId"] = origClientOrderId
        if price is not None:
            params["price"] = price
        if quantity is not None:
            params["quantity"] = quantity
        params.update(extra)

        logger.debug(f"{self._tag} modify_order: {symbol}")
        return await self._call(METHOD_MODIFY_ORDER, params)

    async def get_account(self, **extra: Any) -> dict[str, Any]:
        """Query account balances and margin info via ``account.status``.

        Returns:
            Account status dict (balances, margin ratio, PnL, etc.).
        """
        logger.debug(f"{self._tag} get_account")
        return await self._call(METHOD_ACCOUNT_STATUS, extra)

    async def get_positions(
        self,
        symbol: Optional[str] = None,
        **extra: Any,
    ) -> list[dict[str, Any]]:
        """Query position information via ``position.information``.

        Args:
            symbol: Filter to a single symbol (optional).

        Returns:
            List of position dicts (may be a single dict wrapped in a list).
        """
        params: dict[str, Any] = {**extra}
        if symbol is not None:
            params["symbol"] = symbol

        logger.debug(f"{self._tag} get_positions{symbol and ' for '+symbol or ''}")
        raw = await self._call(METHOD_POSITION_INFORMATION, params)
        # Binance returns a list for position.information; normalise
        if isinstance(raw, dict):
            return [raw]
        if isinstance(raw, list):
            return raw
        return [raw]

    # ------------------------------------------------------------------
    # Internal — request dispatch
    # ------------------------------------------------------------------

    async def _call(self, method: str, raw_params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and await the response.

        Serialises params (string coercion), signs them, sends the request,
        and waits for the matching ``id`` response from the reader loop.
        """
        req_id = _make_id()
        params = _serialise_params(raw_params)
        signed = _build_params(self._api_key, self._api_secret, params)

        request = json.dumps({
            "id": req_id,
            "method": method,
            "params": signed,
        })

        # Create future BEFORE acquiring send_lock to avoid deadlock
        # if the reader resolves while we hold the lock.
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = fut

        try:
            async with self._send_lock:
                await self._ensure_connected()
                await self._ws_send(request)

            # Wait for response (with timeout)
            result = await asyncio.wait_for(fut, timeout=self._request_timeout)
            return result

        except asyncio.TimeoutError:
            raise OrderError(f"Request {method} timed out after {self._request_timeout}s")
        except (ConnectionClosed, WebSocketException) as exc:
            raise OrderError(f"WebSocket error during {method}: {exc}") from exc
        finally:
            self._pending.pop(req_id, None)

    # ------------------------------------------------------------------
    # Internal — WebSocket operations
    # ------------------------------------------------------------------

    async def _ensure_connected(self) -> None:
        """Reconnect if the WebSocket is down (and we haven't been stopped)."""
        if self._ws is not None and self._ws.state == websockets.protocol.State.OPEN:
            return
        if not self._should_reconnect:
            raise OrderError("WebSocket client has been shut down")
        await self._connect_once()
        # Restart reader if needed
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._reader_loop())

    async def _connect_once(self) -> None:
        """Perform a single connection attempt."""
        self._ws = await websockets.connect(
            self._url,
            ping_interval=None,      # we handle pings ourselves
            ping_timeout=None,
            close_timeout=5,
            max_size=2 ** 20,        # 1 MB max message
        )
        logger.debug(f"{self._tag} WebSocket opened")

    async def _ws_send(self, payload: str) -> None:
        """Send a JSON string through the websocket with error handling."""
        try:
            await self._ws.send(payload)  # type: ignore[union-attr]
        except (ConnectionClosed, WebSocketException) as exc:
            self._ws = None
            raise OrderError(f"WebSocket send failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal — reader loop
    # ------------------------------------------------------------------

    async def _reader_loop(self) -> None:
        """Background task that reads incoming messages.

        Handles:
          - JSON-RPC responses → match by id, resolve pending futures
          - Server pings → respond with pong
          - Connection drops → trigger reconnection
        """
        while self._should_reconnect:
            try:
                await self._read_messages()
            except asyncio.CancelledError:
                logger.debug(f"{self._tag} reader cancelled")
                return
            except (ConnectionClosed, WebSocketException) as exc:
                logger.warning(f"{self._tag} connection lost: {exc}")
            except Exception:
                logger.exception(f"{self._tag} unexpected reader error")

            # Try to reconnect
            if not self._should_reconnect:
                return

            await self._reconnect()

    async def _read_messages(self) -> None:
        """Inner loop: read messages from the active websocket."""
        ws = self._ws
        if ws is None:
            return

        async for raw in ws:
            if isinstance(raw, bytes):
                # Binance WS Trading API sends text, but handle bytes just in case
                raw = raw.decode("utf-8")

            if not isinstance(raw, str):
                logger.warning(f"{self._tag} unexpected message type: {type(raw)}")
                continue

            # Handle server ping (plain text 'ping' or JSON ping)
            await self._handle_ping(raw)

            # Try parsing as JSON-RPC response
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"{self._tag} non-JSON message: {raw[:200]}")
                continue

            self._dispatch_response(msg)

    async def _handle_ping(self, raw: str) -> None:
        """Respond to server pings.

        Binance WS Trading API may send a plain-text ``ping`` frame or use a
        different mechanism.  We handle both the ``"ping"`` string and JSON
        ping frames gracefully.
        """
        if raw.strip().lower() == "ping":
            try:
                await self._ws.send("pong")  # type: ignore[union-attr]
            except Exception:
                pass

    def _dispatch_response(self, msg: dict[str, Any]) -> None:
        """Route an incoming JSON-RPC response/notification to its future."""
        # Skip if not a response (no id)
        rid = msg.get("id")
        if rid is None:
            # Could be a server notification — log and ignore
            logger.debug(f"{self._tag} notification: {msg.get('method', '')}")
            return

        fut = self._pending.get(rid)
        if fut is None:
            logger.debug(f"{self._tag} response for unknown id: {rid}")
            return

        if fut.done():
            return

        # Check for errors
        error = msg.get("error")
        if error is not None:
            code = error.get("code", 0)
            message = error.get("msg", str(error))

            if code == ERROR_INSUFFICIENT_BALANCE:
                fut.set_exception(InsufficientBalance(message))
            elif code == ERROR_RATE_LIMIT:
                fut.set_exception(RateLimitExceeded(message))
            else:
                fut.set_exception(OrderError(f"Binance error [{code}]: {message}"))
            return

        # Success — return the result
        result = msg.get("result", msg)
        fut.set_result(result)

    # ------------------------------------------------------------------
    # Internal — reconnection
    # ------------------------------------------------------------------

    async def _reconnect(self) -> None:
        """Exponential-backoff reconnection loop."""
        delay = min(
            RECONNECT_BASE_DELAY * (2 ** self._reconnect_attempt),
            RECONNECT_MAX_DELAY,
        )
        # Add ±50 % jitter
        import random
        jitter = delay * RECONNECT_JITTER * (2 * random.random() - 1)
        delay = max(0.1, delay + jitter)

        self._reconnect_attempt += 1
        logger.info(
            f"{self._tag} reconnecting in {delay:.1f}s "
            f"(attempt {self._reconnect_attempt})"
        )

        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        if not self._should_reconnect:
            return

        try:
            self._ws = await websockets.connect(
                self._url,
                ping_interval=None,
                ping_timeout=None,
                close_timeout=5,
                max_size=2 ** 20,
            )
            self._reconnect_attempt = 0
            logger.info(f"{self._tag} reconnected ✓")
        except Exception as exc:
            logger.error(f"{self._tag} reconnection failed: {exc}")
            self._ws = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Check if the WebSocket is currently open."""
        return (
            self._ws is not None
            and self._running
            and self._ws.state == websockets.protocol.State.OPEN
        )

    @property
    def pending_count(self) -> int:
        """Number of in-flight requests awaiting response."""
        return len(self._pending)
