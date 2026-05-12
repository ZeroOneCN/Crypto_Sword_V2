"""Position tracking — sync with exchange & database."""

from __future__ import annotations

from loguru import logger

from cryptopilot.persistence.database import Database
from cryptopilot.persistence.repositories import PositionRepository, PositionHistoryRepository
from cryptopilot.persistence.models import PositionRecord
from cryptopilot.trading.order_executor import PositionInfo


class PositionManager:
    """In-memory position cache synced with exchange and persisted to DB."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = PositionRepository(db)
        self._history_repo = PositionHistoryRepository(db)
        self._positions: dict[str, dict] = {}  # symbol -> db row
        self._closed_positions: dict[str, dict] = {}

    async def _archive_position(self, position: dict | None) -> None:
        """Persist a closed position snapshot into history for replay/reporting."""

        if not position:
            return
        exit_time = str(position.get("exit_time", "") or "")
        if not exit_time:
            return
        try:
            payload = {
                k: v for k, v in position.items()
                if k in PositionRecord.__dataclass_fields__
            }
            rec = PositionRecord(**payload)
            await self._history_repo.archive(rec)
        except Exception:
            logger.debug(
                f"无法归档已平仓持仓 {position.get('symbol', '')}",
                exc_info=True,
            )

    @staticmethod
    def infer_strategy_from_metadata(position: dict | None) -> dict[str, str]:
        """Fallback strategy attribution for legacy rows without explicit strategy fields."""

        if not position:
            return {"strategy_id": "", "strategy_preset": "", "support_presets": ""}

        strategy_id = str(position.get("strategy_id", "") or "")
        strategy_preset = str(position.get("strategy_preset", "") or "")
        support_presets = str(position.get("support_presets", "") or "")
        if strategy_id or strategy_preset:
            return {
                "strategy_id": strategy_id,
                "strategy_preset": strategy_preset or strategy_id.split("_", 1)[0],
                "support_presets": support_presets,
            }

        entry_reason = str(position.get("entry_reason", "") or "")
        if entry_reason.startswith("preset:"):
            preset_part, _, _ = entry_reason.partition("|")
            preset_name = preset_part.replace("preset:", "", 1).strip()
            if preset_name:
                return {
                    "strategy_id": f"{preset_name}_{position.get('symbol', '')}",
                    "strategy_preset": preset_name,
                    "support_presets": support_presets,
                }

        fallback = str(position.get("strategy_name", "") or "")
        if fallback:
            return {
                "strategy_id": fallback,
                "strategy_preset": fallback.split("_", 1)[0],
                "support_presets": support_presets,
            }
        return {"strategy_id": "", "strategy_preset": "", "support_presets": support_presets}

    async def _fallback_strategy_from_orders(self, symbol: str) -> dict[str, str]:
        """Fallback attribution from the latest order rows for legacy positions."""

        row = await self._db.fetch_one(
            """SELECT strategy_name
               FROM orders
               WHERE symbol = ? AND strategy_name != ''
               ORDER BY created_at DESC, id DESC
               LIMIT 1""",
            (symbol,),
        )
        if not row:
            return {"strategy_id": "", "strategy_preset": "", "support_presets": ""}
        strategy_name = str(row.get("strategy_name", "") or "")
        if not strategy_name:
            return {"strategy_id": "", "strategy_preset": "", "support_presets": ""}
        return {
            "strategy_id": strategy_name,
            "strategy_preset": strategy_name.split("_", 1)[0],
            "support_presets": "",
        }

    async def sync_from_exchange(self, executor) -> None:
        """Pull positions from exchange, update memory + DB."""
        positions = await executor.get_position_info()
        active_symbols = set()

        for pos in positions:
            sym = pos.symbol
            active_symbols.add(sym)

            # Preserve local metadata from existing DB record
            existing = self._positions.get(sym, {})
            entry_reason = existing.get("entry_reason", "")
            inferred = self.infer_strategy_from_metadata(existing)
            if not inferred["strategy_id"]:
                order_fallback = await self._fallback_strategy_from_orders(sym)
                if order_fallback["strategy_id"]:
                    inferred = order_fallback

            rec = PositionRecord(
                symbol=pos.symbol,
                side=pos.position_side,
                qty=pos.quantity,
                entry_price=pos.entry_price,
                mark_price=pos.mark_price,
                leverage=pos.leverage,
                liquidation_price=pos.liquidation_price,
                unrealized_pnl=pos.unrealized_pnl,
                strategy_id=inferred["strategy_id"],
                strategy_preset=inferred["strategy_preset"],
                support_presets=inferred["support_presets"],
                entry_reason=entry_reason,
            )
            await self._repo.upsert(rec)
            row = await self._repo.get_by_symbol(sym)
            if row:
                fallback = self.infer_strategy_from_metadata(row)
                if not fallback["strategy_id"]:
                    order_fallback = await self._fallback_strategy_from_orders(sym)
                    if order_fallback["strategy_id"]:
                        fallback = order_fallback
                row["strategy_id"] = row.get("strategy_id") or fallback["strategy_id"]
                row["strategy_preset"] = row.get("strategy_preset") or fallback["strategy_preset"]
                row["support_presets"] = row.get("support_presets") or fallback["support_presets"]
                self._positions[sym] = row

        # Remove positions that are no longer open on exchange
        for sym in list(self._positions.keys()):
            if sym not in active_symbols:
                closed_row = dict(self._positions[sym])
                self._closed_positions[sym] = closed_row
                await self._archive_position(closed_row)
                await self._repo.delete(sym, self._positions[sym].get("side", ""))
                self._positions.pop(sym, None)

    def get_position(self, symbol: str) -> dict | None:
        """Get a position for a symbol (or None)."""
        return self._positions.get(symbol)

    def get_all_positions(self) -> list[dict]:
        """Return all tracked positions."""
        return list(self._positions.values())

    def has_position(self, symbol: str) -> bool:
        """Check if we hold a position in this symbol."""
        pos = self._positions.get(symbol)
        return pos is not None and abs(pos.get("qty", 0)) > 0

    async def set_entry_reason(self, symbol: str, reason: str) -> None:
        """Set the entry_reason for an existing position in cache + DB."""
        pos = self._positions.get(symbol)
        if pos is not None:
            pos["entry_reason"] = reason
            try:
                from cryptopilot.persistence.models import PositionRecord
                rec = PositionRecord(**{k: v for k, v in pos.items() if k in PositionRecord.__dataclass_fields__})
                await self._repo.upsert(rec)
            except Exception:
                logger.debug(f"无法保存 entry_reason for {symbol}")

    async def set_strategy_context(
        self,
        symbol: str,
        *,
        strategy_id: str,
        strategy_preset: str,
        support_presets: list[str] | None = None,
        entry_reason: str | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        current_stop: float | None = None,
        initial_qty: float | None = None,
    ) -> None:
        """Persist stable strategy attribution on an open position."""

        pos = self._positions.get(symbol)
        if pos is None:
            return
        pos["strategy_id"] = strategy_id
        pos["strategy_preset"] = strategy_preset
        pos["support_presets"] = ",".join(support_presets or [])
        if entry_reason is not None:
            pos["entry_reason"] = entry_reason
        if stop_loss_price is not None:
            pos["stop_loss_price"] = stop_loss_price
        if take_profit_price is not None:
            pos["take_profit_price"] = take_profit_price
        if current_stop is not None:
            pos["current_stop"] = current_stop
        if initial_qty is not None:
            pos["initial_qty"] = initial_qty
        try:
            rec = PositionRecord(**{k: v for k, v in pos.items() if k in PositionRecord.__dataclass_fields__})
            await self._repo.upsert(rec)
        except Exception:
            logger.debug(f"无法保存 strategy context for {symbol}")

    def get_position_context(self, symbol: str) -> dict | None:
        """Return open or just-closed position context for close attribution."""

        pos = self._positions.get(symbol) or self._closed_positions.get(symbol)
        if pos is None:
            return None
        enriched = dict(pos)
        inferred = self.infer_strategy_from_metadata(enriched)
        enriched["strategy_id"] = enriched.get("strategy_id") or inferred["strategy_id"]
        enriched["strategy_preset"] = enriched.get("strategy_preset") or inferred["strategy_preset"]
        enriched["support_presets"] = enriched.get("support_presets") or inferred["support_presets"]
        return enriched

    async def update_risk_state(
        self,
        symbol: str,
        *,
        current_stop: float | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        tp_tiers_filled: str | None = None,
        partial_tp_count: int | None = None,
        sideways_defense_moved: int | None = None,
    ) -> None:
        """Persist runtime exit-state changes for an open position."""

        pos = self._positions.get(symbol)
        if pos is None:
            return
        if current_stop is not None:
            pos["current_stop"] = current_stop
        if stop_loss_price is not None:
            pos["stop_loss_price"] = stop_loss_price
        if take_profit_price is not None:
            pos["take_profit_price"] = take_profit_price
        if tp_tiers_filled is not None:
            pos["tp_tiers_filled"] = tp_tiers_filled
        if partial_tp_count is not None:
            pos["partial_tp_count"] = partial_tp_count
        if sideways_defense_moved is not None:
            pos["sideways_defense_moved"] = sideways_defense_moved
        try:
            rec = PositionRecord(**{k: v for k, v in pos.items() if k in PositionRecord.__dataclass_fields__})
            await self._repo.upsert(rec)
        except Exception:
            logger.debug(f"鏃犳硶淇濆瓨 risk state for {symbol}")

    async def mark_closed(
        self,
        symbol: str,
        *,
        side: str,
        exit_reason: str,
        exit_price: float,
        exit_time: str,
        pnl: float,
        pnl_pct: float,
    ) -> None:
        """Persist close metadata before exchange sync removes the live row."""

        pos = self.get_position_context(symbol)
        if pos is None:
            return
        pos["exit_reason"] = exit_reason
        pos["exit_price"] = exit_price
        pos["exit_time"] = exit_time
        pos["pnl"] = pnl
        pos["pnl_pct"] = pnl_pct
        self._closed_positions[symbol] = dict(pos)
        try:
            await self._repo.mark_closed(
                symbol,
                side,
                exit_reason=exit_reason,
                exit_price=exit_price,
                exit_time=exit_time,
                pnl=pnl,
                pnl_pct=pnl_pct,
            )
            await self._archive_position(pos)
        except Exception:
            logger.debug(f"无法保存 close metadata for {symbol}")

    @property
    def position_count(self) -> int:
        return len([p for p in self._positions.values() if abs(p.get("qty", 0)) > 0])
