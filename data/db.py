"""
db.py — Database connection helpers (asyncpg)

Uses a module-level connection pool to avoid per-query TCP handshake overhead
and to prevent exceeding Postgres max_connections when multiple services run
concurrently (monitor, scanner, orchestrator agents).
"""
import os
import asyncio
import asyncpg
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

DSN = (
    f"postgresql://{os.getenv('DB_USER', 'trader')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST', 'localhost')}:"
    f"{os.getenv('DB_PORT', '5432')}/"
    f"{os.getenv('DB_NAME', 'trade_db')}"
)

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "4"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "20"))


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it if necessary."""
    global _pool
    if _pool is not None and not _pool._closed:
        return _pool
    async with _pool_lock:
        # Double-check after acquiring lock
        if _pool is not None and not _pool._closed:
            return _pool
        logger.info(f"[DB] Initializing connection pool (min={DB_POOL_MIN}, max={DB_POOL_MAX})")
        _pool = await asyncpg.create_pool(
            DSN,
            min_size=DB_POOL_MIN,
            max_size=DB_POOL_MAX,
            command_timeout=30,
            max_inactive_connection_lifetime=60.0,
            timeout=15.0
        )
        logger.info("[DB] Connection pool ready")
    return _pool


async def get_db_conn() -> asyncpg.Connection:
    """
    Backward-compatible: acquires a connection from the shared pool.
    """
    pool = await get_pool()
    try:
        return await pool.acquire(timeout=15.0)
    except asyncio.TimeoutError:
        logger.error("[DB] Timeout acquiring raw connection.")
        raise
        
from contextlib import asynccontextmanager
from fastapi import HTTPException

@asynccontextmanager
async def get_db_session(timeout: float = 15.0):
    """
    Robust connection manager. Recommended for all endpoints and tasks.
    Guarantees that the connection is released to the pool, preventing leaks.
    """
    pool = await get_pool()
    try:
        conn = await pool.acquire(timeout=timeout)
        try:
            yield conn
        finally:
            await pool.release(conn)
    except asyncio.TimeoutError:
        logger.error("[DB] Connection pool exhausted!")
        raise HTTPException(503, "Database connection pool exhausted – try again soon")
    except Exception as e:
        logger.error(f"[DB] Database error: {e}")
        raise HTTPException(500, f"Database error: {str(e)}")


async def close_pool() -> None:
    """Gracefully close the pool on service shutdown."""
    global _pool
    if _pool and not _pool._closed:
        await _pool.close()
        logger.info("[DB] Connection pool closed")
        _pool = None

async def log_pool_stats():
    """Periodically logs database connection pool metrics for debugging/monitoring."""
    while True:
        try:
            pool = await get_pool()
            total = pool.get_size()
            idle = pool.get_idle_size()
            waiting = pool._queue.qsize() if hasattr(pool, '_queue') else 0
            logger.info(f"[DB] Pool stats - Total: {total}, Idle: {idle}, Waiting: {waiting}")
        except Exception as e:
            logger.error(f"[DB] Error logging pool stats: {e}")
        await asyncio.sleep(30)
