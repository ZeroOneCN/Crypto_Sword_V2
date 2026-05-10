"""市值数据抓取 — CoinGecko 免费 API."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from loguru import logger

COINGECKO_API = "https://api.coingecko.com/api/v3"
CACHE_TTL = 3600  # 1 小时缓存


@dataclass
class MarketCapData:
    symbol: str
    market_cap: float       # USD
    circulating_supply: float
    current_price: float
    total_volume_24h: float
    fetched_at: float = 0.0


class MarketCapFetcher:
    """从 CoinGecko 免费 API 拉取市值排名.

    接口: GET /api/v3/coins/markets
    返回 Top-250 币种的市值/价格/成交量.
    """

    def __init__(self, proxy: str | None = None) -> None:
        self._cache: dict[str, MarketCapData] = {}
        self._last_fetch: float = 0.0
        self._proxy = proxy

    async def fetch_all(self) -> dict[str, MarketCapData]:
        """拉取 Top-250 市值数据."""
        now = time.time()
        if self._cache and (now - self._last_fetch) < CACHE_TTL:
            return self._cache

        client_kwargs: dict = {"base_url": COINGECKO_API, "timeout": 30.0}
        if self._proxy:
            client_kwargs["proxy"] = self._proxy

        all_coins = []
        # CoinGecko 每页最多 250，分两页拉 Top-500
        for page in [1, 2]:
            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    resp = await client.get(
                        "/coins/markets",
                        params={
                            "vs_currency": "usd",
                            "order": "market_cap_desc",
                            "per_page": 250,
                            "page": page,
                            "sparkline": "false",
                        },
                    )
                    if resp.status_code == 200:
                        all_coins.extend(resp.json())
                    else:
                        logger.warning(f"CoinGecko 分页 {page} 返回 {resp.status_code}")
                        break
            except Exception as exc:
                logger.warning(f"CoinGecko 分页 {page} 拉取失败: {exc}")
                break

        if not all_coins:
            return self._cache

        count = 0
        for coin in all_coins:
            sym = coin.get("symbol", "").upper()
            if not sym:
                continue
            try:
                self._cache[sym] = MarketCapData(
                    symbol=sym,
                    market_cap=float(coin.get("market_cap", 0)),
                    circulating_supply=float(coin.get("circulating_supply", 0)),
                    current_price=float(coin.get("current_price", 0)),
                    total_volume_24h=float(coin.get("total_volume", 0)),
                    fetched_at=now,
                )
                count += 1
            except (ValueError, TypeError):
                continue

        self._last_fetch = now
        logger.info(f"市值数据已更新: {count} 个币种 (CoinGecko)")

        return self._cache

    def get(self, symbol: str) -> MarketCapData | None:
        """按 symbol 查找 (例如 BTC → MarketCapData)."""
        return self._cache.get(symbol.upper())

    def get_market_cap(self, symbol: str) -> float:
        """获取市值 (USD), 自动处理 BTCUSDT → BTC 映射."""
        # 去除 USDT 后缀 (Binance 格式 → 通用格式)
        clean = symbol.upper().replace("USDT", "").replace("BUSD", "").replace("USDC", "")
        entry = self._cache.get(clean)
        return entry.market_cap if entry else 0.0
