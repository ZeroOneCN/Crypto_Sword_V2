"""真实流通市值因子 — 市值越小 → 爆发空间越大 → 得分越高.

connectfarm1 逻辑: <$50M 市值的币种最容易被庄家操控拉盘.
"""

from cryptopilot.strategy.factors.base import FactorBase, FactorScore
from cryptopilot.strategy.factors import register_factor
from cryptopilot.strategy.scanner import Candidate


class MarketCapFactor(FactorBase):
    """市值评分因子.

    市值 < $50M  → 满分 100
    市值 < $100M → 80 分
    市值 < $500M → 50 分
    市值 < $1B   → 30 分
    市值 > $1B   → 10 分
    """

    TIERS = [
        (50_000_000, 100),    # < $50M
        (100_000_000, 80),    # < $100M
        (200_000_000, 60),    # < $200M
        (500_000_000, 40),    # < $500M
        (1_000_000_000, 20),  # < $1B
    ]

    def __init__(self, name: str = "market_cap", weight: float = 0.25, **params) -> None:
        super().__init__(name, weight, **params)
        self._fetcher = None  # MarketCapFetcher, set externally

    def set_fetcher(self, fetcher) -> None:
        self._fetcher = fetcher

    def evaluate(self, candidate: Candidate, cache) -> FactorScore:
        mcap = 0.0
        if self._fetcher:
            mcap = self._fetcher.get_market_cap(candidate.symbol)

        if mcap <= 0:
            return self._make_score(30, "NEUTRAL", "市值数据暂无")

        score = 10  # default: large cap
        for threshold, s in self.TIERS:
            if mcap < threshold:
                score = s
                break

        direction = "LONG"  # 市值小 → 看好 (庄家容易拉盘)
        return self._make_score(score, direction, f"市值=${mcap:,.0f}")


register_factor("market_cap", MarketCapFactor)
