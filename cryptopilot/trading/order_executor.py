"""Binance REST API wrapper — order creation, cancellation, queries.

Supports both futures (fapi) and spot (api) endpoints. HMAC-SHA256
signed requests via httpx async client.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import httpx
from loguru import logger

from cryptopilot.core.config import AppConfig
from cryptopilot.core.exceptions import OrderError, InsufficientBalance, InvalidPrecision, RateLimitExceeded
from cryptopilot.trading.precision import parse_symbol_filters, clamp_qty, clamp_price
from cryptopilot.trading.rate_limiter import RateLimiter
from cryptopilot.utils.time_utils import utc_timestamp_ms

# Binance REST base URLs
FUTURES_REST = "https://fapi.binance.com"
FUTURES_REST_TESTNET = "https://testnet.binancefuture.com"
SPOT_REST = "https://api.binance.com"
SPOT_REST_TESTNET = "https://testnet.binance.vision"


@dataclass
class OrderRequest:
    """Standardized order request."""
    symbol: str
    side: str            # BUY or SELL
    order_type: str      # MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET
    quantity: float
    price: float = 0.0
    stop_price: float = 0.0
    reduce_only: bool = False
    position_side: str = "BOTH"  # BOTH, LONG, SHORT
    client_order_id: str = ""
    time_in_force: str = "GTC"


@dataclass
class OrderResult:
    """Result of an order API call."""
    symbol: str
    order_id: int
    client_order_id: str
    price: float
    orig_qty: float
    executed_qty: float
    status: str
    side: str
    order_type: str
    position_side: str
    avg_price: float
    update_time: int


@dataclass
class PositionInfo:
    """Position information from exchange."""
    symbol: str
    position_side: str
    quantity: float
    entry_price: float
    mark_price: float
    leverage: int
    liquidation_price: float
    unrealized_pnl: float
    margin_type: str = ""


@dataclass
class AccountInfo:
    """Account balance / margin info."""
    total_balance: float
    available_balance: float
    unrealized_pnl: float
    margin_ratio: float
    margin_type: str = ""


@dataclass
class HistoryOrder:
    """Historical order from exchange."""
    symbol: str
    order_id: int
    client_order_id: str
    side: str
    order_type: str
    status: str
    price: float
    orig_qty: float
    executed_qty: float
    avg_price: float
    cum_quote: float   # cumulative quote cost = SUM(fill_price * fill_qty)
    stop_price: float
    time: int          # ms
    update_time: int   # ms
    position_side: str
    reduce_only: bool

    @classmethod
    def from_ws(cls, raw: dict) -> "HistoryOrder":
        return cls(
            symbol=raw.get("symbol", ""),
            order_id=int(raw.get("orderId", 0)),
            client_order_id=raw.get("clientOrderId", ""),
            side=raw.get("side", ""),
            order_type=raw.get("type", ""),
            status=raw.get("status", ""),
            price=float(raw.get("price", 0)),
            orig_qty=float(raw.get("origQty", 0)),
            executed_qty=float(raw.get("executedQty", 0)),
            avg_price=float(raw.get("avgPrice", 0)),
            cum_quote=float(raw.get("cumQuote", 0)),
            stop_price=float(raw.get("stopPrice", 0)),
            time=int(raw.get("time", 0)),
            update_time=int(raw.get("updateTime", 0)),
            position_side=raw.get("positionSide", "BOTH"),
            reduce_only=raw.get("reduceOnly", False),
        )


@dataclass
class HistoryTrade:
    """Historical trade/fill from exchange."""
    symbol: str
    order_id: int
    trade_id: int
    side: str
    price: float
    qty: float
    commission: float
    commission_asset: str
    realized_pnl: float
    time: int         # ms
    position_side: str
    buyer: bool

    @classmethod
    def from_ws(cls, raw: dict) -> "HistoryTrade":
        return cls(
            symbol=raw.get("symbol", ""),
            order_id=int(raw.get("orderId", 0)),
            trade_id=int(raw.get("id", 0)),
            side=raw.get("side", ""),
            price=float(raw.get("price", 0)),
            qty=float(raw.get("qty", 0)),
            commission=float(raw.get("commission", 0)),
            commission_asset=raw.get("commissionAsset", ""),
            realized_pnl=float(raw.get("realizedPnl", 0)),
            time=int(raw.get("time", 0)),
            position_side=raw.get("positionSide", "BOTH"),
            buyer=raw.get("buyer", False),
        )


@dataclass
class IncomeEntry:
    """PnL income entry from Binance income history."""
    symbol: str
    income_type: str        # REALIZED_PNL, COMMISSION, FUNDING_FEE, etc.
    income: float
    asset: str
    info: str              # trade summary
    time: int              # ms
    trade_id: int

    @classmethod
    def from_ws(cls, raw: dict) -> "IncomeEntry":
        return cls(
            symbol=raw.get("symbol", ""),
            income_type=raw.get("incomeType", ""),
            income=float(raw.get("income", 0)),
            asset=raw.get("asset", ""),
            info=raw.get("info", ""),
            time=int(raw.get("time", 0)),
            trade_id=int(raw.get("tranId", 0)),
        )


class OrderExecutor:
    """Async wrapper around Binance REST API for trading."""

    def __init__(
        self,
        config: AppConfig,
        api_key: str,
        api_secret: str,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._config = config
        self._api_key = api_key
        self._api_secret = api_secret
        self._rate_limiter = rate_limiter or RateLimiter(
            max_weight=config.order.rate_limit_weight_per_minute
        )
        self._base_url = self._build_base_url()
        self._symbol_info: dict[str, dict] = {}
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise OrderError("OrderExecutor not started. Call initialize() first.")
        return self._client

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def initialize(self) -> None:
        """Create HTTP client and load exchange info."""
        client_kwargs: dict = {
            "base_url": self._base_url,
            "timeout": httpx.Timeout(30.0),
            "headers": {"X-MBX-APIKEY": self._api_key},
        }
        proxy_cfg = self._config.proxy
        if proxy_cfg.enabled and proxy_cfg.https:
            client_kwargs["proxy"] = proxy_cfg.https
            logger.info(f"已启用代理: {proxy_cfg.https}")

        self._client = httpx.AsyncClient(**client_kwargs)
        await self._load_exchange_info()
        logger.info(f"OrderExecutor 已初始化 ({self._base_url})")

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ----------------------------------------------------------------
    # Public API — orders
    # ----------------------------------------------------------------

    async def create_order(self, req: OrderRequest) -> OrderResult:
        """Submit a new order. Validates precision before sending.

        STOP_MARKET/TAKE_PROFIT_MARKET/STOP/TAKE_PROFIT/TRAILING_STOP_MARKET
        路由到 Binance Algo Order API (POST /fapi/v1/algoOrder).
        """
        filters = self._symbol_info.get(req.symbol)
        if filters:
            step = filters["step_size"]
            tick = filters["tick_size"]
            req = OrderRequest(
                symbol=req.symbol,
                side=req.side,
                order_type=req.order_type,
                quantity=clamp_qty(req.quantity, step, filters.get("min_qty", 0), filters["max_qty"]),
                price=clamp_price(req.price, tick),
                stop_price=clamp_price(req.stop_price, tick) if req.stop_price else 0.0,
                reduce_only=req.reduce_only,
                position_side=req.position_side,
                client_order_id=req.client_order_id or _make_client_id(),
                time_in_force=req.time_in_force if req.order_type == "LIMIT" else "GTC",
            )

        is_algo = req.order_type in ("STOP_MARKET", "STOP", "TAKE_PROFIT_MARKET", "TAKE_PROFIT", "TRAILING_STOP_MARKET")
        if is_algo:
            params = {
                "algoType": "CONDITIONAL",
                "symbol": req.symbol,
                "side": req.side,
                "type": req.order_type,
                "quantity": str(req.quantity),
                "triggerPrice": str(req.stop_price) if req.stop_price else "0",
                "workingType": "MARK_PRICE",
                "clientAlgoId": req.client_order_id,
            }
            if req.position_side and req.position_side != "BOTH":
                params["positionSide"] = req.position_side
            if req.order_type == "TRAILING_STOP_MARKET":
                params.pop("triggerPrice", None)
            raw = await self._signed_request("POST", "/fapi/v1/algoOrder", params)
        else:
            params = self._build_order_params(req, is_algo=False)
            raw = await self._signed_request("POST", self._order_endpoint(), params)
        return self._parse_order_result(raw)

    async def cancel_order(self, symbol: str, order_id: str | int, is_algo: bool = False) -> bool:
        """Cancel an open order by order ID. Set is_algo=True for algo orders."""
        if is_algo:
            params = {"symbol": symbol, "algoId": str(order_id)}
            endpoint = "/fapi/v1/algoOrder"
        else:
            params = {
                "symbol": symbol,
                "origClientOrderId": str(order_id) if not str(order_id).isdigit() else "",
                "orderId": str(order_id) if str(order_id).isdigit() else "",
            }
            endpoint = self._order_endpoint()
        try:
            await self._signed_request("DELETE", endpoint, params)
            return True
        except OrderError:
            return False

    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders (regular + algo) for a symbol."""
        try:
            await self._signed_request("DELETE", self._all_open_orders_endpoint(), {"symbol": symbol})
        except OrderError:
            pass
        try:
            await self._signed_request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": symbol})
        except OrderError:
            pass
        return True

    async def create_sl_tp_orders(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        stop_price: float,
        take_profit_price: float,
    ) -> list[OrderResult]:
        """Submit both a stop-loss and take-profit order for a position.

        Both orders have reduceOnly=True so they close the position
        without opening an opposing one. Submitted in parallel.

        Returns list of [stop_loss_result, take_profit_result].
        """
        import asyncio as aio

        close_side = "SELL" if position_side == "LONG" else "BUY"

        sl_req = OrderRequest(
            symbol=symbol,
            side=close_side,
            order_type="STOP_MARKET",
            quantity=quantity,
            stop_price=stop_price,
            reduce_only=True,
            position_side=position_side,
            client_order_id=_make_client_id("sl"),
        )

        tp_req = OrderRequest(
            symbol=symbol,
            side=close_side,
            order_type="TAKE_PROFIT_MARKET",
            quantity=quantity,
            stop_price=take_profit_price,
            reduce_only=True,
            position_side=position_side,
            client_order_id=_make_client_id("tp"),
        )

        results = await aio.gather(
            self.create_order(sl_req),
            self.create_order(tp_req),
            return_exceptions=True,
        )

        failed = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                failed.append((i, r))

        if failed:
            # 部分成功 → 回滚已成功的订单
            logger.error(f"SL/TP 部分失败: {failed}, 回滚已成功订单...")
            for i, r in enumerate(results):
                if not isinstance(r, Exception) and r.order_id:
                    try:
                        await self.cancel_order(symbol, r.client_order_id)
                    except Exception:
                        logger.warning(f"回滚取消失败: {r.client_order_id}")
            first_err = failed[0][1]
            raise OrderError(f"Failed to place SL/TP order: {first_err}") from first_err

        logger.info(
            f"SL/TP 已提交 {symbol}: SL={stop_price:.4f} TP={take_profit_price:.4f} 数量={quantity}"
        )
        return list(results)

    async def create_oco_order(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        stop_price: float,
        take_profit_price: float,
        stop_limit_price: float = 0.0,
    ) -> dict:
        """Submit a native OCO (One-Cancels-the-Other) order.

        Creates a pair: limit order at TP price + stop-market at SL price.
        When one executes, the exchange automatically cancels the other.
        Only available for Binance futures.

        POST /fapi/v1/order/oco
        """
        close_side = "SELL" if position_side == "LONG" else "BUY"

        # 精度处理 (与 create_order 保持一致)
        filters = self._symbol_info.get(symbol)
        if filters:
            step = filters["step_size"]
            tick = filters["tick_size"]
            quantity = clamp_qty(quantity, step, filters.get("min_qty", 0), filters["max_qty"])
            take_profit_price = clamp_price(take_profit_price, tick)
            stop_price = clamp_price(stop_price, tick)
            stop_limit_price = clamp_price(stop_limit_price, tick)

        params: dict = {
            "symbol": symbol,
            "side": close_side,
            "quantity": str(quantity),
            "price": str(take_profit_price),     # TP limit price
            "stopPrice": str(stop_price),         # SL trigger price
            "stopLimitPrice": str(stop_limit_price or stop_price),  # SL execution price
            "stopLimitTimeInForce": "GTC",
            "reduceOnly": "true",
            "newClientOrderId": _make_client_id("oco_tp"),
            "stopClientOrderId": _make_client_id("oco_sl"),
            "listClientOrderId": _make_client_id("oco"),
        }
        if position_side != "BOTH":
            params["positionSide"] = position_side

        raw = await self._signed_request("POST", "/fapi/v1/order/oco", params)

        logger.info(
            f"OCO 已提交 {symbol}: SL={stop_price:.4f} TP={take_profit_price:.4f} 数量={quantity}"
        )
        return raw

    async def create_protection_orders(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        stop_price: float,
        take_profit_price: float,
        use_oco: bool = True,
    ) -> list[OrderResult] | dict:
        """Place protection orders (SL+TP), preferring OCO for futures.

        If use_oco is True and trading_type is futures, uses the native OCO endpoint.
        Otherwise falls back to two separate orders submitted in parallel.
        """
        if use_oco and self._config.exchange.trading_type == "futures":
            return await self.create_oco_order(
                symbol=symbol,
                position_side=position_side,
                quantity=quantity,
                stop_price=stop_price,
                take_profit_price=take_profit_price,
            )

        return await self.create_sl_tp_orders(
            symbol=symbol,
            position_side=position_side,
            quantity=quantity,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
        )

    async def create_algo_order(self, req: OrderRequest) -> OrderResult:
        """Submit an ALGO order (CONDITIONAL) via REST /fapi/v1/algo/order.

        Used for STOP_MARKET / TAKE_PROFIT_MARKET stop-loss placements
        that Binance requires to go through the algo order endpoint.
        """
        filters = self._symbol_info.get(req.symbol)
        if filters:
            step = filters["step_size"]
            tick = filters["tick_size"]
            req = OrderRequest(
                symbol=req.symbol,
                side=req.side,
                order_type=req.order_type,
                quantity=clamp_qty(req.quantity, step, filters.get("min_qty", 0), filters["max_qty"]),
                stop_price=clamp_price(req.stop_price, tick) if req.stop_price else 0.0,
                reduce_only=req.reduce_only,
                position_side=req.position_side,
                client_order_id=req.client_order_id or _make_client_id(),
            )
        params: dict = {
            "symbol": req.symbol,
            "side": req.side,
            "type": req.order_type,
            "quantity": str(req.quantity),
            "algoType": "CONDITIONAL",
            "newOrderRespType": "RESULT",
        }
        if req.position_side and req.position_side != "BOTH":
            params["positionSide"] = req.position_side
        if req.stop_price > 0:
            params["stopPrice"] = str(req.stop_price)
            params["workingType"] = "MARK_PRICE"
        if req.reduce_only:
            params["reduceOnly"] = "true"
        raw = await self._signed_request("POST", "/fapi/v1/algo/order", params)
        result = OrderResult(
            symbol=raw.get("symbol", req.symbol),
            order_id=int(raw.get("algoId", raw.get("orderId", 0))),
            client_order_id=raw.get("clientAlgoId", req.client_order_id),
            price=float(raw.get("price", 0) or 0),
            orig_qty=float(raw.get("origQty", req.quantity)),
            executed_qty=float(raw.get("executedQty", 0)),
            status=raw.get("algoStatus", raw.get("status", "NEW")),
            side=raw.get("side", req.side),
            order_type=raw.get("type", req.order_type),
            position_side=raw.get("positionSide", req.position_side),
            avg_price=float(raw.get("avgPrice", 0) or 0),
            update_time=raw.get("updateTime", 0),
        )
        logger.info(
            f"Algo订单已提交: {req.symbol} {req.order_type} @{req.stop_price} "
            f"qty={req.quantity} id={result.order_id}"
        )
        return result

    async def create_three_tier_tp(
        self,
        symbol: str,
        position_side: str,
        total_qty: float,
        entry_price: float,
        tp1_pct: float = 3.0,
        tp2_pct: float = 6.0,
        tp3_pct: float = 10.0,
    ) -> tuple[list[OrderResult], int]:
        """三级分批止盈: TP1(30%) / TP2(30%) / TP3(40%).

        crypto_sword 经典分批止盈:
          TP1: 30%仓位 @ 入场价+3%
          TP2: 30%仓位 @ 入场价+6%
          TP3: 40%仓位 @ 入场价+10%

        全部 reduceOnly=true, 互不影响.
        """
        import asyncio as aio

        close_side = "SELL" if position_side == "LONG" else "BUY"

        # 计算 TP 价格
        if position_side == "LONG":
            tp1_price = entry_price * (1 + tp1_pct / 100)
            tp2_price = entry_price * (1 + tp2_pct / 100)
            tp3_price = entry_price * (1 + tp3_pct / 100)
        else:
            tp1_price = entry_price * (1 - tp1_pct / 100)
            tp2_price = entry_price * (1 - tp2_pct / 100)
            tp3_price = entry_price * (1 - tp3_pct / 100)

        # 分批数量
        qty1 = total_qty * 0.30
        qty2 = total_qty * 0.30
        qty3 = total_qty * 0.40

        filters = self._symbol_info.get(symbol)
        if filters:
            tick = filters["tick_size"]
            step = filters["step_size"]
            qty1 = clamp_qty(qty1, step, filters.get("min_qty", 0), filters["max_qty"])
            qty2 = clamp_qty(qty2, step, filters.get("min_qty", 0), filters["max_qty"])
            qty3 = clamp_qty(qty3, step, filters.get("min_qty", 0), filters["max_qty"])
            tp1_price = clamp_price(tp1_price, tick)
            tp2_price = clamp_price(tp2_price, tick)
            tp3_price = clamp_price(tp3_price, tick)

        reqs = [
            OrderRequest(
                symbol=symbol, side=close_side, order_type="LIMIT",
                quantity=qty1, price=tp1_price, reduce_only=True,
                position_side=position_side,
                client_order_id=_make_client_id("tp1"),
                time_in_force="GTC",
            ),
            OrderRequest(
                symbol=symbol, side=close_side, order_type="LIMIT",
                quantity=qty2, price=tp2_price, reduce_only=True,
                position_side=position_side,
                client_order_id=_make_client_id("tp2"),
                time_in_force="GTC",
            ),
            OrderRequest(
                symbol=symbol, side=close_side, order_type="LIMIT",
                quantity=qty3, price=tp3_price, reduce_only=True,
                position_side=position_side,
                client_order_id=_make_client_id("tp3"),
                time_in_force="GTC",
            ),
        ]

        results = await aio.gather(
            self.create_order(reqs[0]),
            self.create_order(reqs[1]),
            self.create_order(reqs[2]),
            return_exceptions=True,
        )

        valid = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"TP{i+1} 下单失败: {r}")
            else:
                valid.append(r)

        failed_count = len(results) - len(valid)
        logger.info(
            f"三级止盈已提交 {symbol}: "
            f"TP1=30%@{tp1_price:.4f} TP2=30%@{tp2_price:.4f} TP3=40%@{tp3_price:.4f} "
            f"[成功={len(valid)} 失败={failed_count}]"
        )
        return valid, failed_count

    async def get_order(self, symbol: str, client_order_id: str) -> OrderResult:
        """Query an order by client order ID."""
        params = {
            "symbol": symbol,
            "origClientOrderId": client_order_id,
        }
        raw = await self._signed_request("GET", self._order_endpoint(), params)
        return self._parse_order_result(raw)

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderResult]:
        """Get all open orders, optionally filtered by symbol."""
        params: dict = {}
        if symbol:
            params["symbol"] = symbol
        raw_orders = await self._signed_request("GET", self._open_orders_endpoint(), params)
        return [self._parse_order_result(o) for o in raw_orders]

    async def get_open_algo_orders(self, symbol: str | None = None) -> list[dict]:
        """Get all open algo orders (SL/TP conditional orders)."""
        params: dict = {}
        if symbol:
            params["symbol"] = symbol
        raw = await self._signed_request("GET", "/fapi/v1/openAlgoOrders", params)
        if not isinstance(raw, list):
            return []
        return raw

    # ----------------------------------------------------------------
    # Public API — positions / account
    # ----------------------------------------------------------------

    async def get_position_info(self, symbol: str | None = None) -> list[PositionInfo]:
        """Get open positions."""
        params: dict = {}
        if symbol:
            params["symbol"] = symbol
        raw = await self._signed_request("GET", self._position_endpoint(), params)
        if isinstance(raw, dict):
            raw = [raw]
        return [self._parse_position(p) for p in raw if float(p.get("positionAmt", 0)) != 0]

    async def get_account_info(self) -> AccountInfo:
        """Get account balance and margin info."""
        raw = await self._signed_request("GET", self._account_endpoint(), {})
        return AccountInfo(
            total_balance=float(raw.get("totalWalletBalance", raw.get("totalMarginBalance", 0))),
            available_balance=float(raw.get("availableBalance", 0)),
            unrealized_pnl=float(raw.get("totalUnrealizedProfit", raw.get("unrealizedPnl", 0))),
            margin_ratio=float(raw.get("marginRatio", 0)),
            margin_type=raw.get("marginType", ""),
        )

    # ---- 历史数据拉取 ----

    async def get_order_history(
        self, symbol: str, start_time: int | None = None,
        end_time: int | None = None, limit: int = 500,
    ) -> list[HistoryOrder]:
        """拉取历史订单 (包含已成交/已取消)."""
        params: dict = {"symbol": symbol, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        raw = await self._signed_request("GET", "/fapi/v1/allOrders", params)
        if not isinstance(raw, list):
            return []
        return [HistoryOrder.from_ws(r) for r in raw]

    async def get_trade_history(
        self, symbol: str, start_time: int | None = None,
        end_time: int | None = None, limit: int = 500,
    ) -> list[HistoryTrade]:
        """拉取历史成交 (userTrades)."""
        params: dict = {"symbol": symbol, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        raw = await self._signed_request("GET", "/fapi/v1/userTrades", params)
        if not isinstance(raw, list):
            return []
        return [HistoryTrade.from_ws(r) for r in raw]

    async def get_income_history(
        self, symbol: str | None = None, start_time: int | None = None,
        end_time: int | None = None, limit: int = 500,
        income_type: str | None = None,
    ) -> list[IncomeEntry]:
        """拉取盈亏流水 (income). income_type: REALIZED_PNL, COMMISSION, FUNDING_FEE, etc."""
        params: dict = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if income_type:
            params["incomeType"] = income_type
        raw = await self._signed_request("GET", "/fapi/v1/income", params)
        if not isinstance(raw, list):
            return []
        return [IncomeEntry.from_ws(r) for r in raw]

    async def set_leverage(self, symbol: str, leverage: int) -> dict:
        """Set leverage for a symbol (futures only)."""
        params = {"symbol": symbol, "leverage": leverage}
        return await self._signed_request("POST", "/fapi/v1/leverage", params)

    async def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> dict:
        """Set margin type (ISOLATED / CROSSED)."""
        params = {"symbol": symbol, "marginType": margin_type}
        return await self._signed_request("POST", "/fapi/v1/marginType", params)

    # ----------------------------------------------------------------
    # Internal — HTTP
    # ----------------------------------------------------------------

    async def _signed_request(self, method: str, path: str, params: dict) -> dict | list:
        """Send a signed request to the Binance API with retry on transient errors."""
        import asyncio as aio
        RETRIABLE_CODES = {-1015, -1016, -1021}  # -1003(限流/封IP)不重试,避免升级为Ban
        MAX_RETRIES = 3
        BASE_DELAY = 1.0

        for attempt in range(MAX_RETRIES + 1):
            params["timestamp"] = utc_timestamp_ms()
            params["recvWindow"] = 5000

            # Build signature
            query = urllib.parse.urlencode(sorted(params.items()), quote_via=urllib.parse.quote)
            signature = hmac.new(
                self._api_secret.encode("utf-8"),
                query.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            query += f"&signature={signature}"

            await self._rate_limiter.acquire_with_wait()

            try:
                if method == "GET":
                    resp = await self.client.get(f"{path}?{query}")
                elif method == "POST":
                    resp = await self.client.post(f"{path}?{query}")
                elif method == "DELETE":
                    resp = await self.client.delete(f"{path}?{query}")
                else:
                    raise OrderError(f"Unsupported HTTP method: {method}")
            except httpx.RequestError as exc:
                if attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2 ** attempt)
                    logger.warning(f"网络错误 (尝试 {attempt+1}/{MAX_RETRIES+1}): {exc}, {delay:.1f}s 后重试...")
                    await aio.sleep(delay)
                    continue
                raise OrderError(f"HTTP request failed after {MAX_RETRIES+1} attempts: {exc}") from exc

            data = resp.json()
            if resp.status_code >= 400:
                code = data.get("code", resp.status_code)
                msg = data.get("msg", str(data))

                if code == -2010:
                    raise InsufficientBalance(f"Insufficient balance: {msg}")
                if code in RETRIABLE_CODES and attempt < MAX_RETRIES:
                    delay = BASE_DELAY * (2 ** attempt)
                    logger.warning(f"Binance 瞬时错误 [{code}] (尝试 {attempt+1}/{MAX_RETRIES+1}): {msg}, {delay:.1f}s 后重试...")
                    await aio.sleep(delay)
                    continue
                if code == -1015:
                    raise RateLimitExceeded(f"Rate limit exceeded after retries: {msg}")

                raise OrderError(f"Binance error [{code}]: {msg}")

            return data

    async def _load_exchange_info(self) -> None:
        """Fetch and cache exchange info (symbol filters)."""
        endpoint = "/fapi/v1/exchangeInfo" if self._config.exchange.trading_type == "futures" else "/api/v3/exchangeInfo"
        resp = await self.client.get(endpoint)
        data = resp.json()

        for s in data.get("symbols", []):
            if s.get("status") == "TRADING":
                sym = s["symbol"]
                self._symbol_info[sym] = parse_symbol_filters(s.get("filters", []))

        logger.info(f"已加载 {len(self._symbol_info)} 个交易对信息")

    def get_symbol_filters(self, symbol: str) -> dict | None:
        """公开方法: 获取币种的交易精度过滤器 (step_size, tick_size 等)."""
        return self._symbol_info.get(symbol)

    async def get_ticker_price(self, symbol: str) -> float | None:
        """获取币种最新价 (公开端点, 无权重消耗)."""
        import httpx
        base = self._build_base_url()
        url = f"{base}/fapi/v1/ticker/price?symbol={symbol}"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    return float(data.get("price", 0))
        except Exception:
            pass
        return None

    async def get_position_mode(self) -> bool:
        """检测账户持仓模式: True=双向对冲, False=单向.
        调用 GET /fapi/v1/positionSide/dual (有签名)."""
        try:
            resp = await self._signed_request("GET", "/fapi/v1/positionSide/dual", {})
            return bool(resp.get("dualSidePosition", False))
        except Exception:
            logger.warning("获取持仓模式失败, 默认单向")
            return False

    # ----------------------------------------------------------------
    # Internal — URL selection
    # ----------------------------------------------------------------

    def _build_base_url(self) -> str:
        ex = self._config.exchange
        if ex.trading_type == "futures":
            return FUTURES_REST_TESTNET if ex.testnet else FUTURES_REST
        return SPOT_REST_TESTNET if ex.testnet else SPOT_REST

    def _order_endpoint(self) -> str:
        return "/fapi/v1/order" if self._config.exchange.trading_type == "futures" else "/api/v3/order"

    def _open_orders_endpoint(self) -> str:
        return "/fapi/v1/openOrders" if self._config.exchange.trading_type == "futures" else "/api/v3/openOrders"

    def _all_open_orders_endpoint(self) -> str:
        return "/fapi/v1/allOpenOrders" if self._config.exchange.trading_type == "futures" else "/api/v3/openOrders"

    def _position_endpoint(self) -> str:
        return "/fapi/v2/positionRisk" if self._config.exchange.trading_type == "futures" else "/api/v3/account"

    def _account_endpoint(self) -> str:
        return "/fapi/v2/account" if self._config.exchange.trading_type == "futures" else "/api/v3/account"

    # ----------------------------------------------------------------
    # Internal — Parsers
    # ----------------------------------------------------------------

    def _build_order_params(self, req: OrderRequest, is_algo: bool = False) -> dict:
        params = {
            "symbol": req.symbol,
            "side": req.side,
            "type": req.order_type,
            "quantity": str(req.quantity),
            "newClientOrderId": req.client_order_id,
        }
        if req.position_side and req.position_side != "BOTH" and self._config.exchange.trading_type == "futures":
            params["positionSide"] = req.position_side
        if req.order_type == "LIMIT":
            params["price"] = str(req.price)
            params["timeInForce"] = req.time_in_force
        if is_algo or req.order_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT"):
            params["stopPrice"] = str(req.stop_price)
            params["workingType"] = "MARK_PRICE"
        if req.reduce_only and not (req.position_side and req.position_side != "BOTH"):
            params["reduceOnly"] = "true"
        return params

    def _parse_order_result(self, raw: dict) -> OrderResult:
        # Algo orders use "algoId" + "clientAlgoId"; standard orders use "orderId" + "clientOrderId"
        is_algo = "algoId" in raw
        return OrderResult(
            symbol=raw["symbol"],
            order_id=raw.get("algoId") if is_algo else raw["orderId"],
            client_order_id=raw.get("clientAlgoId") if is_algo else raw.get("clientOrderId", ""),
            price=float(raw.get("price", 0) or 0),
            orig_qty=float(raw.get("origQty", 0)),
            executed_qty=float(raw.get("executedQty", 0)),
            status=raw.get("status", "NEW"),
            side=raw.get("side", ""),
            order_type=raw.get("type", ""),
            position_side=raw.get("positionSide", "BOTH"),
            avg_price=float(raw.get("avgPrice", 0) or 0),
            update_time=raw.get("updateTime", 0),
        )

    def _parse_position(self, raw: dict) -> PositionInfo:
        return PositionInfo(
            symbol=raw.get("symbol", ""),
            position_side=raw.get("positionSide", "BOTH"),
            quantity=float(raw.get("positionAmt", raw.get("quantity", 0))),
            entry_price=float(raw.get("entryPrice", 0) or 0),
            mark_price=float(raw.get("markPrice", 0) or 0),
            leverage=int(float(raw.get("leverage", 1))),
            liquidation_price=float(raw.get("liquidationPrice", 0) or 0),
            unrealized_pnl=float(raw.get("unRealizedProfit", raw.get("unrealizedPnl", 0))),
            margin_type=raw.get("marginType", ""),
        )


def _make_client_id(tag: str = "") -> str:
    """Generate a unique client order ID with optional tag (e.g. 'sl', 'tp')."""
    prefix = f"cp_{tag}_" if tag else "cp_"
    return f"{prefix}{utc_timestamp_ms()}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:6]}"
