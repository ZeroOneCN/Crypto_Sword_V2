"""Sliding-window rate limiter for Binance API weight categories."""

from __future__ import annotations

import asyncio
import time
from collections import deque


class RateLimiter:
    """Token-bucket-like rate limiter based on a sliding window.

    Tracks (timestamp, weight) pairs and sleeps when the
    accumulated weight within the window exceeds the limit.
    """

    def __init__(self, max_weight: int = 1200, window_seconds: float = 60.0) -> None:
        self._max_weight = max_weight
        self._window = window_seconds
        self._entries: deque[tuple[float, int]] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self, weight: int = 1) -> None:
        """等待直到有足够容量, 然后消耗 `weight`."""
        await self.acquire_with_wait(weight)

    async def acquire_with_wait(self, weight: int = 1) -> float:
        """Wait if needed, return how long we waited (seconds)."""
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self._window
            while self._entries and self._entries[0][0] < cutoff:
                self._entries.popleft()

            current_weight = sum(w for _, w in self._entries)
            if current_weight + weight > self._max_weight and self._entries:
                wait_time = self._entries[0][0] + self._window - now + 0.1
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    now = time.monotonic()
                    cutoff = now - self._window
                    while self._entries and self._entries[0][0] < cutoff:
                        self._entries.popleft()

            self._entries.append((now, weight))
            return time.monotonic() - now

    @property
    def remaining(self) -> int:
        """Estimated remaining weight capacity in current window."""
        now = time.monotonic()
        cutoff = now - self._window
        current = sum(w for ts, w in self._entries if ts >= cutoff)
        return max(0, self._max_weight - current)
