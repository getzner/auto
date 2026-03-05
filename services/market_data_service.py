"""
market_data_service.py - Decoupled background service for CCXT streams
Runs the OHLCV and Trades websocket streams to save data to Postgres natively.
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
logger.info(f"[DATA_SERVICE] Logger initialized with level: {log_level}")


_running = True

def _handle_signal(sig, frame):
    global _running
    logger.warning(f"[DATA_SERVICE] Signal {sig} received — shutting down...")
    _running = False

async def shutdown(sig):
    global _running
    logger.warning(f"[DATA_SERVICE] Signal {sig} received — shutting down...")
    _running = False
    
    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    logger.info(f"[DATA_SERVICE] Cancelling {len(tasks)} tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop = asyncio.get_running_loop()
    loop.stop()

async def main():
    from data.market_data import main as market_data_main
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    logger.info("=" * 50)
    logger.info(" Market Data Stream Service Starting")
    logger.info("=" * 50)

    try:
        await market_data_main()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[DATA_SERVICE] Stream crashed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
