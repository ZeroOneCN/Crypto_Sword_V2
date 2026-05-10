"""中央事件总线 — 将交易事件路由到所有通知渠道 (V2 多因子版)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from loguru import logger


class Events(str, Enum):
    """所有可通知事件类型."""
    # 交易事件
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    TAKE_PROFIT_TRIGGERED = "take_profit_triggered"
    TRAILING_STOP_ADJUSTED = "trailing_stop_adjusted"
    PROTECTION_PLACED = "protection_placed"       # 🆕 SL+三级TP 放置成功

    # 系统事件
    CIRCUIT_BREAKER_ACTIVATED = "circuit_breaker_activated"
    STRATEGY_STARTED = "strategy_started"
    STRATEGY_STOPPED = "strategy_stopped"
    STRATEGY_ERROR = "strategy_error"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    DAILY_REPORT = "daily_report"
    ERROR = "error"
    WARNING = "warning"


@dataclass
class EventData:
    """事件负载 — V2 多因子上下文.

    通用字段: event, message, symbol, strategy_id
    开仓专用: price, quantity, leverage, score, top_factors, sl_price, tp_tiers
    平仓专用: exit_price, pnl, pnl_pct, exit_reason, hold_duration
    """
    event: Events
    message: str = ""
    symbol: str = ""
    strategy_id: str = ""

    # 开仓
    price: float = 0.0
    quantity: float = 0.0
    leverage: int = 0
    score: float = 0.0                    # 综合评分
    top_factors: list[str] = field(default_factory=list)  # 前3贡献因子
    sl_price: float = 0.0
    tp_tiers: list[dict] = field(default_factory=list)    # [{pct, price, qty_ratio}]

    # 平仓
    exit_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0                  # 盈亏百分比
    exit_reason: str = ""                  # TP1/TP2/TP3/SL/MANUAL/SIGNAL
    hold_duration: str = ""                # 持仓时长 (如 "3h42m")

    # 熔断
    loss_pct: float = 0.0

    extra: dict | None = None


Handler = Callable[[EventData], None]


class Notifier:
    """中央事件分发器 — 多频道支持."""

    def __init__(self) -> None:
        self._handlers: dict[Events, list[Handler]] = {}

    def register(self, event: Events, handler: Handler) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def unregister(self, event: Events, handler: Handler) -> None:
        try:
            self._handlers.get(event, []).remove(handler)
        except ValueError:
            pass

    def notify(self, data: EventData) -> None:
        handlers = self._handlers.get(data.event, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception:
                logger.exception(f"通知处理错误: {data.event}")

    async def notify_async(self, data: EventData) -> None:
        handlers = self._handlers.get(data.event, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception:
                logger.exception(f"通知处理错误: {data.event}")

    # ================================================================
    # 🆕 V2 风格便利方法 — 携带多因子上下文
    # ================================================================

    def position_opened(
        self,
        symbol: str,
        side: str,
        price: float,
        qty: float,
        leverage: int = 0,
        score: float = 0.0,
        top_factors: list[str] | None = None,
        sl_price: float = 0.0,
        tp_tiers: list[dict] | None = None,
    ) -> None:
        """开仓通知 — V2 多因子评分+保护单."""
        direction = "📈 做多" if side == "LONG" else "📉 做空"
        factors_str = " · ".join(top_factors or [])
        self.notify(EventData(
            event=Events.POSITION_OPENED,
            message=f"{direction} {symbol} @{price:.4f}",
            symbol=symbol,
            price=price,
            quantity=qty,
            leverage=leverage,
            score=score,
            top_factors=top_factors or [],
            sl_price=sl_price,
            tp_tiers=tp_tiers or [],
        ))

    def position_closed(
        self,
        symbol: str,
        side: str,
        exit_price: float,
        pnl: float,
        pnl_pct: float = 0.0,
        exit_reason: str = "",
        hold_duration: str = "",
    ) -> None:
        """平仓通知 — 带上退出原因和持仓时长."""
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        reason_tag = f" [{exit_reason}]" if exit_reason else ""
        self.notify(EventData(
            event=Events.POSITION_CLOSED,
            message=f"{pnl_emoji} 平仓 {symbol} {exit_reason} PnL=${pnl:+.2f}",
            symbol=symbol,
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            hold_duration=hold_duration,
        ))

    def protection_placed(
        self,
        symbol: str,
        sl_price: float,
        sl_pct: float,
        tp_tiers: list[dict],
    ) -> None:
        """保护单放置成功通知 — SL + 三级TP."""
        tp_lines = []
        for t in tp_tiers:
            tp_lines.append(f"  TP{t['tier']} @{t['price']:.5f} (+{t['pct']}% · {int(t['qty_ratio']*100)}%仓位)")
        tp_text = "\n".join(tp_lines)
        self.notify(EventData(
            event=Events.PROTECTION_PLACED,
            message=f"🛡️ {symbol}\nSL @{sl_price:.5f} (-{sl_pct:.1f}%)\n{tp_text}",
            symbol=symbol,
            sl_price=sl_price,
            tp_tiers=tp_tiers,
        ))

    def tp_triggered(
        self,
        symbol: str,
        tier: int,
        price: float,
        pnl: float,
        remaining_qty: float,
    ) -> None:
        """止盈触发通知 — 标识触发级别."""
        self.notify(EventData(
            event=Events.TAKE_PROFIT_TRIGGERED,
            message=f"🎯 TP{tier} 触发 {symbol} @{price:.4f} PnL=${pnl:+.2f}",
            symbol=symbol,
            exit_price=price,
            pnl=pnl,
            exit_reason=f"TP{tier}",
            extra={"tier": tier, "remaining_qty": remaining_qty},
        ))

    def sl_triggered(
        self,
        symbol: str,
        price: float,
        pnl: float,
        pnl_pct: float,
    ) -> None:
        """止损触发通知."""
        self.notify(EventData(
            event=Events.STOP_LOSS_TRIGGERED,
            message=f"🛑 止损触发 {symbol} @{price:.4f} PnL=${pnl:+.2f} ({pnl_pct:+.2f}%)",
            symbol=symbol,
            exit_price=price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason="SL",
        ))

    # ---- 兼容旧接口 ----

    def order_filled(self, symbol: str, side: str, price: float, qty: float, **extra) -> None:
        self.notify(EventData(
            event=Events.ORDER_FILLED,
            message=f"✅ {side} {qty} {symbol} @{price:.4f}",
            symbol=symbol, price=price, quantity=qty,
            extra={"side": side, **extra},
        ))

    def circuit_breaker_activated(self, loss_pct: float, pnl: float) -> None:
        self.notify(EventData(
            event=Events.CIRCUIT_BREAKER_ACTIVATED,
            message=f"⚠️ 熔断触发: 日亏损 {loss_pct:.2f}% (${pnl:.2f})",
            loss_pct=loss_pct, pnl=pnl,
        ))

    def strategy_error(self, strategy_id: str, error: str) -> None:
        self.notify(EventData(
            event=Events.STRATEGY_ERROR,
            message=f"❌ 策略异常 '{strategy_id}': {error}",
            strategy_id=strategy_id,
        ))
