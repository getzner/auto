"""
paper_trader.py — Paper Trading Execution Engine
Simulates fills, tracks positions and P&L.
"""

import os
import asyncio
from datetime import datetime, timezone

from loguru import logger
from data.db import get_db_conn
from data.discord_notifier import notify_trade_open, notify_trade_close


SLIPPAGE_PCT = 0.05  # 0.05% slippage on fills


class PaperTrader:
    async def execute(self, decision_id: int | None, proposal: dict) -> None:
        if proposal.get("direction") == "HOLD" or not decision_id:
            return

        symbol    = proposal.get("symbol", "BTC/USDT")
        side      = "long" if proposal["direction"] == "LONG" else "short"
        raw_price = float(proposal.get("entry_price") or proposal.get("current_price", 0))
        # Apply slippage
        slip = raw_price * SLIPPAGE_PCT / 100
        fill_price = raw_price + slip if side == "long" else raw_price - slip

        size_pct  = float(proposal.get("position_size_pct", 5.0))
        balance   = await self._get_balance()
        size_usdt = balance * size_pct / 100

        stop_loss   = proposal.get("stop_loss")
        take_profit = proposal.get("take_profit")

        conn = await get_db_conn()
        try:
            pos_id = await conn.fetchval(
                """
                INSERT INTO positions
                    (decision_id, symbol, side, entry_price, size_usdt,
                     stop_loss, take_profit, opened_at, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'open')
                RETURNING id
                """,
                decision_id, symbol, side, fill_price, size_usdt,
                stop_loss, take_profit,
                datetime.now(timezone.utc),
            )
            # Mark decision as executed
            await conn.execute(
                "UPDATE decisions SET executed=true WHERE id=$1", decision_id
            )
        finally:
            await conn.close()

        logger.info(
            f"[PAPER] {side.upper()} {symbol} | "
            f"fill={fill_price:.2f} size=${size_usdt:.2f} "
            f"SL={stop_loss} TP={take_profit} pos_id={pos_id}"
        )

        # Discord notification (non-blocking)
        try:
            await notify_trade_open(
                symbol=symbol, side=side, fill_price=fill_price,
                size_usdt=size_usdt, stop_loss=float(stop_loss) if stop_loss else None,
                take_profit=float(take_profit) if take_profit else None,
                position_id=pos_id, decision_id=decision_id,
            )
        except Exception as e:
            logger.warning(f"[PAPER] Discord notify failed: {e}")

    async def _get_balance(self) -> float:
        """Compute current paper balance = starting balance + closed PnL."""
        starting = float(os.getenv("PAPER_STARTING_BALANCE", "10000"))
        conn = await get_db_conn()
        try:
            row = await conn.fetchrow(
                "SELECT COALESCE(SUM(pnl_usdt), 0) AS total FROM positions WHERE status='closed'"
            )
            realized = float(row["total"]) if row else 0.0
        finally:
            await conn.close()
        return starting + realized

    async def close_position(self, position_id: int, close_price: float, reason: str = "manual") -> None:
        """Close a paper position and calculate P&L."""
        conn = await get_db_conn()
        try:
            pos = await conn.fetchrow(
                "SELECT * FROM positions WHERE id=$1", position_id
            )
            if not pos or pos["status"] != "open":
                return

            entry = float(pos["entry_price"])
            size  = float(pos["size_usdt"])
            qty   = size / entry

            if pos["side"] == "long":
                pnl = (close_price - entry) * qty
            else:
                pnl = (entry - close_price) * qty

            await conn.execute(
                """
                UPDATE positions
                SET status='closed', closed_at=$1, close_price=$2, pnl_usdt=$3
                WHERE id=$4
                """,
                datetime.now(timezone.utc), close_price, pnl, position_id,
            )
            logger.info(f"[PAPER] Closed pos {position_id} @ {close_price:.2f} PnL={pnl:+.2f} ({reason})")

            # Trigger Reporter Agent (Async in background)
            try:
                from agents.reporter_agent import ReporterAgent
                asyncio.create_task(ReporterAgent().generate_journal_entry(position_id))
            except Exception as e:
                logger.error(f"[PAPER] Failed to spawn ReporterAgent: {e}")

            # Discord notification (non-blocking)
            try:
                await notify_trade_close(
                    symbol=pos["symbol"], side=pos["side"],
                    entry_price=float(pos["entry_price"]),
                    close_price=close_price, size_usdt=float(pos["size_usdt"]),
                    pnl=pnl, reason=reason, position_id=position_id,
                )
            except Exception as e:
                logger.warning(f"[PAPER] Discord notify failed: {e}")
        finally:
            await conn.close()

    async def check_stops(self, symbol: str, current_price: float) -> None:
        """Check all open positions for stop/take-profit hits."""
        conn = await get_db_conn()
        try:
            positions = await conn.fetch(
                "SELECT * FROM positions WHERE symbol=$1 AND status='open'", symbol
            )
        finally:
            await conn.close()

        for pos in positions:
            sl = pos["stop_loss"]
            tp = pos["take_profit"]
            pid = pos["id"]
            side = pos["side"]

            if side == "long":
                if sl and current_price <= float(sl):
                    await self.close_position(pid, current_price, "stop_loss")
                elif tp and current_price >= float(tp):
                    await self.close_position(pid, current_price, "take_profit")
            else:
                if sl and current_price >= float(sl):
                    await self.close_position(pid, current_price, "stop_loss")
                elif tp and current_price <= float(tp):
                    await self.close_position(pid, current_price, "take_profit")
