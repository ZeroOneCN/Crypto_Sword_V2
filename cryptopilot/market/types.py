"""Market data type definitions: Kline, Ticker, Depth, and stream messages."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class KlineData:
    """Single candlestick/kline from Binance WebSocket."""
    symbol: str
    interval: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    taker_buy_volume: float
    taker_buy_quote_volume: float
    is_final: bool
    received_at: float = field(default_factory=time.time)

    @classmethod
    def from_ws(cls, symbol: str, interval: str, k: dict) -> KlineData:
        """Parse from Binance WebSocket kline payload."""
        is_final = k.get("x", False)
        return cls(
            symbol=symbol,
            interval=interval,
            open_time=k["t"],
            close_time=k["T"],
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            quote_volume=float(k["q"]),
            taker_buy_volume=float(k["V"]),
            taker_buy_quote_volume=float(k["Q"]),
            is_final=is_final,
        )


@dataclass
class TickerData:
    """24hr ticker / mark price from Binance WebSocket."""
    symbol: str
    price: float
    price_change: float
    price_change_pct: float
    high_24h: float
    low_24h: float
    volume_24h: float
    quote_volume_24h: float
    event_time: int
    received_at: float = field(default_factory=time.time)

    @classmethod
    def from_ws(cls, data: dict) -> TickerData:
        """Parse from Binance WebSocket 24hr ticker / miniTicker payload.

        miniTicker 不含 "p"/"P" 字段, 从 open/close 计算.
        """
        price = float(data["c"])
        open_price = float(data.get("o", price))
        change = price - open_price
        change_pct = (change / open_price * 100) if open_price > 0 else 0.0
        return cls(
            symbol=data["s"],
            price=price,
            price_change=float(data.get("p", change)),
            price_change_pct=float(data.get("P", change_pct)),
            high_24h=float(data["h"]),
            low_24h=float(data["l"]),
            volume_24h=float(data["v"]),
            quote_volume_24h=float(data["q"]),
            event_time=data["E"],
        )


@dataclass
class DepthData:
    """Order book depth snapshot."""
    symbol: str
    bids: list[tuple[float, float]]  # (price, qty), descending
    asks: list[tuple[float, float]]  # (price, qty), ascending
    first_update_id: int
    last_update_id: int
    received_at: float = field(default_factory=time.time)

    @classmethod
    def from_ws(cls, data: dict) -> DepthData:
        """Parse from Binance WebSocket depth payload."""
        return cls(
            symbol=data["s"],
            bids=[(float(b[0]), float(b[1])) for b in data.get("b", [])],
            asks=[(float(a[0]), float(a[1])) for a in data.get("a", [])],
            first_update_id=data.get("U", 0),
            last_update_id=data.get("u", 0),
        )


@dataclass
class MarkPriceData:
    """标记价 + 资金费率 (markPrice@1s stream)."""
    symbol: str
    mark_price: float
    index_price: float
    funding_rate: float
    next_funding_time: int
    event_time: int
    received_at: float = field(default_factory=time.time)

    @classmethod
    def from_ws(cls, data: dict) -> MarkPriceData:
        return cls(
            symbol=data["s"],
            mark_price=float(data["p"]),
            index_price=float(data["i"]),
            funding_rate=float(data["r"]),
            next_funding_time=data["T"],
            event_time=data["E"],
        )


@dataclass
class OpenInterestData:
    """持仓量 (openInterest stream)."""
    symbol: str
    open_interest: float
    timestamp: int
    received_at: float = field(default_factory=time.time)

    @classmethod
    def from_ws(cls, data: dict) -> OpenInterestData:
        return cls(
            symbol=data["s"],
            open_interest=float(data["o"]),
            timestamp=data["E"],
        )


@dataclass
class LiquidationData:
    """强平订单 (!forceOrder@arr stream)."""
    symbol: str
    side: str               # BUY or SELL (哪方被强平)
    quantity: float
    price: float
    order_type: str          # LIMIT or MARKET
    event_time: int
    received_at: float = field(default_factory=time.time)

    @classmethod
    def from_ws(cls, data: dict) -> LiquidationData:
        o = data.get("o", {})
        return cls(
            symbol=o.get("s", ""),
            side=o.get("S", ""),
            quantity=float(o.get("q", 0)),
            price=float(o.get("p", 0)),
            order_type=o.get("o", ""),
            event_time=data.get("E", 0),
        )


@dataclass
class StreamMessage:
    """Wrapper for any incoming WebSocket message."""
    stream: str
    data: KlineData | TickerData | DepthData | MarkPriceData | OpenInterestData | LiquidationData
    received_at: float = field(default_factory=time.time)
