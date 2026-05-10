"""可插拔多因子评分引擎 — 加载注册的因子, 对候选币种综合打分."""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import FACTOR_REGISTRY
from cryptopilot.strategy.scanner import Candidate

# 导入所有因子模块以触发 register_factor
import cryptopilot.strategy.factors.ma_factor          # noqa
import cryptopilot.strategy.factors.rsi_factor         # noqa
import cryptopilot.strategy.factors.bollinger_factor   # noqa
import cryptopilot.strategy.factors.oi_factor          # noqa
import cryptopilot.strategy.factors.funding_factor      # noqa
import cryptopilot.strategy.factors.dark_flow          # noqa
import cryptopilot.strategy.factors.sentiment_factor    # noqa
import cryptopilot.strategy.factors.volume_factor       # noqa
import cryptopilot.strategy.factors.anomaly_factor      # noqa
import cryptopilot.strategy.factors.market_cap_factor   # noqa
import cryptopilot.strategy.factors.sideways_factor     # noqa
import cryptopilot.strategy.factors.atr_factor          # noqa


@dataclass
class ScoreResult:
    """综合评分结果."""
    symbol: str
    direction: str               # LONG / SHORT / HOLD
    total_score: float           # 归一化到 [-100, 100]
    confidence: float            # 0-1
    factors: list[FactorScore] = field(default_factory=list)
    detail: str = ""


class ScoringEngine:
    """可插拔多因子评分引擎.

    从 FACTOR_REGISTRY 中加载启用的因子,
    对每个候选币种并行评估, 加权汇总输出方向+置信度.
    """

    def __init__(
        self,
        cache,
        buy_threshold: float = 50.0,
        sell_threshold: float = -50.0,
        min_confidence: float = 0.5,
    ) -> None:
        self._cache = cache
        self._buy_threshold = buy_threshold
        self._sell_threshold = sell_threshold
        self._min_confidence = min_confidence
        self._factors: list[FactorBase] = []

    def configure(self, factor_configs: list[dict]) -> None:
        """根据配置加载因子.

        factor_configs 格式:
        [
            {"name": "ma", "weight": 0.15, "params": {"fast": 7, "slow": 25}},
            {"name": "oi", "weight": 0.20},
            ...
        ]
        """
        self._factors = []
        for fc in factor_configs:
            name = fc["name"]
            weight = fc.get("weight", 0.1)
            params = fc.get("params", {})

            cls = FACTOR_REGISTRY.get(name)
            if cls is None:
                logger.warning(f"未知因子类型: {name}, 已跳过")
                continue

            factor = cls(name=name, weight=weight, **params)
            self._factors.append(factor)
            logger.info(f"因子已加载: {name} (权重={weight})")

    def score(self, candidate: Candidate) -> ScoreResult:
        """对候选币种执行全部因子评分, 汇总输出."""
        if not self._factors:
            return ScoreResult(
                symbol=candidate.symbol,
                direction="HOLD",
                total_score=0,
                confidence=0,
                detail="无可用因子",
            )

        factor_scores: list[FactorScore] = []
        for factor in self._factors:
            try:
                fs = factor.evaluate(candidate, self._cache)
                factor_scores.append(fs)
            except Exception:
                logger.exception(f"因子 {factor.name} 评分异常")
                factor_scores.append(FactorScore(
                    name=factor.name, score=0, weight=factor.weight,
                    weighted=0, direction="NEUTRAL", detail="异常"
                ))

        # 汇总
        total_weighted = sum(fs.weighted for fs in factor_scores)
        # 方向分数: LONG=正, SHORT=负
        directional_score = 0.0
        for fs in factor_scores:
            if fs.direction == "LONG":
                directional_score += fs.weighted
            elif fs.direction == "SHORT":
                directional_score -= fs.weighted

        # 归一化到 [-100, 100]
        # 只对有方向信号的因子做归一化, 避免被 NEUTRAL 因子稀释
        active_weight = sum(
            f.weight for fs, f in zip(factor_scores, self._factors)
            if fs.direction != "NEUTRAL"
        )
        if active_weight > 0:
            norm_score = (directional_score / active_weight)
        else:
            norm_score = 0

        direction = self._determine_direction(norm_score, factor_scores)

        # 均值回归过滤: 暴涨不做多, 暴跌不做空
        change_24h = getattr(candidate, "change_24h_pct", 0) or 0
        if direction == "LONG" and change_24h > 8.0:
            direction = "HOLD"
            norm_score = norm_score * 0.3  # 大跌后反弹才安全
        elif direction == "SHORT" and change_24h < -8.0:
            direction = "HOLD"
            norm_score = norm_score * 0.3

        confidence = self._calc_confidence(factor_scores, direction)

        best_factors = sorted(factor_scores, key=lambda f: f.score, reverse=True)[:3]
        detail_parts = [f"{f.name}={f.direction}" for f in best_factors]

        return ScoreResult(
            symbol=candidate.symbol,
            direction=direction,
            total_score=round(norm_score, 1),
            confidence=round(confidence, 2),
            factors=factor_scores,
            detail=f"{direction} (评分={norm_score:.1f}, 置信={confidence:.2f}, {', '.join(detail_parts)})",
        )

    def _determine_direction(self, score: float, factors: list[FactorScore]) -> str:
        if score >= self._buy_threshold:
            return "LONG"
        if score <= self._sell_threshold:
            return "SHORT"
        return "HOLD"

    def _calc_confidence(self, factors: list[FactorScore], direction: str) -> float:
        if direction == "HOLD":
            return 0.0
        effective = [f for f in factors if f.direction != "NEUTRAL" and f.score > 20]
        if not effective:
            return 0.1
        aligned = [f for f in effective if f.direction == direction]
        return round(len(aligned) / len(effective), 2)

    @property
    def factor_count(self) -> int:
        return len(self._factors)

    def factor_names(self) -> list[str]:
        return [f.name for f in self._factors]
