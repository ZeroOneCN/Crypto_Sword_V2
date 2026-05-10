"""Exit lifecycle manager — multi-tier TP, breakeven, trailing stop, sideways detection.

V1-style comprehensive exit management ported to V2 CryptoPilot async architecture.

Handles the full lifecycle:
  1. Multi-tier TP (3 levels: 30%/30%/40% ratios)
  2. Breakeven stop after TP1 fills
  3. Enhanced trailing stop with highest/lowest price tracking
  4. Sideways detection: tighten stop @ 90min, force exit @ 180min
  5. Pre-TP micro exit guard: block premature profit-taking
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from loguru import logger


# ----------------------------------------------------------------
# Enums & Dataclasses
# ----------------------------------------------------------------

class ExitAction(Enum):
    """Decision returned by ExitManager.evaluate()."""
    NO_OP = auto()                 # Nothing to do
    TAKE_PROFIT = auto()           # Fill one or more TP tiers
    MOVE_TO_BREAKEVEN = auto()     # Move stop to entry + offset
    TRAILING_UPDATE = auto()       # Trailing stop moved (log only)
    TIGHTEN_STOP = auto()          # Sideways defense: tighten stop
    FORCE_EXIT = auto()            # Sideways timeout: close position
    STOP_LOSS = auto()             # Stop-loss triggered


@dataclass
class ExitDecision:
    """Result of evaluating exit conditions for a position."""
    action: ExitAction = ExitAction.NO_OP
    symbol: str = ""
    side: str = "LONG"
    reason: str = ""
    # For TAKE_PROFIT: which tiers to fill
    tp_tiers_to_fill: list[int] = field(default_factory=list)
    tp_quantities: list[float] = field(default_factory=list)
    tp_prices: list[float] = field(default_factory=list)
    # For MOVE_TO_BREAKEVEN / TIGHTEN_STOP
    new_stop_price: float = 0.0
    # For FORCE_EXIT / STOP_LOSS
    exit_price: float = 0.0


@dataclass
class TpTierConfig:
    """Configuration for one take-profit tier."""
    level: int
    pct: float          # Price move % from entry
    ratio: float        # Fraction of position to close at this tier


# ----------------------------------------------------------------
# ExitManager
# ----------------------------------------------------------------

class ExitManager:
    """Manages the complete exit lifecycle for all open positions.

    Designed as a stateful service that tracks per-position exit state
    across evaluation cycles. Call evaluate() in your main loop for each
    open position.

    Usage in trading loop (e.g., main.py profit_lock_loop or similar)::

        exit_mgr = ExitManager(tp_config, executor, pm, notifier, cache)
        for pos in pm.get_all_positions():
            entry = pos["entry_price"]
            mark = pos["mark_price"]
            side = pos["side"]
            qty = abs(pos["qty"])

            decision = exit_mgr.evaluate(pos["symbol"], side, entry, mark, qty)
            await exit_mgr.execute(decision)
    """

    def __init__(
        self,
        tp_tiers: list[TpTierConfig] | None = None,
        breakeven_offset_pct: float = 0.5,
        trail_distance_pct: float = 1.5,
        trail_activation_pct: float = 0.5,
        sideways_defense_minutes: float = 90.0,
        sideways_exit_minutes: float = 180.0,
        sideways_range_pct: float = 2.0,
        pre_tp_guard_enabled: bool = True,
        pre_tp_guard_min_roi_pct: float = 0.2,
        *,
        executor=None,         # OrderExecutor (for placing orders)
        position_manager=None,  # PositionManager
        notifier=None,         # Notifier
        cache=None,            # MarketDataCache
    ) -> None:
        # ---- TP tier config ----
        self._tp_tiers = tp_tiers or [
            TpTierConfig(level=1, pct=3.0, ratio=0.30),
            TpTierConfig(level=2, pct=6.0, ratio=0.30),
            TpTierConfig(level=3, pct=10.0, ratio=0.40),
        ]
        # Sort by level
        self._tp_tiers.sort(key=lambda t: t.level)

        # ---- Breakeven ----
        self._breakeven_offset_pct = breakeven_offset_pct

        # ---- Trailing stop ----
        self._trail_distance_pct = trail_distance_pct
        self._trail_activation_pct = trail_activation_pct

        # ---- Sideways detection ----
        self._sideways_defense_minutes = sideways_defense_minutes
        self._sideways_exit_minutes = sideways_exit_minutes
        self._sideways_range_pct = sideways_range_pct

        # ---- Pre-TP guard ----
        self._pre_tp_guard_enabled = pre_tp_guard_enabled
        self._pre_tp_guard_min_roi = pre_tp_guard_min_roi_pct

        # ---- External dependencies ----
        self._executor = executor
        self._pm = position_manager
        self._notifier = notifier
        self._cache = cache

        # ---- Per-position state ----
        self._tp_filled: dict[str, set[int]] = {}       # symbol -> filled tier levels
        self._highest_price: dict[str, float] = {}       # LONG positions
        self._lowest_price: dict[str, float] = {}        # SHORT positions
        self._entry_time: dict[str, float] = {}          # symbol -> entry timestamp
        self._breakeven_set: dict[str, bool] = {}
        self._sideways_defense_set: dict[str, bool] = {}
        self._trail_activated: dict[str, bool] = {}
        self._current_stop: dict[str, float] = {}        # current stop price

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def register_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        initial_stop: float = 0.0,
        *,
        leverage: int = 1,
    ) -> None:
        """Register a newly-opened position for exit tracking.

        Call this after a position is opened (in _execute_signal OPEN branch).
        """
        sym = symbol.upper()
        self._tp_filled[sym] = set()
        self._breakeven_set[sym] = False
        self._sideways_defense_set[sym] = False
        self._trail_activated[sym] = False
        self._entry_time[sym] = time.time()
        self._current_stop[sym] = initial_stop

        side_upper = side.upper()
        if side_upper in ("LONG", "BUY"):
            self._highest_price[sym] = entry_price
        else:
            self._lowest_price[sym] = entry_price

        logger.info(
            f"ExitManager 已注册: {sym} {side_upper} entry={entry_price:.4f} "
            f"qty={quantity} lev={leverage}x"
        )

    def unregister_position(self, symbol: str) -> None:
        """Clean up tracking when a position is fully closed."""
        sym = symbol.upper()
        self._tp_filled.pop(sym, None)
        self._highest_price.pop(sym, None)
        self._lowest_price.pop(sym, None)
        self._entry_time.pop(sym, None)
        self._breakeven_set.pop(sym, None)
        self._sideways_defense_set.pop(sym, None)
        self._trail_activated.pop(sym, None)
        self._current_stop.pop(sym, None)

    @staticmethod
    def calc_pnl_pct(entry: float, current: float, side: str) -> float:
        """Calculate unrealized PnL as percentage of entry."""
        if entry <= 0:
            return 0.0
        side_upper = side.upper()
        if side_upper in ("LONG", "BUY"):
            return (current - entry) / entry * 100
        return (entry - current) / entry * 100

    @staticmethod
    def calc_roi_pct(entry: float, current: float, side: str, leverage: int = 1) -> float:
        """Calculate ROI % (pnl_pct * leverage)."""
        return ExitManager.calc_pnl_pct(entry, current, side) * max(leverage, 1)

    def evaluate(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        quantity: float,
        *,
        leverage: int = 1,
        current_stop: float = 0.0,
    ) -> ExitDecision:
        """Evaluate all exit conditions for a position.

        Args:
            symbol: Trading symbol
            side: LONG / SHORT (or BUY / SELL)
            entry_price: Average entry price
            current_price: Current mark/market price
            quantity: Current position size (absolute value)
            leverage: Position leverage
            current_stop: Current exchange stop-loss price (if any)

        Returns:
            ExitDecision with the recommended action.
        """
        sym = symbol.upper()
        side_upper = side.upper()
        is_long = side_upper in ("LONG", "BUY")

        # Ensure position is registered (lazy init for existing positions)
        if sym not in self._entry_time:
            self.register_position(sym, side_upper, entry_price, quantity,
                                   initial_stop=current_stop, leverage=leverage)

        # Update current stop if provided
        if current_stop > 0:
            self._current_stop[sym] = current_stop

        # ---- 1. Stop-loss check ----
        if self._is_stop_triggered(sym, is_long, current_price, current_stop):
            return ExitDecision(
                action=ExitAction.STOP_LOSS,
                symbol=sym,
                side=side_upper,
                reason="STOP_LOSS",
                exit_price=current_price,
            )

        # ---- 2. Multi-tier TP check ----
        tp_decision = self._check_tp_tiers(sym, side_upper, entry_price, current_price, quantity)
        if tp_decision.action != ExitAction.NO_OP:
            return tp_decision

        # ---- 3. Breakeven check (after TP1 filled) ----
        if self._breakeven_set.get(sym, False):
            pass  # Already set, nothing more to do
        elif self._tp_filled.get(sym, set()):
            # TP1 has filled — move stop to breakeven+offset
            new_stop = self._calc_breakeven_stop(entry_price, is_long)
            self._breakeven_set[sym] = True
            return ExitDecision(
                action=ExitAction.MOVE_TO_BREAKEVEN,
                symbol=sym,
                side=side_upper,
                reason="BREAKEVEN_AFTER_TP1",
                new_stop_price=new_stop,
            )

        # ---- 4. Update price extremes for trailing ----
        if is_long:
            self._highest_price[sym] = max(self._highest_price.get(sym, entry_price), current_price)
        else:
            self._lowest_price[sym] = min(self._lowest_price.get(sym, entry_price), current_price)

        # ---- 5. Sideways detection ----
        sideways = self._check_sideways(sym, side_upper, entry_price, current_price)
        if sideways.action != ExitAction.NO_OP:
            return sideways

        # ---- 6. Trailing stop update ----
        trail = self._check_trailing_stop(sym, is_long, entry_price, current_price)
        if trail.action != ExitAction.NO_OP:
            return trail

        return ExitDecision(action=ExitAction.NO_OP)

    # ----------------------------------------------------------------
    # Decision Execution
    # ----------------------------------------------------------------

    async def execute(self, decision: ExitDecision) -> bool:
        """Execute the decided exit action. Returns True if action was taken."""
        if decision.action == ExitAction.NO_OP:
            return False

        sym = decision.symbol

        try:
            if decision.action == ExitAction.TAKE_PROFIT:
                await self._execute_take_profit(decision)
                return True

            elif decision.action == ExitAction.MOVE_TO_BREAKEVEN:
                await self._execute_move_stop(sym, decision.new_stop_price, decision.reason)
                return True

            elif decision.action == ExitAction.TIGHTEN_STOP:
                await self._execute_move_stop(sym, decision.new_stop_price, decision.reason)
                self._sideways_defense_set[sym] = True
                return True

            elif decision.action == ExitAction.FORCE_EXIT:
                await self._execute_force_exit(sym, decision.reason)
                return True

            elif decision.action == ExitAction.STOP_LOSS:
                await self._execute_force_exit(sym, decision.reason)
                return True

            elif decision.action == ExitAction.TRAILING_UPDATE:
                logger.info(
                    f"移动止损: {sym} 止损已更新至 {decision.new_stop_price:.4f} "
                    f"(原因: {decision.reason})"
                )
                return True

        except Exception:
            logger.exception(f"ExitManager 执行失败: {sym} action={decision.action.name}")

        return False

    # ----------------------------------------------------------------
    # Internal: TP Tiers
    # ----------------------------------------------------------------

    def _check_tp_tiers(
        self, symbol: str, side: str, entry: float, price: float, qty: float
    ) -> ExitDecision:
        """Check if any unfilled TP tiers have been reached."""
        filled = self._tp_filled.get(symbol, set())
        tiers_to_fill: list[int] = []
        quantities: list[float] = []
        prices: list[float] = []

        remaining_qty = qty
        for tier in self._tp_tiers:
            if tier.level in filled:
                continue

            # Calculate TP price for this tier
            tp_price = self._calc_tp_price(entry, tier.pct, side)

            # Check if price has reached this tier
            if self._price_reached(side, price, tp_price):
                tier_qty = qty * tier.ratio
                tiers_to_fill.append(tier.level)
                quantities.append(min(tier_qty, remaining_qty))
                prices.append(tp_price)
                remaining_qty -= tier_qty
                if remaining_qty <= 1e-8:
                    break

        if not tiers_to_fill:
            return ExitDecision(action=ExitAction.NO_OP)

        return ExitDecision(
            action=ExitAction.TAKE_PROFIT,
            symbol=symbol,
            side=side,
            reason=f"TP_TIERS_{','.join(str(t) for t in tiers_to_fill)}",
            tp_tiers_to_fill=tiers_to_fill,
            tp_quantities=quantities,
            tp_prices=prices,
        )

    def mark_tp_filled(self, symbol: str, tier: int) -> None:
        """Mark a TP tier as filled (call after exchange confirms fill)."""
        sym = symbol.upper()
        if sym not in self._tp_filled:
            self._tp_filled[sym] = set()
        self._tp_filled[sym].add(tier)
        logger.info(f"TP{tier} 已成交: {sym}")

    @property
    def tp_tiers_filled(self, symbol: str) -> int:
        """Number of TP tiers filled for a symbol."""
        return len(self._tp_filled.get(symbol.upper(), set()))

    # ----------------------------------------------------------------
    # Internal: Breakeven
    # ----------------------------------------------------------------

    def _calc_breakeven_stop(self, entry: float, is_long: bool) -> float:
        """Calculate breakeven stop price with offset."""
        if is_long:
            return entry * (1 + self._breakeven_offset_pct / 100)
        return entry * (1 - self._breakeven_offset_pct / 100)

    # ----------------------------------------------------------------
    # Internal: Trailing Stop
    # ----------------------------------------------------------------

    def _check_trailing_stop(
        self, symbol: str, is_long: bool, entry: float, price: float
    ) -> ExitDecision:
        """Update trailing stop if price has moved favorably."""
        sym = symbol

        # Check activation
        if not self._trail_activated.get(sym, False):
            if is_long:
                gain = (self._highest_price[sym] - entry) / entry * 100
            else:
                gain = (entry - self._lowest_price[sym]) / entry * 100

            if gain >= self._trail_activation_pct:
                self._trail_activated[sym] = True
                logger.info(f"移动止损已激活: {sym} (涨幅={gain:.2f}%)")
            else:
                return ExitDecision(action=ExitAction.NO_OP)

        # Calculate new stop
        if is_long:
            new_stop = self._highest_price[sym] * (1 - self._trail_distance_pct / 100)
        else:
            new_stop = self._lowest_price[sym] * (1 + self._trail_distance_pct / 100)

        # Only move stop in favorable direction
        old_stop = self._current_stop.get(sym, 0.0)
        if is_long:
            if new_stop <= old_stop:
                return ExitDecision(action=ExitAction.NO_OP)
        else:
            if new_stop >= old_stop:
                return ExitDecision(action=ExitAction.NO_OP)

        # Check if current price has already breached the new stop
        if self._is_stop_triggered(sym, is_long, price, new_stop):
            return ExitDecision(
                action=ExitAction.STOP_LOSS,
                symbol=sym,
                side="LONG" if is_long else "SHORT",
                reason="TRAILING_STOP",
                exit_price=price,
            )

        self._current_stop[sym] = new_stop
        return ExitDecision(
            action=ExitAction.TRAILING_UPDATE,
            symbol=sym,
            side="LONG" if is_long else "SHORT",
            reason="TRAILING_STOP",
            new_stop_price=new_stop,
        )

    # ----------------------------------------------------------------
    # Internal: Sideways Detection
    # ----------------------------------------------------------------

    def _check_sideways(
        self, symbol: str, side: str, entry: float, price: float
    ) -> ExitDecision:
        """Detect sideways/stuck positions and take defensive action."""
        sym = symbol

        age_minutes = (time.time() - self._entry_time.get(sym, time.time())) / 60.0

        # If we've already taken profit, skip sideways check
        if self._tp_filled.get(sym, set()):
            return ExitDecision(action=ExitAction.NO_OP)

        # Check if position has been in a narrow range
        is_long = side.upper() in ("LONG", "BUY")
        extreme = self._highest_price.get(sym) if is_long else self._lowest_price.get(sym)
        if extreme is None:
            return ExitDecision(action=ExitAction.NO_OP)

        # Calculate range from extreme to current
        if entry > 0:
            if is_long:
                range_pct = (extreme - min(price, entry)) / entry * 100
            else:
                range_pct = (max(price, entry) - extreme) / entry * 100
        else:
            range_pct = 100.0

        # ---- Sideways EXIT timeout ----
        if age_minutes >= self._sideways_exit_minutes:
            # Pre-TP guard: don't exit with a micro-profit unless SL is forced
            pnl_pct = self.calc_pnl_pct(entry, price, side)
            if self._pre_tp_guard_enabled:
                roi_pct = abs(pnl_pct)  # without leverage for guard check
                if roi_pct > self._pre_tp_guard_min_roi:
                    # Has small profit but hasn't reached TP1 — don't force exit,
                    # just tighten the stop to protect
                    if not self._sideways_defense_set.get(sym, False):
                        new_stop = self._calc_breakeven_stop(entry, is_long)
                        logger.warning(
                            f"横盘超时但盈利未达TP1: {sym} "
                            f"age={age_minutes:.0f}m pnl={pnl_pct:+.2f}% — 收紧止损"
                        )
                        return ExitDecision(
                            action=ExitAction.TIGHTEN_STOP,
                            symbol=sym,
                            side=side,
                            reason="SIDEWAYS_DEFENSE_MICRO_PROFIT",
                            new_stop_price=new_stop,
                        )

            # Force exit
            logger.warning(
                f"横盘超时退出: {sym} age={age_minutes:.0f}m "
                f"pnl={pnl_pct:+.2f}% range={range_pct:.2f}%"
            )
            return ExitDecision(
                action=ExitAction.FORCE_EXIT,
                symbol=sym,
                side=side,
                reason="SIDEWAYS_TIMEOUT",
                exit_price=price,
            )

        # ---- Sideways DEFENSE timeout ----
        if (age_minutes >= self._sideways_defense_minutes
                and range_pct <= self._sideways_range_pct
                and not self._sideways_defense_set.get(sym, False)):
            new_stop = self._calc_breakeven_stop(entry, is_long)
            logger.warning(
                f"横盘防守: {sym} age={age_minutes:.0f}m "
                f"range={range_pct:.2f}% — 止损收紧至 {new_stop:.4f}"
            )
            return ExitDecision(
                action=ExitAction.TIGHTEN_STOP,
                symbol=sym,
                side=side,
                reason="SIDEWAYS_DEFENSE",
                new_stop_price=new_stop,
            )

        return ExitDecision(action=ExitAction.NO_OP)

    # ----------------------------------------------------------------
    # Internal: Execution Helpers
    # ----------------------------------------------------------------

    async def _execute_take_profit(self, decision: ExitDecision) -> None:
        """Execute partial TP fills by placing market orders."""
        sym = decision.symbol
        is_long = decision.side.upper() in ("LONG", "BUY")
        close_side = "SELL" if is_long else "BUY"

        for i, tier in enumerate(decision.tp_tiers_to_fill):
            qty = decision.tp_quantities[i]
            if qty <= 1e-8:
                continue

            try:
                from cryptopilot.trading.order_executor import OrderRequest

                req = OrderRequest(
                    symbol=sym,
                    side=close_side,
                    order_type="MARKET",
                    quantity=qty,
                    reduce_only=True,
                    position_side="LONG" if is_long else "SHORT",
                )
                result = await self._executor.create_order(req)
                logger.info(
                    f"TP{tier} 执行: {sym} qty={qty:.4f} "
                    f"price={result.avg_price or result.price:.4f} status={result.status}"
                )
                self.mark_tp_filled(sym, tier)
            except Exception:
                logger.exception(f"TP{tier} 执行失败: {sym}")

        # Sync positions after fills
        if self._pm:
            await self._pm.sync_from_exchange(self._executor)

    async def _execute_move_stop(self, symbol: str, new_stop: float, reason: str) -> None:
        """Move the exchange stop-loss order to a new price."""
        sym = symbol

        # Cancel existing SL orders
        try:
            await self._executor.cancel_all_orders(sym)
        except Exception:
            logger.warning(f"撤销旧止损单失败: {sym}")

        # Get current position to determine side and quantity
        pos = self._pm.get_position(sym) if self._pm else None
        if not pos:
            logger.warning(f"无法找到持仓 {sym}，止损移动取消")
            return

        side = pos.get("side", "LONG")
        is_long = side.upper() in ("LONG", "BUY")
        qty = abs(pos.get("qty", 0))
        if qty <= 0:
            return

        # Place new stop-loss order
        try:
            from cryptopilot.trading.order_executor import OrderRequest, _make_client_id

            req = OrderRequest(
                symbol=sym,
                side="SELL" if is_long else "BUY",
                order_type="STOP_MARKET",
                quantity=qty,
                stop_price=new_stop,
                reduce_only=True,
                position_side="LONG" if is_long else "SHORT",
                client_order_id=_make_client_id("sl_defense"),
            )
            result = await self._executor.create_order(req)
            self._current_stop[sym] = new_stop
            logger.info(
                f"止损已移动: {sym} → {new_stop:.4f} (原因: {reason}) "
                f"[order_id={result.order_id}]"
            )
        except Exception:
            logger.exception(f"止损移动失败: {sym}")

    async def _execute_force_exit(self, symbol: str, reason: str) -> None:
        """Force-close a position via market order."""
        sym = symbol

        pos = self._pm.get_position(sym) if self._pm else None
        if not pos:
            logger.warning(f"无法找到持仓 {sym}，强制退出取消")
            return

        side = pos.get("side", "LONG")
        is_long = side.upper() in ("LONG", "BUY")
        qty = abs(pos.get("qty", 0))
        if qty <= 0:
            return

        # Cancel all open orders first
        try:
            await self._executor.cancel_all_orders(sym)
        except Exception:
            pass

        # Market close
        try:
            from cryptopilot.trading.order_executor import OrderRequest

            req = OrderRequest(
                symbol=sym,
                side="SELL" if is_long else "BUY",
                order_type="MARKET",
                quantity=qty,
                reduce_only=True,
                position_side="LONG" if is_long else "SHORT",
            )
            result = await self._executor.create_order(req)
            logger.warning(
                f"强制平仓: {sym} reason={reason} "
                f"price={result.avg_price or result.price:.4f} status={result.status}"
            )
        except Exception:
            logger.exception(f"强制平仓失败: {sym}")

        # Clean up tracking
        self.unregister_position(sym)

        # Sync
        if self._pm:
            await self._pm.sync_from_exchange(self._executor)

    # ----------------------------------------------------------------
    # Internal: Pure Helpers
    # ----------------------------------------------------------------

    def _calc_tp_price(self, entry: float, pct: float, side: str) -> float:
        """Calculate TP price for a given percentage from entry."""
        is_long = side.upper() in ("LONG", "BUY")
        if is_long:
            return entry * (1 + pct / 100)
        return entry * (1 - pct / 100)

    @staticmethod
    def _price_reached(side: str, current: float, target: float) -> bool:
        """Check if current price has reached (or crossed) a target."""
        is_long = side.upper() in ("LONG", "BUY")
        if is_long:
            return current >= target
        return current <= target

    def _is_stop_triggered(
        self, symbol: str, is_long: bool, price: float, stop: float
    ) -> bool:
        """Check if stop-loss level has been breached."""
        if stop <= 0:
            return False
        if is_long:
            return price <= stop
        return price >= stop


# ----------------------------------------------------------------
# Factory: build from config
# ----------------------------------------------------------------

def build_exit_manager_from_config(
    raw_cfg: dict,
    executor=None,
    position_manager=None,
    notifier=None,
    cache=None,
) -> ExitManager:
    """Create an ExitManager from config.yaml scoring section.

    Reads from scoring.tp_tiers and sideways management settings.
    """
    scoring = raw_cfg.get("scoring", {})
    tp_cfg = scoring.get("tp_tiers", {})

    # Build TP tier configs
    tp1_pct = float(tp_cfg.get("tp1_pct", 3.0))
    tp2_pct = float(tp_cfg.get("tp2_pct", 6.0))
    tp3_pct = float(tp_cfg.get("tp3_pct", 10.0))
    tp1_ratio = float(tp_cfg.get("tp1_ratio", 0.30))
    tp2_ratio = float(tp_cfg.get("tp2_ratio", 0.30))
    tp3_ratio = float(tp_cfg.get("tp3_ratio", 0.40))

    tiers = [
        TpTierConfig(level=1, pct=tp1_pct, ratio=tp1_ratio),
        TpTierConfig(level=2, pct=tp2_pct, ratio=tp2_ratio),
        TpTierConfig(level=3, pct=tp3_pct, ratio=tp3_ratio),
    ]

    # Read risk config for trailing/sideways params
    risk = raw_cfg.get("risk", {})

    return ExitManager(
        tp_tiers=tiers,
        breakeven_offset_pct=float(tp_cfg.get("breakeven_offset_pct", 0.5)),
        trail_distance_pct=float(risk.get("trailing_distance_pct", 1.5)),
        trail_activation_pct=float(risk.get("trailing_activation_pct", 0.5)),
        sideways_defense_minutes=float(tp_cfg.get("sideways_defense_minutes", 90.0)),
        sideways_exit_minutes=float(tp_cfg.get("sideways_exit_minutes", 180.0)),
        sideways_range_pct=float(tp_cfg.get("sideways_range_pct", 2.0)),
        pre_tp_guard_enabled=bool(tp_cfg.get("pre_tp_guard_enabled", True)),
        pre_tp_guard_min_roi_pct=float(tp_cfg.get("pre_tp_guard_min_roi_pct", 0.2)),
        executor=executor,
        position_manager=position_manager,
        notifier=notifier,
        cache=cache,
    )
