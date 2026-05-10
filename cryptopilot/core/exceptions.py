"""Custom exception hierarchy for CryptoPilot."""


class CryptoPilotError(Exception):
    """Base exception for all CryptoPilot errors."""


class ConfigError(CryptoPilotError):
    """Configuration loading or validation failure."""


class SecurityError(CryptoPilotError):
    """Encryption or decryption failure."""


class MarketDataError(CryptoPilotError):
    """WebSocket disconnection, data corruption."""


class StrategyError(CryptoPilotError):
    """Strategy execution crash."""


class OrderError(CryptoPilotError):
    """Base for order-related errors."""


class InsufficientBalance(OrderError):
    """Not enough balance to place order."""


class InvalidPrecision(OrderError):
    """Quantity or price does not meet exchange precision requirements."""


class RateLimitExceeded(OrderError):
    """Binance API rate limit exceeded."""


class RiskError(CryptoPilotError):
    """Circuit breaker triggered or position limit reached."""


class DatabaseError(CryptoPilotError):
    """Database operation failure."""
