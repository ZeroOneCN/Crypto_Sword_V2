"""Telegram Bot — V2 宙斯交易中枢风格推送 (raw httpx, no PTB dependency).

Uses direct httpx.AsyncClient calls to the Telegram Bot API for:
- sendMessage (all notifications)
- getUpdates (command polling for /status, /positions, etc.)

This completely avoids python-telegram-bot's complex initialization which
hangs on slow networks (~10s per API call).
"""

from __future__ import annotations

import asyncio
import json
from typing import Callable, Awaitable

import httpx
from loguru import logger

from cryptopilot.notification.notifier import EventData, Events

SEP = "━━━━━━━━━━━━━━━━━━━━"

# ── Telegram Bot API base URL ──────────────────────────────────────
API_BASE = "https://api.telegram.org"

# ── Timeouts: generous enough for slow networks, bounded to avoid hangs ──
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
POLL_TIMEOUT = 30  # long-poll timeout for getUpdates


# ═══════════════════════════════════════════════════════════════════
# Formatting helpers (unchanged from V1/V2 style)
# ═══════════════════════════════════════════════════════════════════

def _fmt_pnl(pnl: float) -> str:
    return f"${pnl:+.2f}"


def _html_esc(s: str) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _hold_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}秒"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}分{s}秒"
    h, m = divmod(m, 60)
    return f"{h}小时{m}分"


def _score_label(score: float) -> str:
    if score >= 90:
        return "王炸"
    elif score >= 75:
        return "极高"
    elif score >= 60:
        return "高"
    elif score >= 45:
        return "中"
    return "低"


def _score_bar(score: float) -> str:
    filled = min(int(score / 10), 10)
    return "█" * filled + "░" * (10 - filled)


def _side_emoji(side: str) -> str:
    s = (side or "").upper()
    return "📈 做多" if s == "LONG" else "📉 做空" if s == "SHORT" else "📊"


def _margin_label(mt: str) -> str:
    return "🔒 逐仓" if (mt or "").lower() == "isolated" else "🌐 全仓"


