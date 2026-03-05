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

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "8"))


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
            max_inactive_connection_lifetime=300,
        )
        logger.info("[DB] Connection pool ready")
    return _pool


async def get_db_conn() -> asyncpg.Connection:
    """
    Backward-compatible: acquires a connection from the shared pool.
    
    IMPORTANT: Callers MUST release the connection after use:
      conn = await get_db_conn()
      try:
          ...
      finally:
          await conn.close()   # returns connection to pool
    
    Or use the pool directly for performance-critical code:
      pool = await get_pool()
      async with pool.acquire() as conn:
          ...
    """
    pool = await get_pool()
    return await pool.acquire()


async def close_pool() -> None:
    """Gracefully close the pool on service shutdown."""
    global _pool
    if _pool and not _pool._closed:
        await _pool.close()
        logger.info("[DB] Connection pool closed")
        _pool = None
