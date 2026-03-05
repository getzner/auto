"""
main.py — Main entry point.
Starts both the market data feed and the hourly orchestrator loop.
Also runs the weekly Meta-Agent self-improvement cycle.
"""

import asyncio
import os
import sys
import time
import signal
from datetime import datetime, timezone

from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# Single logger configuration (no duplicates)
log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
logger.remove()
logger.add(sys.stderr, level=log_level)
logger.info(f"[MAIN] Logger initialized with level: {log_level}")

SYMBOLS   = os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT").split(",")
TIMEFRAME = os.getenv("TIMEFRAME", "1h")


_running = True


def _handle_signal(sig, frame):
    global _running
    logger.warning(f"Signal {sig} received — shutting down...")
    _running = False


async def orchestrator_loop() -> None:
    """Run agent cycle on startup, then at the top of every hour.
    Uses absolute-time sleep to avoid drift when cycles take > 60s.
    """
    from agents.orchestrator import run_cycle

    first_run = True

    while _running:
        now = datetime.now(timezone.utc)

        if first_run or now.minute == 0:
            cycle_start = time.monotonic()
            for sym in SYMBOLS:
                if not _running:
                    break
                sym = sym.strip()
                logger.info(f"[MAIN] ── Cycle: {sym} (first={first_run}) ──")
                try:
                    await run_cycle(sym)
                except Exception:
                    logger.exception(f"[MAIN] Cycle error for {sym}")

            first_run = False

            # Sleep until 5s past the next hour boundary (prevents drift)
            now_after = datetime.now(timezone.utc)
            seconds_past_hour = now_after.minute * 60 + now_after.second
            sleep_time = max(3600 - seconds_past_hour + 5, 60)
            logger.info(f"[MAIN] Next cycle in {sleep_time // 60}m{sleep_time % 60}s")
            await asyncio.sleep(sleep_time)
        else:
            await asyncio.sleep(30)


# ── Gap 1: Weekly Meta-Agent self-improvement loop ──────────
# Runs every 7 days. Evaluates all agent performance and triggers
# autonomous improvement cycles as described in smart_agents.md.

WEEKLY_REVIEW_INTERVAL = int(os.getenv("META_REVIEW_INTERVAL_DAYS", "7")) * 86400

async def meta_agent_loop() -> None:
    """Weekly Meta-Agent review: evaluate agents, trigger self-improvement."""
    # Wait 60s after startup before first evaluation (let other services settle)
    await asyncio.sleep(60)
    logger.info("[META] Meta-Agent loop started (first review in stats-gathering mode)")

    last_review = 0.0

    while _running:
        now_ts = time.time()
        if now_ts - last_review >= WEEKLY_REVIEW_INTERVAL:
            logger.info("[META] ★ Starting weekly agent performance review...")
            try:
                from agents.meta_agent import MetaAgent
                result = await MetaAgent().weekly_review()
                last_review = now_ts
                logger.info(f"[META] ★ Weekly review complete: {str(result)[:200]}")
            except Exception as e:
                logger.error(f"[META] Weekly review failed: {e}")
        await asyncio.sleep(3600)  # Check every hour if it's time for a review


# stop_checker_loop and market_data streams have been moved to their own
# decoupled services (`services/monitor_service.py` and `services/market_data_service.py`)
# to allow for robust microservice architecture.


async def heartbeat_loop() -> None:
    """Update heartbeat in Redis every 15s."""
    from data.redis_client import get_redis
    redis = get_redis()
    while _running:
        try:
            redis.set("main_heartbeat", datetime.now(timezone.utc).isoformat())
        except Exception as e:
            logger.error(f"[MAIN] Heartbeat error: {e}")
        await asyncio.sleep(15)


PID_FILE = "/opt/trade_server/data/main.pid"
if not os.path.exists("/opt/trade_server/data"):
    PID_FILE = os.path.join(os.path.dirname(__file__), "data", "main.pid")

async def main() -> None:
    # ── PID Lock ──────────────────────────────────────────
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            logger.error(f"[MAIN] 🛑 Engine already running with PID {old_pid}. Exiting.")
            sys.exit(1)
        except (OSError, ValueError):
            try:
                os.remove(PID_FILE)
            except OSError as e:
                logger.warning(f"[MAIN] Could not remove old PID file: {e}")
            
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError as e:
        logger.warning(f"[MAIN] Could not write new PID file: {e}")

    # Set up signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(sig)))

    logger.info("=" * 50)
    logger.info(" Trade Server Starting")
    logger.info(f" Mode: {os.getenv('TRADE_MODE', 'paper')}")
    logger.info(f" Symbols: {SYMBOLS}")
    logger.info("=" * 50)

    # Run Orchestrator + Heartbeat + Meta-Agent
    tasks = [
        asyncio.create_task(orchestrator_loop(), name="orchestrator"),
        asyncio.create_task(heartbeat_loop(),    name="heartbeat"),
        asyncio.create_task(meta_agent_loop(),   name="meta_agent"),  # Gap 1: wekelijkse self-improvement
    ]
    
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except OSError:
                pass


async def shutdown(sig):
    global _running
    logger.warning(f"Signal {sig} received — shutting down...")
    _running = False
    
    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    logger.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

    loop = asyncio.get_running_loop()
    loop.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