class TelegramBot:
    """V2 Telegram 机器人 — raw httpx, no PTB dependency."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        allowed_users: list[str] | None = None,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._allowed_users = set(allowed_users or [])
        self._running = False
        self._http: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task | None = None
        self._last_update_id: int = 0

        # Callbacks
        self._status_callback: Callable | None = None
        self._pause_callback: Callable | None = None
        self._resume_callback: Callable | None = None
        self._close_all_callback: Callable | None = None
        self._positions_callback: Callable | None = None

    # ── Public API ─────────────────────────────────────────────────

    def set_callbacks(
        self,
        status_func=None,
        pause_func=None,
        resume_func=None,
        close_all_func=None,
        positions_func=None,
    ) -> None:
        self._status_callback = status_func
        self._pause_callback = pause_func
        self._resume_callback = resume_func
        self._close_all_callback = close_all_func
        self._positions_callback = positions_func

    async def start(self) -> None:
        """Start the bot: create HTTP client, verify token, begin polling."""
        if not self._token or not self._chat_id:
            logger.info("Telegram 未启用 (缺少 token/chat_id)")
            return

        self._http = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

        try:
            # Verify the token works with a quick getMe
            ok, result = await self._api_call("getMe")
            if not ok:
                logger.error(f"Telegram getMe 失败: {result}")
                await self._http.aclose()
                self._http = None
                return
            bot_name = result.get("first_name", "?")
            logger.info(f"Telegram Bot 已验证: @{result.get('username', '?')} ({bot_name})")
        except Exception as exc:
            logger.error(f"Telegram getMe 异常: {exc}")
            await self._http.aclose()
            self._http = None
            return

        # Start command polling in background
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop(), name="tg_poll")
        logger.info("Telegram Bot 已启动 (httpx 模式, 命令轮询中)")

    async def stop(self) -> None:
        """Stop polling and close HTTP client."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self._http:
            await self._http.aclose()
            self._http = None
        logger.info("Telegram Bot 已停止")

    async def send_message(self, text: str) -> None:
        """Send an HTML-formatted message to the configured chat."""
        if not self._running or not self._http:
            return
        try:
            await self._api_call("sendMessage", {
                "chat_id": self._chat_id,
                "text": text[:4096],
                "parse_mode": "HTML",
            })
        except Exception:
            logger.warning(f"Telegram 发送失败: {text[:100]}")

    def on_event(self, data: EventData) -> None:
        """Handle Notifier event → format and send Telegram message."""
        if not self._running:
            return
        try:
            loop = asyncio.get_running_loop()
            msg = self._format_event(data)
            if msg:
                loop.create_task(self.send_message(msg))
        except RuntimeError:
            pass

    # ── Internal: Telegram API ─────────────────────────────────────

    async def _api_call(self, method: str, params: dict | None = None) -> tuple[bool, dict]:
        """Make a call to the Telegram Bot API. Returns (ok, result_json).

        Uses POST with form-encoded data (required by sendMessage and others).
        For parameterless calls like getMe, sends empty data.
        Also tries URL query params as fallback for GET-like methods.
        """
        if not self._http:
            return False, {"error": "no http client"}
        url = f"{API_BASE}/bot{self._token}/{method}"
        try:
            if params:
                # sendMessage and most methods require form-encoded data
                resp = await self._http.post(url, data=params)
            else:
                resp = await self._http.post(url)
            data = resp.json()
            return data.get("ok", False), data.get("result", data)
        except httpx.TimeoutException:
            logger.warning(f"Telegram API 超时: {method}")
            return False, {"error": "timeout"}
        except Exception as exc:
            logger.warning(f"Telegram API 异常: {method} - {exc}")
            return False, {"error": str(exc)}

    # ── Internal: Command Polling ──────────────────────────────────

    async def _poll_loop(self) -> None:
        """Long-poll getUpdates for command handling."""
        logger.debug("Telegram 命令轮询已启动")
        consecutive_errors = 0

        while self._running and self._http:
            try:
                params = {
                    "timeout": POLL_TIMEOUT,
                    "allowed_updates": ["message"],
                }
                if self._last_update_id > 0:
                    params["offset"] = self._last_update_id + 1

                ok, result = await self._api_call("getUpdates", params)
                if not ok:
                    consecutive_errors += 1
                    if consecutive_errors > 5:
                        logger.error("Telegram getUpdates 连续失败, 暂停轮询")
                        break
                    await asyncio.sleep(5)
                    continue

                consecutive_errors = 0
                updates = result if isinstance(result, list) else []
                for upd in updates:
                    update_id = upd.get("update_id", 0)
                    if update_id > self._last_update_id:
                        self._last_update_id = update_id
                    msg = upd.get("message") or upd.get("channel_post")
                    if msg:
                        await self._handle_message(msg)

            except asyncio.CancelledError:
                break
            except httpx.TimeoutException:
                # Long-poll timeout is expected — just loop
                consecutive_errors = 0
                continue
            except Exception:
                consecutive_errors += 1
                logger.exception("Telegram 轮询异常")
                await asyncio.sleep(min(consecutive_errors * 5, 60))

    async def _handle_message(self, msg: dict) -> None:
        """Parse and dispatch a command from a message."""
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not text.startswith("/"):
            return  # Only handle commands

        chat_id = str(msg.get("chat", {}).get("id", ""))
        from_user = msg.get("from", {})
        username = from_user.get("username", "")

        # Access control
        if self._allowed_users and username not in self._allowed_users:
            await self._send_to(chat_id, "⛔ 无权限")
            return

        command = text.split()[0].lower().split("@")[0]  # strip @botname

        if command == "/status" and self._status_callback:
            await self._invoke_and_reply(chat_id, self._status_callback)
        elif command == "/positions" and self._positions_callback:
            await self._invoke_and_reply(chat_id, self._positions_callback)
        elif command == "/pause" and self._pause_callback:
            await self._invoke_coro(self._pause_callback)
            await self._send_to(chat_id, "⏸️ 策略已暂停")
        elif command == "/resume" and self._resume_callback:
            await self._invoke_coro(self._resume_callback)
            await self._send_to(chat_id, "▶️ 策略已恢复")
        elif command == "/close_all" and self._close_all_callback:
            await self._invoke_coro(self._close_all_callback)
            await self._send_to(chat_id, "🚨 紧急平仓已执行")
        elif command == "/help":
            await self._send_to(chat_id, (
                "/status — 系统状态\n"
                "/positions — 持仓明细\n"
                "/pause — 暂停策略\n"
                "/resume — 恢复策略\n"
                "/close_all — 紧急平仓"
            ))

    async def _send_to(self, chat_id: str, text: str) -> None:
        """Send a message to a specific chat (for command replies)."""
        if self._http:
            await self._api_call("sendMessage", {
                "chat_id": chat_id,
                "text": text[:4096],
                "parse_mode": "HTML",
            })

    async def _invoke_and_reply(self, chat_id: str, func: Callable) -> None:
        """Invoke a callback and send the result to chat_id."""
        try:
            result = func()
            if hasattr(result, '__await__'):
                result = await result
            await self._send_to(chat_id, str(result))
        except Exception as exc:
            await self._send_to(chat_id, f"❌ 错误: {exc}")

    async def _invoke_coro(self, func: Callable) -> None:
        """Invoke a coroutine callback."""
        try:
            result = func()
            if hasattr(result, '__await__'):
                await result
        except Exception:
            logger.exception("命令执行异常")

    # ═══════════════════════════════════════════════════════════════
    # Event formatting (unchanged V1/V2 style)
    # ═══════════════════════════════════════════════════════════════

    def _format_event(self, data: EventData) -> str:
        event = data.event

        if event == Events.POSITION_OPENED:
            return self._fmt_position_opened(data)
        elif event == Events.POSITION_CLOSED:
            return self._fmt_position_closed(data)
        elif event == Events.PROTECTION_PLACED:
            return self._fmt_protection_placed(data)
        elif event == Events.TAKE_PROFIT_TRIGGERED:
            return self._fmt_tp_triggered(data)
        elif event == Events.STOP_LOSS_TRIGGERED:
            return self._fmt_sl_triggered(data)
        elif event == Events.CIRCUIT_BREAKER_ACTIVATED:
            return (
                f"🔴 <b>宙斯交易中枢 | 熔断触发</b>\n"
                f"🕒 <code>{data.message}</code>\n{SEP}\n"
                f"💰 日亏损: <code>{data.loss_pct:.2f}%</code> (${data.pnl:.2f})\n"
                f"{SEP}\n⚠️ 已暂停开仓，等待次日 UTC 0 点重置"
            )
        elif event == Events.DAILY_REPORT:
            return data.message
        elif event == Events.ERROR:
            return f"❌ <b>宙斯交易中枢 | 异常</b>\n{SEP}\n{_html_esc(data.message)}"
        elif event == Events.WARNING:
            return f"⚠️ <b>宙斯交易中枢 | 警告</b>\n{SEP}\n{_html_esc(data.message)}"
        elif event == Events.STRATEGY_ERROR:
            return f"❌ <b>宙斯交易中枢 | 策略异常</b>\n{SEP}\n{_html_esc(data.message)}"
        else:
            return data.message

    def _fmt_position_opened(self, data: EventData) -> str:
        side = _side_emoji(data.extra.get("side", "") if data.extra else "")
        now_str = data.message or ""
        symbol = _html_esc(data.symbol)
        lev = data.leverage or 1
        entry = data.price
        qty = data.quantity
        notional = entry * qty if entry > 0 and qty > 0 else 0

        parts = []
        parts.append(f"🟢 <b>宙斯交易中枢 | 开仓成功</b>")
        if now_str:
            parts.append(f"🕒 <code>{_html_esc(now_str)}</code>")
        parts.append("")
        parts.append(f"🔥 <b>{symbol}</b>｜{side}｜<code>{lev}x</code>")
        parts.append(SEP)
        parts.append(f"💵 <b>入场</b>: <code>{entry:.5f}</code>")
        parts.append(f"📦 <b>仓位</b>: <code>{qty}</code>｜名义 <code>{notional:.2f} USDT</code>")

        if data.sl_price > 0:
            sl_dist_pct = abs(data.sl_price - entry) / entry * 100 if entry > 0 else 0
            if side == "📈 做多":
                sl_est = (entry - data.sl_price) * qty if data.sl_price < entry else (data.sl_price - entry) * qty
            else:
                sl_est = (data.sl_price - entry) * qty if data.sl_price > entry else (entry - data.sl_price) * qty
            parts.append(f"🛑 <b>止损</b>: <code>{data.sl_price:.5f}</code>（{sl_dist_pct:.2f}%）｜预计 <code>-{abs(sl_est):.2f} USDT</code>")

        tp_total_pnl = 0
        if data.tp_tiers:
            for t in data.tp_tiers:
                tp_price = t.get("price", 0)
                if tp_price > 0 and qty > 0:
                    tier_qty_ratio = t.get("qty_ratio", 1.0)
                    tier_qty = qty * tier_qty_ratio
                    if side == "📈 做多":
                        tp_pnl = (tp_price - entry) * tier_qty
                    else:
                        tp_pnl = (entry - tp_price) * tier_qty
                    tp_total_pnl += tp_pnl
            if tp_total_pnl > 0:
                parts.append(f"💰 <b>预计止盈</b>: <code>+{tp_total_pnl:.2f} USDT</code>")

        if data.extra:
            risk_usdt = data.extra.get("risk_usdt", 0)
            risk_pct = data.extra.get("risk_pct", 0)
            if risk_usdt > 0:
                parts.append(f"🎯 <b>风险</b>: <code>{risk_usdt:.2f} USDT</code>｜<code>{risk_pct:.2f}%</code>")

        if data.extra:
            oi_pct = data.extra.get("oi_change_pct", 0)
            funding = data.extra.get("funding_rate", 0)
            oi_bonus = data.extra.get("oi_funding_bonus", 0)
            if oi_bonus or oi_pct or funding:
                bonus_str = f" | 加分 <code>+{oi_bonus}</code>" if oi_bonus else ""
                oi_str = f" | OI <code>{oi_pct:+.1f}%</code>" if oi_pct else ""
                funding_str = f" | Funding <code>{funding:+.4f}%</code>" if funding else ""
                parts.append(f"<b>OI/Funding</b> {bonus_str}{oi_str}{funding_str}")

        if data.extra:
            strategy = data.extra.get("strategy_line", "")
            if strategy:
                parts.append(f"🧭 <b>策略</b>: <code>{_html_esc(str(strategy))}</code>")

        if data.score > 0:
            label = _score_label(data.score)
            bar = _score_bar(data.score)
            parts.append(f"⭐ <b>评分</b>: <code>{data.score:.0f}/100</code> {bar}｜{label}")

        if data.top_factors and len(data.top_factors) > 0:
            factors = "、".join(data.top_factors[:3])
            parts.append(f"📊 <b>开仓理由</b>: {_html_esc(factors)}")

        if data.tp_tiers and len(data.tp_tiers) > 0:
            parts.append("")
            parts.append(f"📊 <b>分批止盈</b>")
            for t in data.tp_tiers:
                tp_price = t.get("price", 0)
                tp_pct = t.get("pct", 0)
                tier = t.get("tier", "?")
                qty_ratio = t.get("qty_ratio", 1.0)
                tier_qty = qty * qty_ratio if qty > 0 else 0
                if side == "📈 做多":
                    tp_pnl = (tp_price - entry) * tier_qty if tp_price > 0 and entry > 0 else 0
                else:
                    tp_pnl = (entry - tp_price) * tier_qty if tp_price > 0 and entry > 0 else 0
                parts.append(
                    f"TP{tier}: <code>+{tp_pct}%</code> → <code>{tp_price:.5f}</code> "
                    f"({int(qty_ratio*100)}% / {tier_qty:.3f}) | 预计 <code>+{tp_pnl:.2f} USDT</code>"
                )

        parts.append(SEP)
        parts.append("✅ 已成交，保护单将同步确认")
        return "\n".join(parts)

    def _fmt_position_closed(self, data: EventData) -> str:
        pnl_emoji = "🟢" if data.pnl >= 0 else "🔴"
        side = _side_emoji(data.extra.get("side", "") if data.extra else "")
        symbol = _html_esc(data.symbol)
        reason_label = self._exit_reason_label(data.exit_reason)

        entry_price = data.extra.get("entry_price", 0) if data.extra else 0
        exit_price = data.exit_price
        pnl = data.pnl
        pnl_pct = data.pnl_pct
        hold_sec = data.extra.get("hold_seconds", 0) if data.extra else 0

        parts = []
        parts.append(f"{pnl_emoji} <b>宙斯交易中枢 | 平仓完成</b>")
        if data.message:
            parts.append(f"🕒 <code>{_html_esc(data.message)}</code>")
        parts.append("")
        parts.append(f"<b>{symbol}</b>｜{side}")
        parts.append(SEP)

        if entry_price > 0:
            parts.append(f"💵 <b>价格</b>: <code>{entry_price:.5f}</code> → <code>{exit_price:.5f}</code>")
            if side == "📈 做多":
                price_change = (exit_price - entry_price) / entry_price * 100
            else:
                price_change = (entry_price - exit_price) / entry_price * 100
            parts.append(f"📊 <b>价格涨幅</b>: <code>{price_change:+.2f}%</code>")
        else:
            parts.append(f"💵 <b>平仓价</b>: <code>{exit_price:.5f}</code>")

        parts.append(f"💰 <b>盈亏</b>: <b>{_fmt_pnl(pnl)} USDT</b>（<code>{pnl_pct:+.2f}%</code>）")
        parts.append(f"📌 <b>原因</b>: <code>{reason_label}</code>")

        if data.extra and data.extra.get("leverage", 0) > 0:
            lev = data.extra["leverage"]
            roi = pnl_pct * lev
            parts.append(f"🚀 <b>实际 ROI</b>: <code>{roi:+.2f}%</code>")

        if hold_sec > 0:
            parts.append(f"⏱ <b>持仓</b>: {_hold_duration(hold_sec)}")
        elif data.hold_duration:
            parts.append(f"⏱ <b>持仓</b>: {_html_esc(data.hold_duration)}")

        if data.extra and data.extra.get("strategy_line"):
            parts.append(f"🧭 <b>策略</b>: <code>{_html_esc(str(data.extra['strategy_line']))}</code>")

        parts.append(SEP)
        if pnl >= 0:
            parts.append("✅ 盈利离场，记录已入库")
        else:
            parts.append("🔴 亏损离场，等待复盘优化")
        return "\n".join(parts)

    def _fmt_protection_placed(self, data: EventData) -> str:
        symbol = _html_esc(data.symbol)
        parts = [f"🛡️ <b>宙斯交易中枢 | 保护单就绪 · {symbol}</b>", SEP]
        if data.sl_price > 0:
            parts.append(f"🛑 SL: <code>{data.sl_price:.5f}</code>")
        for t in data.tp_tiers:
            parts.append(
                f"🎯 TP{t.get('tier','?')}: <code>{t.get('price',0):.5f}</code> "
                f"(+{t.get('pct',0)}% · {int(t.get('qty_ratio',1)*100)}%仓位)"
            )
        return "\n".join(parts)

    def _fmt_tp_triggered(self, data: EventData) -> str:
        tier = data.extra.get("tier", "?") if data.extra else "?"
        return (
            f"🎯 <b>宙斯交易中枢 | TP{tier} 触发 · {_html_esc(data.symbol)}</b>\n"
            f"{SEP}\n"
            f"💵 触发价: <code>{data.exit_price:.5f}</code>\n"
            f"💰 已实现: <code>{_fmt_pnl(data.pnl)}</code>\n"
            f"📦 剩余仓位: <code>{data.extra.get('remaining_qty', 0) if data.extra else 0}</code>"
        )

    def _fmt_sl_triggered(self, data: EventData) -> str:
        return (
            f"🛑 <b>宙斯交易中枢 | 止损触发 · {_html_esc(data.symbol)}</b>\n"
            f"{SEP}\n"
            f"💵 触发价: <code>{data.exit_price:.5f}</code>\n"
            f"💰 亏损: <code>{_fmt_pnl(data.pnl)}</code> ({data.pnl_pct:+.2f}%)"
        )

    def _exit_reason_label(self, reason: str) -> str:
        labels = {
            "TP1": "止盈1触发",
            "TP2": "止盈2触发",
            "TP3": "止盈3触发",
            "TP_HIT": "止盈触发",
            "SL": "止损触发",
            "SL_HIT": "止损触发",
            "MANUAL": "手动平仓",
            "SIGNAL": "信号平仓",
            "SIGNAL_CLOSE": "信号平仓",
            "MARKET_CLOSE": "市价平仓",
            "CIRCUIT_BREAKER": "熔断平仓",
            "EXCHANGE_REALIZED": "交易所已实现盈亏同步",
        }
        return labels.get(reason, reason)
