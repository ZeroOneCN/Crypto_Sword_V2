"""Telegram Bot — V2 宙斯交易中枢风格推送 (向V1看齐)."""

from __future__ import annotations

from loguru import logger

from cryptopilot.notification.notifier import EventData, Events

SEP = "━━━━━━━━━━━━━━━━━━━━"


def _fmt_pnl(pnl: float) -> str:
    """格式化盈亏, 带正负号."""
    return f"${pnl:+.2f}"


def _html_esc(s: str) -> str:
    """HTML 转义."""
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _hold_duration(seconds: float) -> str:
    """秒 → 人类可读时长."""
    if seconds < 60:
        return f"{int(seconds)}秒"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}分{s}秒"
    h, m = divmod(m, 60)
    return f"{h}小时{m}分"


def _score_label(score: float) -> str:
    """评分 → 置信度标签."""
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
    """评分可视化."""
    filled = min(int(score / 10), 10)
    return "█" * filled + "░" * (10 - filled)


def _side_emoji(side: str) -> str:
    """方向 → emoji."""
    s = (side or "").upper()
    return "📈 做多" if s == "LONG" else "📉 做空" if s == "SHORT" else "📊"


def _margin_label(mt: str) -> str:
    """保证金模式标签."""
    return "🔒 逐仓" if (mt or "").lower() == "isolated" else "🌐 全仓"


