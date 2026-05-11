"""Configuration loading: .env secrets + config.yaml, merged via pydantic."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings

from cryptopilot.core.exceptions import ConfigError

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


# ----------------------------------------------------------------
# .env — secrets (never logged, never exposed)
# ----------------------------------------------------------------

class EnvSettings(BaseSettings):
    """Loaded from .env file. Keep this instance private."""

    binance_api_key: str = ""
    binance_api_secret: str = ""
    encryption_password: str = ""
    encryption_salt: str = "cryptopilot_salt"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_allowed_users: str = ""

    model_config = {"env_file": str(ROOT_DIR / ".env"), "extra": "ignore"}


# ----------------------------------------------------------------
# config.yaml — non-sensitive app configuration
# ----------------------------------------------------------------

class ProxyConfig(BaseModel):
    enabled: bool = False
    http: str = ""
    https: str = ""


class ExchangeConfig(BaseModel):
    testnet: bool = True
    trading_type: str = "futures"


class WebSocketConfig(BaseModel):
    streams: list[str] = Field(default_factory=lambda: ["kline_1m", "ticker"])
    reconnect_max_attempts: int = 100
    reconnect_base_delay: float = 1.0


class RiskConfig(BaseModel):
    max_daily_loss_pct: float = 2.0
    max_positions: int = 10
    max_position_pct: float = 20.0
    max_leverage: int = 10
    default_leverage: int = 3
    risk_per_trade: float = 1.5
    stop_loss_pct: float = 12.0
    take_profit_pct: float = 25.0
    trailing_distance_pct: float = 8.0
    trailing_activation_pct: float = 0.5


class TpTiersConfig(BaseModel):
    """Multi-tier take-profit configuration."""
    tp1_pct: float = 3.0
    tp2_pct: float = 6.0
    tp3_pct: float = 10.0
    tp1_ratio: float = 0.30
    tp2_ratio: float = 0.30
    tp3_ratio: float = 0.40
    breakeven_offset_pct: float = 0.5
    sideways_defense_minutes: float = 90.0
    sideways_exit_minutes: float = 180.0
    sideways_range_pct: float = 2.0
    pre_tp_guard_enabled: bool = True
    pre_tp_guard_min_roi_pct: float = 0.2


class ScoringConfig(BaseModel):
    """Multi-factor scoring engine configuration."""
    active_preset: str = "composite"
    buy_threshold: float = 50.0
    sell_threshold: float = -50.0
    min_confidence: float = 0.5
    scan_top_n: int = 100
    scan_interval_sec: int = 300
    tp_tiers: TpTiersConfig = Field(default_factory=TpTiersConfig)


class OrderConfig(BaseModel):
    default_type: str = "market"
    cancel_pending_on_stop: bool = True
    rate_limit_weight_per_minute: int = 1200


class NotificationConfig(BaseModel):
    telegram_enabled: bool = False


class LoggingConfig(BaseModel):
    level: str = "INFO"
    retention_days: int = 30


class WebConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 1688


class StrategyInstanceConfig(BaseModel):
    name: str
    enabled: bool = True
    symbol: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    order: OrderConfig = Field(default_factory=OrderConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    strategies: list[StrategyInstanceConfig] = Field(default_factory=list)


# ----------------------------------------------------------------
# Singletons
# ----------------------------------------------------------------

_env: EnvSettings | None = None
_app: AppConfig | None = None


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"config.yaml not found at {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def load_config(config_path: str | None = None) -> AppConfig:
    """Load .env and config.yaml, validate, return merged AppConfig."""
    global _env, _app

    _env = EnvSettings()

    yaml_path = Path(config_path) if config_path else (ROOT_DIR / "config.yaml")
    yaml_data = _load_yaml(yaml_path)

    try:
        _app = AppConfig(**yaml_data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config.yaml: {exc}") from exc

    return _app


def get_config() -> AppConfig:
    """Return cached AppConfig. Call load_config() first."""
    if _app is None:
        raise ConfigError("Config not loaded — call load_config() first")
    return _app


def get_env() -> EnvSettings:
    """Return cached EnvSettings. Call load_config() first."""
    if _env is None:
        raise ConfigError("Config not loaded — call load_config() first")
    return _env
