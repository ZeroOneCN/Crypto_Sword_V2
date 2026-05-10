"""候选池 — 优先级队列, 容量上限, TTL 淘汰."""

from __future__ import annotations

import asyncio
import time
from heapq import heappush, heappop, heapify

from cryptopilot.strategy.scanner import Candidate


class CandidatePool:
    """按 scanner_score 降序维护的候选池.

    - 容量上限 max_size (默认 20)
    - 新候选到达时若池满且评分高于池底, 替换最低分
    - TTL 过期自动清理
    - 线程安全 (asyncio.Lock)
    """

    def __init__(self, max_size: int = 20, ttl_seconds: float = 60.0) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._heap: list[Candidate] = []  # 最小堆, 按 sort_key (负score)
        self._by_symbol: dict[str, Candidate] = {}
        self._lock = asyncio.Lock()

    async def push(self, candidate: Candidate) -> bool:
        """入池. 返回 True 表示成功入池."""
        async with self._lock:
            # 已有同币种候选 → 更新
            existing = self._by_symbol.get(candidate.symbol)
            if existing:
                if candidate.scanner_score > existing.scanner_score:
                    self._heap = [c for c in self._heap if c.symbol != candidate.symbol]
                    heapify(self._heap)
                else:
                    return False
            else:
                # 池满 → 替换池底最低分
                if len(self._heap) >= self._max_size:
                    if candidate.scanner_score > -self._heap[0].sort_key:
                        removed = heappop(self._heap)
                        self._by_symbol.pop(removed.symbol, None)
                    else:
                        return False

            heappush(self._heap, candidate)
            self._by_symbol[candidate.symbol] = candidate
            return True

    async def pop_top(self, k: int = 5) -> list[Candidate]:
        """取出评分最高的 K 个候选 (不移除)."""
        async with self._lock:
            self._expire()
            sorted_candidates = sorted(self._heap, key=lambda c: -c.sort_key)
            return sorted_candidates[:k]

    async def get_all(self) -> list[Candidate]:
        """返回全池快照 (按评分降序)."""
        async with self._lock:
            self._expire()
            return sorted(self._heap, key=lambda c: -c.sort_key)

    async def remove(self, symbol: str) -> bool:
        """从池中移除指定币种."""
        async with self._lock:
            if symbol in self._by_symbol:
                self._heap = [c for c in self._heap if c.symbol != symbol]
                heapify(self._heap)
                self._by_symbol.pop(symbol, None)
                return True
            return False

    @property
    def size(self) -> int:
        return len(self._heap)

    def _expire(self) -> None:
        """清理超过 TTL 的候选."""
        now = time.time()
        cutoff = now - self._ttl
        remaining = [c for c in self._heap if c.scraped_at >= cutoff]
        if len(remaining) != len(self._heap):
            removed = [c.symbol for c in self._heap if c.scraped_at < cutoff]
            for sym in removed:
                self._by_symbol.pop(sym, None)
            self._heap = remaining
            heapify(self._heap)