class TelegramBot:
    """V2 Telegram 机器人 — 宙斯交易中枢通知风格."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        allowed_users: list[str] | None = None,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._allowed_users = set(allowed_users or [])
        self._app: object | None = None
        self._running = False
        self._status_callback = None
        self._pause_callback = None
        self._resume_callback = None
        self._close_all_callback = None
        self._positions_callback = None

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
        if not self._token or not self._chat_id:
            logger.info("Telegram 未启用 (缺少 token/chat_id)")
            return
        try:
            import asyncio as _asyncio

            from telegram import Update
            from telegram.ext import Application, CommandHandler, ContextTypes
            from telegram.request import HTTPXRequest

            # Explicit timeouts to avoid hanging on slow connections
            # Default PTB timeouts (connect=5, read=5) can cause 10s+ stalls
            _request = HTTPXRequest(
                connect_timeout=8.0,
                read_timeout=8.0,
                write_timeout=8.0,
            )

            app = (
                Application.builder()
                .token(self._token)
                .request(_request)
                .build()
            )
            self._app = app

            async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                if not self._check_user(update):
                    return
                if self._status_callback:
                    r = self._status_callback()
                    if hasattr(r, '__await__'):
                        r = await r
                    await update.message.reply_text(str(r))

            async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                if not self._check_user(update):
                    return
                if self._positions_callback:
                    r = self._positions_callback()
                    if hasattr(r, '__await__'):
                        r = await r
                    await update.message.reply_text(str(r))

            async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                if not self._check_user(update):
                    return
                if self._pause_callback:
                    await self._pause_callback()
                await update.message.reply_text("⏸️ 策略已暂停")

            async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                if not self._check_user(update):
                    return
                if self._resume_callback:
                    await self._resume_callback()
                await update.message.reply_text("▶️ 策略已恢复")

            async def close_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                if not self._check_user(update):
                    return
                if self._close_all_callback:
                    await self._close_all_callback()
                await update.message.reply_text("🚨 紧急平仓已执行")

            async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                await update.message.reply_text(
                    "/status — 系统状态\n"
                    "/positions — 持仓明细\n"
                    "/pause — 暂停策略\n"
                    "/resume — 恢复策略\n"
                    "/close_all — 紧急平仓"
                )

            app.add_handler(CommandHandler("status", status))
            app.add_handler(CommandHandler("positions", positions))
            app.add_handler(CommandHandler("pause", pause))
            app.add_handler(CommandHandler("resume", resume))
            app.add_handler(CommandHandler("close_all", close_all))
            app.add_handler(CommandHandler("help", help_cmd))

            # Hard timeout for initialization — prevents hanging on network issues
            _INIT_TIMEOUT = 20.0  # generous but bounded
            try:
                await _asyncio.wait_for(app.initialize(), timeout=_INIT_TIMEOUT)
            except _asyncio.TimeoutError:
                logger.error(
                    f"Telegram 初始化超时 ({_INIT_TIMEOUT}s) — "
                    "网络到 api.telegram.org 可能不可达"
                )
                self._app = None
                return

            await app.start()
            self._running = True
            logger.info("Telegram Bot 已启动")

        except ImportError:
            logger.warning("python-telegram-bot 未安装 — Telegram 禁用")
        except Exception:
            logger.exception("Telegram Bot 启动失败")
            self._app = None
            self._running = False

    async def stop(self) -> None:
        if self._app and self._running:
            try:
                await self._app.stop()
                await self._app.shutdown()
            except Exception:
                pass
            self._running = False

    async def send_message(self, text: str) -> None:
        if not self._running or not self._app:
            return
        try:
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=text[:4096],
                parse_mode='HTML',
            )
        except Exception:
            logger.warning(f"Telegram 发送失败: {text[:100]}")

    def on_event(self, data: EventData) -> None:
        """处理 Notifier 事件 → 格式化 Telegram 消息."""
        if not self._running:
            return
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            msg = self._format_event(data)
            if msg:
                loop.create_task(self.send_message(msg))
        except RuntimeError:
            pass

    # ================================================================
    # 事件格式化 — V1 风格富文本
    # ================================================================

    def _format_event(self, data: EventData) -> str:
        """根据事件类型生成 Telegram 消息."""
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
        """开仓通知 - V1 风格."""
        side = _side_emoji(data.extra.get("side", "") if data.extra else "")
        now_str = data.message or ""
        symbol = _html_esc(data.symbol)
        lev = data.leverage or 1
        entry = data.price
        qty = data.quantity
        notional = entry * qty if entry > 0 and qty > 0 else 0

        parts = []
        # 标题
        parts.append(f"🟢 <b>宙斯交易中枢 | 开仓成功</b>")
        if now_str:
            parts.append(f"🕒 <code>{_html_esc(now_str)}</code>")
        parts.append("")
        parts.append(f"🔥 <b>{symbol}</b>｜{side}｜<code>{lev}x</code>")
        parts.append(SEP)

        # 入场 + 仓位
        parts.append(f"💵 <b>入场</b>: <code>{entry:.5f}</code>")
        parts.append(f"📦 <b>仓位</b>: <code>{qty}</code>｜名义 <code>{notional:.2f} USDT</code>")

        # 止损 + 止盈 (带预估盈亏)
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
                tp_pct = t.get("pct", 0)
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

        # 风险信息
        if data.extra:
            risk_usdt = data.extra.get("risk_usdt", 0)
            risk_pct = data.extra.get("risk_pct", 0)
            if risk_usdt > 0:
                parts.append(f"🎯 <b>风险</b>: <code>{risk_usdt:.2f} USDT</code>｜<code>{risk_pct:.2f}%</code>")

        # OI / Funding
        if data.extra:
            oi_pct = data.extra.get("oi_change_pct", 0)
            funding = data.extra.get("funding_rate", 0)
            oi_bonus = data.extra.get("oi_funding_bonus", 0)
            if oi_bonus or oi_pct or funding:
                bonus_str = f" | 加分 <code>+{oi_bonus}</code>" if oi_bonus else ""
                oi_str = f" | OI <code>{oi_pct:+.1f}%</code>" if oi_pct else ""
                funding_str = f" | Funding <code>{funding:+.4f}%</code>" if funding else ""
                parts.append(f"<b>OI/Funding</b> {bonus_str}{oi_str}{funding_str}")

        # 策略 + 评分
        if data.extra:
            strategy = data.extra.get("strategy_line", "")
            if strategy:
                parts.append(f"🧭 <b>策略</b>: <code>{_html_esc(str(strategy))}</code>")

        if data.score > 0:
            label = _score_label(data.score)
            bar = _score_bar(data.score)
            parts.append(f"⭐ <b>评分</b>: <code>{data.score:.0f}/100</code> {bar}｜{label}")

        # 开仓因子
        if data.top_factors and len(data.top_factors) > 0:
            factors = "、".join(data.top_factors[:3])
            parts.append(f"📊 <b>开仓理由</b>: {_html_esc(factors)}")

        # 分批止盈明细
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

        # 结尾
        parts.append(SEP)
        parts.append("✅ 已成交，保护单将同步确认")
        return "\n".join(parts)

    def _fmt_position_closed(self, data: EventData) -> str:
        """平仓通知 - V1 风格."""
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
        # 标题
        parts.append(f"{pnl_emoji} <b>宙斯交易中枢 | 平仓完成</b>")
        if data.message:
            parts.append(f"🕒 <code>{_html_esc(data.message)}</code>")
        parts.append("")
        parts.append(f"<b>{symbol}</b>｜{side}")
        parts.append(SEP)

        # 价格变动
        if entry_price > 0:
            parts.append(f"💵 <b>价格</b>: <code>{entry_price:.5f}</code> → <code>{exit_price:.5f}</code>")
            if side == "📈 做多":
                price_change = (exit_price - entry_price) / entry_price * 100
            else:
                price_change = (entry_price - exit_price) / entry_price * 100
            parts.append(f"📊 <b>价格涨幅</b>: <code>{price_change:+.2f}%</code>")
        else:
            parts.append(f"💵 <b>平仓价</b>: <code>{exit_price:.5f}</code>")

        # PnL
        parts.append(f"💰 <b>盈亏</b>: <b>{_fmt_pnl(pnl)} USDT</b>（<code>{pnl_pct:+.2f}%</code>）")

        # 平仓原因
        parts.append(f"📌 <b>原因</b>: <code>{reason_label}</code>")

        # ROI (如果有杠杆)
        if data.extra and data.extra.get("leverage", 0) > 0:
            lev = data.extra["leverage"]
            roi = pnl_pct * lev
            parts.append(f"🚀 <b>实际 ROI</b>: <code>{roi:+.2f}%</code>")

        # 持仓时长
        if hold_sec > 0:
            parts.append(f"⏱ <b>持仓</b>: {_hold_duration(hold_sec)}")

        # 策略
        if data.extra and data.extra.get("strategy_line"):
            parts.append(f"🧭 <b>策略</b>: <code>{_html_esc(str(data.extra['strategy_line']))}</code>")

        # 结尾
        parts.append(SEP)
        if pnl >= 0:
            parts.append("✅ 盈利离场，记录已入库")
        else:
            parts.append("🔴 亏损离场，等待复盘优化")

        return "\n".join(parts)

    def _fmt_protection_placed(self, data: EventData) -> str:
        """保护单放置通知."""
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
        """TP触发通知."""
        tier = data.extra.get("tier", "?") if data.extra else "?"
        return (
            f"🎯 <b>宙斯交易中枢 | TP{tier} 触发 · {_html_esc(data.symbol)}</b>\n"
            f"{SEP}\n"
            f"💵 触发价: <code>{data.exit_price:.5f}</code>\n"
            f"💰 已实现: <code>{_fmt_pnl(data.pnl)}</code>\n"
            f"📦 剩余仓位: <code>{data.extra.get('remaining_qty', 0) if data.extra else 0}</code>"
        )

    def _fmt_sl_triggered(self, data: EventData) -> str:
        """止损触发通知."""
        return (
            f"🛑 <b>宙斯交易中枢 | 止损触发 · {_html_esc(data.symbol)}</b>\n"
            f"{SEP}\n"
            f"💵 触发价: <code>{data.exit_price:.5f}</code>\n"
            f"💰 亏损: <code>{_fmt_pnl(data.pnl)}</code> ({data.pnl_pct:+.2f}%)"
        )

    # ================================================================
    # 工具函数
    # ================================================================

    def _exit_reason_label(self, reason: str) -> str:
        """平仓原因 → 中文标签."""
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

    def _check_user(self, update) -> bool:
        if not self._allowed_users:
            return True
        return update.effective_user.username in self._allowed_users
