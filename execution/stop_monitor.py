"""
stop_monitor.py — Per-Minute Price Monitor & Stop Management
Runs as a background async loop. Checks all open positions every 60 seconds.
Designed to be started from api/server.py on startup.
"""

import asyncio
import os
from datetime import datetime, timezone
from loguru import logger


MONITOR_INTERVAL = int(os.getenv("STOP_MONITOR_INTERVAL", "60"))   # seconds
SYMBOLS          = [s.strip() for s in os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT").split(",")]

_monitor_active = False
_last_error_time = 0.0

def is_monitor_running() -> bool:
    import time
    if not _monitor_active: return False
    if time.time() - _last_error_time < 60: return False  # Degraded status turns LED red
    return True


async def _get_current_price(symbol: str) -> float | None:
    """Fetch live price from Bybit REST API."""
    import aiohttp
    bybit_symbol = symbol.replace("/", "")
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={bybit_symbol}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                data = await resp.json()
                ticker = data["result"]["list"][0]
                return float(ticker["lastPrice"])
    except Exception as e:
        logger.warning(f"[MONITOR] Price fetch failed for {symbol}: {e}")
        return None


async def _get_open_positions() -> list[dict]:
    """Fetch all open positions from DB."""
    from data.db import get_db_conn
    import decimal
    from datetime import date

    conn = await get_db_conn()
    try:
        rows = await conn.fetch("SELECT * FROM positions WHERE status='open'")
        positions = []
        for r in rows:
            d = dict(r)
            # Normalize types
            for k, v in d.items():
                if isinstance(v, decimal.Decimal):
                    d[k] = float(v)
            positions.append(d)
        return positions
    finally:
        await conn.close()


async def monitor_loop() -> None:
    """
    Main monitoring loop — runs every MONITOR_INTERVAL seconds.
    Checks all open positions against current prices.
    """
    from execution.position_manager import PositionManager
    manager = PositionManager()

    global _monitor_active
    _monitor_active = True
    logger.info(
        f"[MONITOR] 🟢 Stop monitor started "
        f"(interval={MONITOR_INTERVAL}s, symbols={SYMBOLS})"
    )

    while True:
        try:
            positions = await _get_open_positions()

            if not positions:
                logger.debug("[MONITOR] No open positions")
            else:
                # Fetch prices for all unique symbols in open positions
                symbols_needed = list({p["symbol"] for p in positions})
                prices = {}
                for sym in symbols_needed:
                    price = await _get_current_price(sym)
                    if price:
                        prices[sym] = price

                logger.debug(
                    f"[MONITOR] Checking {len(positions)} positions | "
                    + " | ".join(f"{s}=${p:,.0f}" for s, p in prices.items())
                )

                for pos in positions:
                    sym   = pos["symbol"]
                    price = prices.get(sym)
                    if price:
                        await manager.check_position(pos, price)

            # ── Live Position Sync ────────────────────────
            from utils.config import get_env_string
            if get_env_string("TRADE_MODE", "paper") == "live":
                await _sync_live_trades(positions)

        except Exception as e:
            import time
            global _last_error_time
            _last_error_time = time.time()
            logger.exception(f"[MONITOR] Error in monitor loop: {e}")

        await asyncio.sleep(MONITOR_INTERVAL)


async def _sync_live_trades(db_positions: list[dict]) -> None:
    """
    Syncs DB with Bybit status. If a live position exists in DB but 
    is gone from Bybit, mark it as closed and trigger reporter.
    """
    from execution.live_trader import LiveTrader
    live = LiveTrader()
    bybit_pos = await live.get_active_positions()
    bybit_symbols = {p["symbol"] for p in bybit_pos if float(p.get("size", 0)) != 0}

    for db_pos in db_positions:
        if not db_pos.get("is_live"):
            continue
        
        # Bybit uses BTCPUSDT format (no slash)
        bybit_fmt = db_pos["symbol"].replace("/", "")
        if bybit_fmt not in bybit_symbols:
            logger.info(f"[MONITOR] 🔄 Live position {db_pos['id']} ({db_pos['symbol']}) closed on Bybit. Syncing...")
            
            # Fetch last price for this symbol to record as close_price
            price = await _get_current_price(db_pos["symbol"])
            
            from data.db import get_db_conn
            conn = await get_db_conn()
            try:
                entry = float(db_pos["entry_price"])
                size  = float(db_pos["size_usdt"])
                qty   = size / entry if entry > 0 else 0
                close_price = price or entry # Fallback to entry if fetch fails
                
                if db_pos["side"] == "long":
                    pnl = (close_price - entry) * qty
                else:
                    pnl = (entry - close_price) * qty

                await conn.execute(
                    """
                    UPDATE positions 
                    SET status='closed', closed_at=NOW(), close_price=$1, pnl_usdt=$2
                    WHERE id=$3
                    """,
                    close_price, pnl, db_pos["id"]
                )
                
                # Trigger Reporter
                try:
                    from agents.reporter_agent import ReporterAgent
                    asyncio.create_task(ReporterAgent().generate_journal_entry(db_pos["id"]))
                except: pass

            finally:
                await conn.close()


def start_monitor() -> asyncio.Task | None:
    """Start the monitor loop as a background task. Call from server startup."""
    if is_monitor_running():
        logger.warning("[MONITOR] Already running, skipping duplicate start.")
        return None
    return asyncio.create_task(monitor_loop())
