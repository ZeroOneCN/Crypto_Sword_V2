"""Pluggable scoring factors for multi-factor strategy evaluation."""

from cryptopilot.strategy.factors.base import FactorBase

# Factor registry — populated by register() calls in each module
FACTOR_REGISTRY: dict[str, type[FactorBase]] = {}


def register_factor(name: str, cls: type[FactorBase]) -> None:
    FACTOR_REGISTRY[name] = cls


def get_factor(name: str) -> type[FactorBase] | None:
    return FACTOR_REGISTRY.get(name)
