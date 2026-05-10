"""Loguru-based logging with rotation, retention, and trade audit log."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from cryptopilot.core.config import ROOT_DIR


def _scrub_secrets(record: dict) -> bool:
    """Filter out sensitive fields from log records."""
    msg = str(record.get("message", ""))
    sensitive = ("api_key", "api_secret", "secret", "token", "password")
    for keyword in sensitive:
        if keyword.lower() in msg.lower():
            record["message"] = "[REDACTED — sensitive data]"
    return True


def setup_logging(level: str = "INFO", retention_days: int = 30) -> None:
    """Initialize loguru with console + file sinks.

    Args:
        level: Minimum log level for console output.
        retention_days: How many days to keep log files.
    """
    logger.remove()

    log_dir = ROOT_DIR / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Console sink
    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <7}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        filter=_scrub_secrets,
    )

    # File sink — all events
    logger.add(
        log_dir / "cryptopilot_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",
        retention=f"{retention_days} days",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | "
            "{name}:{function}:{line} | {message}"
        ),
        filter=_scrub_secrets,
    )

    # Trade audit log — only trade-related events
    logger.add(
        log_dir / "trade_{time:YYYY-MM-DD}.log",
        level="INFO",
        rotation="00:00",
        retention=f"{retention_days} days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
        filter=lambda r: r["extra"].get("trade", False),
    )

    logger.info(f"日志已初始化 (级别={level}, 保留={retention_days}天)")
