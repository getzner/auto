"""
position_manager.py — Multi-TP, Trailing Stop & Breakeven Logic
Handles TP1/TP2 partial closes and dynamic SL adjustment for open positions.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from loguru import logger
from data.db import get_db_conn


@dataclass
class TPLevel:
    pct:       float   # price % gain to trigger TP
    close_pct: float   # % of position to close at this level


# Default TP configuration — overridable via .env
DEFAULT_TP_LEVELS = [
    TPLevel(pct=0.03, close_pct=0.40),   # TP1: +3% → close 40%
    TPLevel(pct=0.05, close_pct=0.40),   # TP2: +5% → close 40%
    # Remaining 20% uses trailing stop
]
TRAILING_ACTIVATION_PCT = 0.05          # start trailing after +5%
TRAILING_DISTANCE_USD   = 300.0         # trail by $300 (or 0.5%)
TRAILING_DISTANCE_PCT   = 0.005         # 0.5% of price


class PositionManager:
    """
    Manages open paper positions with multi-TP and trailing stop logic.
    Designed to be called every minute from the stop monitor.
    """

    def __init__(self, paper_trader=None):
        from execution.paper_trader import PaperTrader
        self.trader = paper_trader or PaperTrader()

    async def check_position(self, pos: dict, current_price: float) -> None:
        """
        Evaluate a single open position against current price.
        Handles: SL hit, TP1, TP2, trailing stop, breakeven move.
        """
        pid   = pos["id"]
        side  = pos["side"]
        entry = float(pos["entry_price"])
        sl    = float(pos["stop_loss"]) if pos["stop_loss"] else None
        tp    = float(pos["take_profit"]) if pos["take_profit"] else None
        size  = float(pos["size_usdt"])
        symbol = pos["symbol"]

        # ── Hard Stop Loss ─────────────────────────────────
        if sl:
            if side == "long"  and current_price <= sl:
                logger.info(f"[PM] 🔴 SL hit pos {pid} @ {current_price:.2f} (sl={sl})")
                await self.trader.close_position(pid, current_price, "stop_loss")
                return
            if side == "short" and current_price >= sl:
                logger.info(f"[PM] 🔴 SL hit pos {pid} @ {current_price:.2f} (sl={sl})")
                await self.trader.close_position(pid, current_price, "stop_loss")
                return

        # ── Multi-TP Logic ─────────────────────────────────
        if side == "long":
            pnl_pct = (current_price - entry) / entry
        else:
            pnl_pct = (entry - current_price) / entry

        tp1_pct = DEFAULT_TP_LEVELS[0].pct
        tp2_pct = DEFAULT_TP_LEVELS[1].pct

        tp1_hit = await self._is_tp_hit(pos, 1)
        tp2_hit = await self._is_tp_hit(pos, 2)

        # TP1: +3% → close 40%, move SL to breakeven
        if pnl_pct >= tp1_pct and not tp1_hit:
            logger.info(f"[PM] 🟡 TP1 hit pos {pid} @ {current_price:.2f} (+{pnl_pct:.1%})")
            await self._partial_close(pid, current_price, DEFAULT_TP_LEVELS[0].close_pct,
                                       "tp1", symbol, side)
            await self._move_sl_to_breakeven(pid, entry)
            await self._mark_tp(pid, 1)  # write flag to DB
            return

        # TP2: +5% → close another 40%, activate trailing on remainder
        if pnl_pct >= tp2_pct and tp1_hit and not tp2_hit:
            logger.info(f"[PM] 🟢 TP2 hit pos {pid} @ {current_price:.2f} (+{pnl_pct:.1%})")
            await self._partial_close(pid, current_price, DEFAULT_TP_LEVELS[1].close_pct,
                                       "tp2", symbol, side)
            await self._activate_trailing(pid, current_price)
            await self._mark_tp(pid, 2)  # write flag to DB
            return

        # Original single-TP (for positions without multi-TP config)
        if tp and not tp1_hit and not tp2_hit:
            if side == "long"  and current_price >= tp:
                logger.info(f"[PM] ✅ TP hit pos {pid} @ {current_price:.2f}")
                await self.trader.close_position(pid, current_price, "take_profit")
                return
            if side == "short" and current_price <= tp:
                logger.info(f"[PM] ✅ TP hit pos {pid} @ {current_price:.2f}")
                await self.trader.close_position(pid, current_price, "take_profit")
                return

        # ── Trailing Stop (after TP2 or activation) ────────
        trailing_active = await self._get_trailing_high(pid)
        if trailing_active is not None:
            await self._check_trailing(pid, current_price, side, trailing_active)

    # ── Helpers ───────────────────────────────────────────

    async def _partial_close(self, pid: int, price: float, pct: float,
                              reason: str, symbol: str, side: str) -> None:
        """Reduce position size by closing a percentage."""
        conn = await get_db_conn()
        try:
            pos = await conn.fetchrow("SELECT * FROM positions WHERE id=$1", pid)
            if not pos or pos["status"] != "open":
                return
            current_size = float(pos["size_usdt"] or 0)
            if current_size <= 0:
                logger.debug(f"[PM] Skipping partial close pos {pid} — size={current_size}")
                return
            close_size   = current_size * pct
            remain_size  = current_size - close_size

            entry = float(pos["entry_price"])
            qty   = close_size / entry
            if side == "long":
                pnl = (price - entry) * qty
            else:
                pnl = (entry - price) * qty

            # Update position size + record partial close in notes
            await conn.execute(
                "UPDATE positions SET size_usdt=$1 WHERE id=$2",
                remain_size, pid
            )
            logger.info(
                f"[PM] Partial close pos {pid} ({reason}): "
                f"closed ${close_size:.0f} @ {price:.2f} PnL={pnl:+.2f} "
                f"| remaining ${remain_size:.0f}"
            )
        finally:
            await conn.close()

        from data.discord_notifier import _send_embed
        await _send_embed({
            "title":  f"{'📈' if side == 'long' else '📉'} Partial Close — {reason.upper()}",
            "color":  0xF4C542,
            "fields": [
                {"name": "Symbol",  "value": symbol,         "inline": True},
                {"name": "Reason",  "value": reason.upper(), "inline": True},
                {"name": "Price",   "value": f"${price:,.2f}","inline": True},
                {"name": "PnL",     "value": f"+${pnl:.2f}", "inline": True},
                {"name": "Remaining","value": f"${remain_size:.0f}", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _move_sl_to_breakeven(self, pid: int, entry_price: float) -> None:
        """Move stop loss to entry price (breakeven) after TP1."""
        conn = await get_db_conn()
        try:
            await conn.execute(
                "UPDATE positions SET stop_loss=$1 WHERE id=$2",
                entry_price, pid
            )
            logger.info(f"[PM] SL moved to breakeven {entry_price:.2f} for pos {pid}")
        finally:
            await conn.close()

    async def _activate_trailing(self, pid: int, current_price: float) -> None:
        """Store trailing high watermark to start trailing stop."""
        conn = await get_db_conn()
        try:
            # Store trailing activation price in take_profit field (repurposed)
            # Use negative value as a flag: -current_price = trailing active at this level
            await conn.execute(
                "UPDATE positions SET take_profit=$1 WHERE id=$2",
                -current_price, pid
            )
            logger.info(f"[PM] Trailing stop activated for pos {pid} @ {current_price:.2f}")
        finally:
            await conn.close()

    async def _check_trailing(self, pid: int, current_price: float,
                               side: str, high_water: float) -> None:
        """Update trailing stop and check if it's been hit."""
        trail_dist = max(
            current_price * TRAILING_DISTANCE_PCT,
            TRAILING_DISTANCE_USD
        )

        if side == "long":
            new_high = max(high_water, current_price)
            trail_sl = new_high - trail_dist
            if current_price <= trail_sl:
                logger.info(f"[PM] 🔵 Trailing stop hit pos {pid} @ {current_price:.2f}")
                await self.trader.close_position(pid, current_price, "trailing_stop")
                return
            # Update high watermark
            if new_high > high_water:
                conn = await get_db_conn()
                try:
                    await conn.execute(
                        "UPDATE positions SET take_profit=$1 WHERE id=$2",
                        -new_high, pid
                    )
                finally:
                    await conn.close()

    async def _get_trailing_high(self, pid: int) -> float | None:
        """Return the trailing high watermark if trailing is active, else None."""
        conn = await get_db_conn()
        try:
            row = await conn.fetchrow("SELECT take_profit FROM positions WHERE id=$1", pid)
            if row and row["take_profit"] and float(row["take_profit"]) < 0:
                return abs(float(row["take_profit"]))
            return None
        finally:
            await conn.close()

    async def _is_tp_hit(self, pos: dict, level: int) -> bool:
        """Check TP level via tp_flags column in DB (reliable, not size-based)."""
        conn = await get_db_conn()
        try:
            row = await conn.fetchrow(
                "SELECT tp_flags FROM positions WHERE id=$1", pos["id"]
            )
            if not row:
                return False
            flags = int(row["tp_flags"] or 0)
            return flags >= level
        finally:
            await conn.close()

    async def _mark_tp(self, pid: int, level: int) -> None:
        """Write TP level flag to DB — prevents re-triggering on next cycle."""
        conn = await get_db_conn()
        try:
            await conn.execute(
                "UPDATE positions SET tp_flags=$1 WHERE id=$2",
                level, pid
            )
            logger.debug(f"[PM] TP{level} flag set for pos {pid}")
        finally:
            await conn.close()
