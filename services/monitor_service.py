"""
monitor_service.py - Decoupled background service
Runs the infinite stop_monitor loop to protect positions independently.
Also runs the legacy stop_checker_loop for paper trading if enabled.
"""

import sys
import os
import asyncio
import signal
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
logger.remove()
logger.add(sys.stderr, level=log_level)
logger.info(f"[MONITOR_SERVICE] Logger initialized with level: {log_level}")

SYMBOLS = os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT").split(",")

_running = True

async def stop_checker_loop() -> None:
    """Check open paper positions for stop/TP hits every minute."""
    from data.market_data import make_exchange
    from execution.paper_trader import PaperTrader

    exchange = make_exchange()
    paper = PaperTrader()

    try:
        while _running:
            for _ in range(30): # 30 * 1s sleeps to check _running frequently
                if not _running: break
                await asyncio.sleep(1)
            
            if not _running: break

            for sym in SYMBOLS:
                sym = sym.strip()
                try:
                    ticker = await exchange.fetch_ticker(sym)
                    price  = float(ticker["last"])
                    await paper.check_stops(sym, price)
                except Exception as e:
                    logger.error(f"[MONITOR_SERVICE] Paper stop checker error {sym}: {e}")
    finally:
        await exchange.close()

async def shutdown(sig):
    global _running
    logger.warning(f"[MONITOR_SERVICE] Signal {sig} received — shutting down...")
    _running = False
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    logger.info(f"[MONITOR_SERVICE] Cancelling {len(tasks)} tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop = asyncio.get_running_loop()
    loop.stop()

async def main():
    from execution.stop_monitor import monitor_loop
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    logger.info("=" * 50)
    logger.info(f" Stop Monitor Service Starting for {SYMBOLS}")
    logger.info("=" * 50)

    try:
        tasks = [
            asyncio.create_task(monitor_loop()),             # Live
            asyncio.create_task(stop_checker_loop())         # Paper
        ]
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[MONITOR_SERVICE] Crashed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
