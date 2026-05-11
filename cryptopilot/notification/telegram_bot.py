"""Telegram Bot — V2 多因子风格推送."""

from __future__ import annotations

from loguru import logger

from cryptopilot.notification.notifier import EventData, Events


def _fmt_pnl(pnl: float) -> str:
    """格式化盈亏, 带正负号."""
    return f"${pnl:+.2f}"


def _fmt_duration(seconds: float) -> str:
    """秒数 → 人类可读时长."""
    if seconds < 60:
        return f"{int(seconds)}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


class TelegramBot:
    """V2 Telegram 机器人 — 多因子评分 · 三级止盈 · 漏斗扫描."""

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
            from telegram import Update
            from telegram.ext import Application, CommandHandler, ContextTypes

            app = Application.builder().token(self._token).build()
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

            await app.initialize()
            await app.start()
            self._running = True
            logger.info("Telegram Bot 已启动")

        except ImportError:
            logger.warning("python-telegram-bot 未安装 — Telegram 禁用")
        except Exception:
            logger.exception("Telegram Bot 启动失败")

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
    # 🆕 V2 事件格式化 — 多因子 · 三级止盈 · 漏斗风格
    # ================================================================

    def _format_event(self, data: EventData) -> str:
        """根据事件类型生成 V2 风格的 Telegram 消息."""
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
            return f"🚨 熔断触发\n日亏损 {data.loss_pct:.2f}% (${data.pnl:.2f})"
        elif event == Events.WARNING:
            return f"⚠️ {data.message}"
        elif event == Events.DAILY_REPORT:
            return data.message
        elif event == Events.ERROR:
            return f"❌ {data.message}"
        elif event == Events.STRATEGY_ERROR:
            return f"❌ {data.message}"
        else:
            return data.message

    def _fmt_position_opened(self, data: EventData) -> str:
        """开仓通知 — V2 多因子评分卡片."""
        direction = "📈 做多" if data.symbol else data.message
        # 使用 data 字段构建消息
        parts = []
        emoji = "🟢" if data.symbol else "📊"
        side_emoji = "📈" if data.symbol else ""
        
        # 标题行
        parts.append(f"{emoji} <b>CryptoPilot · 开仓</b>")
        parts.append(f"")
        parts.append(f"<b>{data.symbol}</b> · {self._side_label(data)} · {data.leverage}x · {self._margin_label(data.margin_type)}")
        parts.append(f"")
        
        # 成交信息
        parts.append(f"💰 入场: <code>{data.price:.5f}</code>")
        parts.append(f"📦 数量: <code>{data.quantity}</code>")
        if data.leverage:
            parts.append(f"⚡ 杠杆: <code>{data.leverage}x</code>")
        
        # V2 特色: 多因子评分
        if data.score > 0:
            score_bar = self._score_bar(data.score)
            parts.append(f"")
            parts.append(f"🎯 综合评分: <code>{data.score:.0f}</code> {score_bar}")
            if data.top_factors:
                factors = " · ".join(data.top_factors[:3])
                parts.append(f"📊 因子贡献: {factors}")
        
        # 保护单
        parts.append(f"")
        parts.append(f"🛡️ <b>保护单:</b>")
        if data.sl_price > 0:
            sl_pct = abs(data.sl_price - data.price) / data.price * 100
            parts.append(f"  🛑 SL: <code>{data.sl_price:.5f}</code> (-{sl_pct:.1f}%)")
        for t in data.tp_tiers:
            parts.append(f"  🎯 TP{t['tier']}: <code>{t['price']:.5f}</code> (+{t['pct']}% · {int(t['qty_ratio']*100)}%仓位)")

        return "\n".join(parts)

    def _fmt_position_closed(self, data: EventData) -> str:
        """平仓通知 — V2 盈亏卡片."""
        pnl_emoji = "🟢" if data.pnl >= 0 else "🔴"
        parts = []
        
        parts.append(f"{pnl_emoji} <b>CryptoPilot · 平仓</b>")
        parts.append(f"")
        parts.append(f"<b>{data.symbol}</b> · {self._exit_reason_label(data.exit_reason)}")
        parts.append(f"")
        parts.append(f"💵 平仓价: <code>{data.exit_price:.5f}</code>")
        parts.append(f"💰 盈亏: <code>{_fmt_pnl(data.pnl)}</code>")
        if data.pnl_pct != 0:
            parts.append(f"📊 收益率: <code>{data.pnl_pct:+.2f}%</code>")
        if data.hold_duration:
            parts.append(f"⏱️ 持仓: <code>{data.hold_duration}</code>")

        return "\n".join(parts)

    def _fmt_protection_placed(self, data: EventData) -> str:
        """保护单放置通知."""
        parts = [f"🛡️ <b>保护单就绪 · {data.symbol}</b>", ""]
        if data.sl_price > 0:
            parts.append(f"🛑 SL: <code>{data.sl_price:.5f}</code>")
        for t in data.tp_tiers:
            parts.append(f"🎯 TP{t['tier']}: <code>{t['price']:.5f}</code> (+{t['pct']}% · {int(t['qty_ratio']*100)}%仓位)")
        return "\n".join(parts)

    def _fmt_tp_triggered(self, data: EventData) -> str:
        """TP触发通知."""
        return (
            f"🎯 <b>TP{data.extra.get('tier', '?')} 触发 · {data.symbol}</b>\n"
            f"\n"
            f"💵 触发价: <code>{data.exit_price:.5f}</code>\n"
            f"💰 已实现: <code>{_fmt_pnl(data.pnl)}</code>\n"
            f"📦 剩余仓位: <code>{data.extra.get('remaining_qty', 0)}</code>"
        )

    def _fmt_sl_triggered(self, data: EventData) -> str:
        """止损触发通知."""
        return (
            f"🛑 <b>止损触发 · {data.symbol}</b>\n"
            f"\n"
            f"💵 触发价: <code>{data.exit_price:.5f}</code>\n"
            f"💰 亏损: <code>{_fmt_pnl(data.pnl)}</code> ({data.pnl_pct:+.2f}%)"
        )

    # ================================================================
    # 工具函数
    # ================================================================

    def _side_label(self, data: EventData) -> str:
        """从 extra 推断方向."""
        if data.extra and "side" in data.extra:
            return "📈 做多" if data.extra["side"] == "LONG" else "📉 做空"
        return ""

    def _margin_label(self, margin_type: str) -> str:
        """保证金模式标签."""
        return "🔒 逐仓" if margin_type.lower() == "isolated" else "🌐 全仓"

    def _exit_reason_label(self, reason: str) -> str:
        labels = {
            "TP1": "🎯 止盈1",
            "TP2": "🎯 止盈2",
            "TP3": "🎯 止盈3",
            "SL": "🛑 止损",
            "MANUAL": "👤 手动",
            "SIGNAL": "📡 信号",
        }
        return labels.get(reason, reason)

    def _score_bar(self, score: float) -> str:
        """评分可视化: ████░░ 风格."""
        filled = min(int(score / 10), 10)
        return "█" * filled + "░" * (10 - filled)

    def _check_user(self, update) -> bool:
        if not self._allowed_users:
            return True
        return update.effective_user.username in self._allowed_users
