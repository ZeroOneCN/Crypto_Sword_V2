"""Margin ratio and liquidation price monitor — background safety watchdog."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from loguru import logger


@dataclass
class MarginAlert:
    level: str          # INFO, WARNING, CRITICAL
    message: str
    symbol: str
    margin_ratio: float
    mark_price: float
    liquidation_price: float
    distance_pct: float  # how far from liquidation


class MarginMonitor:
    """Periodically checks account margin health and position liquidation risk.

    Runs as a background task. Emits alerts through a callback.
    When margin is critically high, triggers emergency position reduction.
    """

    def __init__(
        self,
        check_interval: float = 30.0,
        warning_threshold: float = 0.80,     # 80% margin ratio → warning
        critical_threshold: float = 0.90,    # 90% margin ratio → critical
        liq_distance_warning: float = 5.0,   # 5% from liquidation → warning
        liq_distance_critical: float = 2.0,  # 2% from liquidation → critical
    ) -> None:
        self._interval = check_interval
        self._warning = warning_threshold
        self._critical = critical_threshold
        self._liq_warn = liq_distance_warning
        self._liq_crit = liq_distance_critical
        self._running = False
        self._alert_callback = None  # async callable(MarginAlert)
        self._emergency_callback = None  # async callable() — triggered on critical

    def set_callbacks(self, alert_callback=None, emergency_callback=None) -> None:
        self._alert_callback = alert_callback
        self._emergency_callback = emergency_callback

    async def start(self, executor, position_manager, notifier=None) -> None:
        """Begin periodic monitoring. Blocks until stop() is called."""
        self._running = True
        logger.info(
            f"保证金监控已启动（间隔={self._interval}秒，"
            f"警告阈值={self._warning*100:.0f}%，危急阈值={self._critical*100:.0f}%）"
        )

        while self._running:
            try:
                await self._check(executor, position_manager, notifier)
            except Exception:
                logger.exception("保证金监控检查异常")
            await asyncio.sleep(self._interval)

    async def stop(self) -> None:
        self._running = False

    async def _check(self, executor, position_manager, notifier) -> None:
        """Run one health check cycle."""
        # Check account margin ratio
        try:
            acct = await executor.get_account_info()
        except Exception:
            logger.warning("保证金监控：获取账户信息失败")
            return

        margin_ratio = acct.margin_ratio
        if margin_ratio <= 0:
            return  # No open positions or spot mode

        # Overall margin check
        if margin_ratio >= self._critical:
            alert = MarginAlert(
                level="CRITICAL",
                message=(
                    f"危急：保证金比率 {margin_ratio*100:.1f}% 超过阈值 "
                    f"{self._critical*100:.0f}%，请立即减仓！"
                ),
                symbol="*",
                margin_ratio=margin_ratio,
                mark_price=0,
                liquidation_price=0,
                distance_pct=0,
            )
            self._do_alert(alert, notifier)
            if self._emergency_callback:
                try:
                    await self._emergency_callback()
                except Exception:
                    logger.exception("紧急回调执行失败")
            return
        elif margin_ratio >= self._warning:
            alert = MarginAlert(
                level="WARNING",
                message=f"保证金比率 {margin_ratio*100:.1f}% 超过警告阈值 {self._warning*100:.0f}%，请密切关注",
                symbol="*",
                margin_ratio=margin_ratio,
                mark_price=0,
                liquidation_price=0,
                distance_pct=0,
            )
            self._do_alert(alert, notifier)

        # Per-position liquidation distance check
        try:
            positions = await executor.get_position_info()
        except Exception:
            positions = []

        for pos in positions:
            if abs(pos.quantity) <= 0 or pos.liquidation_price <= 0:
                continue
            if pos.mark_price <= 0:
                continue

            # Calculate distance from liquidation as percentage
            if pos.position_side == "LONG":
                liq_distance = (pos.mark_price - pos.liquidation_price) / pos.mark_price * 100
            else:
                liq_distance = (pos.liquidation_price - pos.mark_price) / pos.mark_price * 100

            if liq_distance <= 0:
                level = "CRITICAL"
                msg = (
                    f"已爆仓或濒临爆仓：{pos.symbol} {pos.position_side} "
                    f"标记价={pos.mark_price:.4f} 强平价={pos.liquidation_price:.4f}"
                )
            elif liq_distance <= self._liq_crit:
                level = "CRITICAL"
                msg = (
                    f"危急：{pos.symbol} {pos.position_side} 距强平仅 "
                    f"{liq_distance:.1f}%！"
                    f"标记价={pos.mark_price:.4f} 强平价={pos.liquidation_price:.4f}"
                )
            elif liq_distance <= self._liq_warn:
                level = "WARNING"
                msg = (
                    f"警告：{pos.symbol} {pos.position_side} "
                    f"距强平 {liq_distance:.1f}% "
                    f"标记价={pos.mark_price:.4f} 强平价={pos.liquidation_price:.4f}"
                )
            else:
                continue  # Position is healthy

            alert = MarginAlert(
                level=level,
                message=msg,
                symbol=pos.symbol,
                margin_ratio=margin_ratio,
                mark_price=pos.mark_price,
                liquidation_price=pos.liquidation_price,
                distance_pct=liq_distance,
            )
            self._do_alert(alert, notifier)

    def _do_alert(self, alert: MarginAlert, notifier) -> None:
        """Log and optionally push the alert."""
        if alert.level == "CRITICAL":
            logger.error(alert.message)
        else:
            logger.warning(alert.message)

        if notifier and self._alert_callback:
            try:
                self._alert_callback(alert)
            except Exception:
                pass
