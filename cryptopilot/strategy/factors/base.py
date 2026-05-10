"""Abstract base class for all scoring factors."""

from __future__ import annotations

import math
from collections import deque
from abc import ABC, abstractmethod
from dataclasses import dataclass

from cryptopilot.strategy.scanner import Candidate


@dataclass
class FactorScore:
    """单个因子的评分明细."""
    name: str
    score: float         # 0-100 (越高越强)
    weight: float        # 权重 (0-1)
    weighted: float      # score * weight
    direction: str       # LONG / SHORT / NEUTRAL
    detail: str = ""


class FactorBase(ABC):
    """所有评分因子的抽象基类.

    每个因子接收一个 Candidate (从扫描器得到),
    结合 MarketDataCache 中的历史数据,
    输出一个 FactorScore.
    """

    def __init__(self, name: str, weight: float = 0.1, **params) -> None:
        self.name = name
        self.weight = weight
        self.params = params

    @abstractmethod
    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        """对候选币种评分. 返回 FactorScore."""

    def _make_score(self, score: float, direction: str, detail: str = "") -> FactorScore:
        score = max(0.0, min(100.0, score))
        return FactorScore(
            name=self.name,
            score=round(score, 1),
            weight=self.weight,
            weighted=round(score * self.weight, 1),
            direction=direction,
            detail=detail,
        )

    # ---- Utilities for subclasses ----

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(v, hi))

    @staticmethod
    def _ma(values: list[float], period: int) -> float:
        if len(values) < period:
            return 0.0
        return sum(values[-period:]) / period

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)
