"""
scanner_service.py - Decoupled background service
Runs the infinite scanner_loop watching for setups in Redis from indicators.
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
logger.info(f"[SCANNER_SERVICE] Logger initialized with level: {log_level}")

SYMBOLS = os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT").split(",")

_running = True

async def shutdown(sig):
    global _running
    logger.warning(f"[SCANNER_SERVICE] Signal {sig} received — shutting down...")
    _running = False
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    logger.info(f"[SCANNER_SERVICE] Cancelling {len(tasks)} tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop = asyncio.get_running_loop()
    loop.stop()

async def main():
    from data.scanner import start_scanner, scanner_loop
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    logger.info("=" * 50)
    logger.info(f" Scanner Service Starting for {SYMBOLS}")
    logger.info("=" * 50)

    try:
        # We run the loop directly rather than as a background task
        # since this service is dedicated solely to it
        await scanner_loop(SYMBOLS)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[SCANNER_SERVICE] Crashed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
