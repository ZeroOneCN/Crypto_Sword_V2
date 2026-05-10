"""Exchange precision helpers — step size, tick size, notional clamping."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from cryptopilot.core.exceptions import InvalidPrecision


def round_step_size(value: float, step_size: float) -> float:
    """Round a quantity DOWN to the nearest valid step_size."""
    if step_size <= 0:
        return value
    v = Decimal(str(value))
    s = Decimal(str(step_size))
    result = (v // s) * s
    return float(result)


def round_tick_size(value: float, tick_size: float) -> float:
    """Round a price to the nearest valid tick_size."""
    if tick_size <= 0:
        return value
    v = Decimal(str(value))
    t = Decimal(str(tick_size))
    result = (v / t).quantize(Decimal("1"), rounding=ROUND_DOWN) * t
    return float(result)


def clamp_qty(
    qty: float,
    step_size: float,
    min_qty: float = 0,
    max_qty: float = float("inf"),
) -> float:
    """Round and clamp a quantity to exchange-allowed bounds."""
    qty = round_step_size(qty, step_size)
    if min_qty > 0 and qty < min_qty:
        raise InvalidPrecision(f"Quantity {qty} below minimum {min_qty}")
    if qty > max_qty:
        qty = round_step_size(max_qty, step_size)
    return qty


def clamp_price(price: float, tick_size: float) -> float:
    """Round a price to the tick_size."""
    return round_tick_size(price, tick_size)


def parse_symbol_filters(filters: list[dict]) -> dict[str, float]:
    """Extract PRICE_FILTER and LOT_SIZE from Binance exchange info filters.

    Returns dict with keys: tick_size, step_size, min_qty, max_qty, min_notional.
    """
    result = {
        "tick_size": 0.01,
        "step_size": 0.001,
        "min_qty": 0.001,
        "max_qty": float("inf"),
        "min_notional": 5.0,
    }
    for f in filters:
        kind = f.get("filterType", "")
        if kind == "PRICE_FILTER":
            result["tick_size"] = float(f.get("tickSize", 0.01))
        elif kind == "LOT_SIZE":
            result["step_size"] = float(f.get("stepSize", 0.001))
            result["min_qty"] = float(f.get("minQty", 0.001))
            result["max_qty"] = float(f.get("maxQty", float("inf")))
        elif kind == "MIN_NOTIONAL":
            result["min_notional"] = float(f.get("notional", 5.0))
    return result
