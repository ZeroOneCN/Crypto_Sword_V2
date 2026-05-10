"""Telegram Bot integration — push notifications and interactive commands."""

from __future__ import annotations

from loguru import logger

from cryptopilot.notification.notifier import EventData, Events


class TelegramBot:
    """Telegram bot for notifications and commands.

    Commands:
        /status    — Show strategy status summary
        /pause     — Pause all strategies
        /resume    — Resume all strategies
        /close_all — Emergency close all positions and cancel orders
        /positions — List open positions
        /help      — Show available commands

    Usage:
        bot = TelegramBot(token="...", chat_id="...", allowed_users=["user1"])
        notifier.register(Events.ORDER_FILLED, bot.on_event)
        await bot.start()
    """

    def __init__(
        self,
        token: str,
        chat_id: str,
        allowed_users: list[str] | None = None,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._allowed_users = set(allowed_users or [])
        self._app: object | None = None  # telegram.ext.Application
        self._running = False

        # Callbacks set after construction
        self._status_callback = None
        self._pause_callback = None
        self._resume_callback = None
        self._close_all_callback = None

    def set_callbacks(
        self,
        status_func=None,
        pause_func=None,
        resume_func=None,
        close_all_func=None,
    ) -> None:
        self._status_callback = status_func
        self._pause_callback = pause_func
        self._resume_callback = resume_func
        self._close_all_callback = close_all_func

    async def start(self) -> None:
        """Start the Telegram bot (non-blocking)."""
        if not self._token or not self._chat_id:
            logger.info("Telegram bot disabled (no token or chat_id)")
            return

        try:
            from telegram import Update
            from telegram.ext import (
                Application,
                CommandHandler,
                ContextTypes,
            )

            app = Application.builder().token(self._token).build()
            self._app = app

            async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                if not self._check_user(update):
                    return
                if self._status_callback:
                    result = await self._status_callback() if hasattr(self._status_callback, "__call__") else self._status_callback()
                    await update.message.reply_text(str(result) if not isinstance(result, str) else result)

            async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                if not self._check_user(update):
                    return
                if self._pause_callback:
                    await self._pause_callback()
                await update.message.reply_text("All strategies paused.")

            async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                if not self._check_user(update):
                    return
                if self._resume_callback:
                    await self._resume_callback()
                await update.message.reply_text("All strategies resumed.")

            async def close_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                if not self._check_user(update):
                    return
                if self._close_all_callback:
                    await self._close_all_callback()
                await update.message.reply_text("Emergency close executed.")

            async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
                msg = (
                    "/status — Strategy status\n"
                    "/positions — Open positions\n"
                    "/pause — Pause all\n"
                    "/resume — Resume all\n"
                    "/close_all — Emergency close all"
                )
                await update.message.reply_text(msg)

            app.add_handler(CommandHandler("status", status))
            app.add_handler(CommandHandler("pause", pause))
            app.add_handler(CommandHandler("resume", resume))
            app.add_handler(CommandHandler("close_all", close_all))
            app.add_handler(CommandHandler("help", help_cmd))

            await app.initialize()
            await app.start()
            self._running = True
            logger.info("Telegram bot started")

        except ImportError:
            logger.warning("python-telegram-bot not installed — Telegram disabled")
        except Exception:
            logger.exception("Failed to start Telegram bot")

    async def stop(self) -> None:
        if self._app and self._running:
            try:
                await self._app.stop()
                await self._app.shutdown()
            except Exception:
                pass
            self._running = False
            logger.info("Telegram bot stopped")

    async def send_message(self, text: str) -> None:
        """Send a text message to the configured chat_id."""
        if not self._running or not self._app:
            return
        try:
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=text[:4096],  # Telegram message limit
            )
        except Exception:
            logger.warning(f"Failed to send Telegram message: {text[:100]}")

    def on_event(self, data: EventData) -> None:
        """Handle incoming events from the Notifier. Fires send_message asynchronously."""
        if not self._running:
            return
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.send_message(data.message))
        except RuntimeError:
            pass

    def _check_user(self, update) -> bool:
        """Verify the user is allowed."""
        if not self._allowed_users:
            return True
        username = update.effective_user.username
        return username in self._allowed_users
