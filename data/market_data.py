"""
market_data.py — CCXT Pro WebSocket feed
Streams 1h OHLCV candles and raw trades for all configured symbols.
Stores to PostgreSQL + publishes to Redis pub/sub for real-time agents.
"""

import asyncio
import os
import json
from datetime import datetime, timezone

import ccxt.pro as ccxtpro
from loguru import logger
from dotenv import load_dotenv

from data.db import get_db_conn
from data.redis_client import get_redis

load_dotenv()

EXCHANGE_NAME = os.getenv("EXCHANGE", "bybit")
SYMBOLS       = os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT").split(",")
TIMEFRAME     = os.getenv("TIMEFRAME", "1h")
API_KEY       = os.getenv("EXCHANGE_API_KEY", "")
API_SECRET    = os.getenv("EXCHANGE_API_SECRET", "")


def make_exchange() -> ccxtpro.Exchange:
    cls = getattr(ccxtpro, EXCHANGE_NAME)
    return cls({
        "apiKey":    API_KEY,
        "secret":    API_SECRET,
        "enableRateLimit": True,
        "options":   {"defaultType": "spot"},
    })


async def watch_ohlcv(exchange: ccxtpro.Exchange, symbol: str) -> None:
    """Stream 1h OHLCV candles → PostgreSQL + Redis."""
    logger.info(f"[OHLCV] Starting stream: {symbol} {TIMEFRAME}")
    while True:
        try:
            candles = await exchange.watch_ohlcv(symbol, TIMEFRAME)
            for ts_ms, o, h, l, c, v in candles:
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                row = {
                    "symbol": symbol, "timeframe": TIMEFRAME,
                    "ts": ts, "open": o, "high": h,
                    "low": l, "close": c, "volume": v,
                }
                await _upsert_candle(row)
                # Notify agents via Redis
                r = get_redis()
                r.publish("candles", json.dumps(row, default=str))
                logger.debug(f"[OHLCV] {symbol} {ts} O={o} H={h} L={l} C={c} V={v:.2f}")
        except Exception as e:
            logger.error(f"[OHLCV] {symbol} error: {e} — retrying in 5s")
            await asyncio.sleep(5)


async def watch_trades(exchange: ccxtpro.Exchange, symbol: str) -> None:
    """Stream raw trades → PostgreSQL (for CVD/orderflow reconstruction)."""
    logger.info(f"[TRADES] Starting stream: {symbol}")
    while True:
        try:
            trades = await exchange.watch_trades(symbol)
            rows = []
            for t in trades:
                side        = t["side"]              # buy | sell
                taker_side  = side                   # in spot, side == taker side
                rows.append({
                    "symbol":      symbol,
                    "exchange_id": str(t["id"]),
                    "ts":          datetime.fromtimestamp(
                                       t["timestamp"] / 1000, tz=timezone.utc
                                   ),
                    "price":      t["price"],
                    "amount":     t["amount"],
                    "side":       side,
                    "taker_side": taker_side,
                })
            await _bulk_insert_trades(rows)
        except Exception as e:
            logger.error(f"[TRADES] {symbol} error: {e} — retrying in 5s")
            await asyncio.sleep(5)


async def _upsert_candle(row: dict) -> None:
    conn = await get_db_conn()
    try:
        await conn.execute(
            """
            INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (symbol, timeframe, ts) DO UPDATE
                SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, volume=EXCLUDED.volume
            """,
            row["symbol"], row["timeframe"], row["ts"],
            row["open"], row["high"], row["low"], row["close"], row["volume"],
        )
    finally:
        await conn.close()


async def _bulk_insert_trades(rows: list[dict]) -> None:
    if not rows:
        return
    conn = await get_db_conn()
    try:
        await conn.executemany(
            """
            INSERT INTO trades_raw
                (symbol, exchange_id, ts, price, amount, side, taker_side)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            ON CONFLICT DO NOTHING
            """,
            [(r["symbol"], r["exchange_id"], r["ts"],
              r["price"], r["amount"], r["side"], r["taker_side"])
             for r in rows],
        )
    finally:
        await conn.close()


async def main() -> None:
    exchange = make_exchange()
    logger.info(f"Exchange: {EXCHANGE_NAME} | Symbols: {SYMBOLS}")
    tasks = []
    for sym in SYMBOLS:
        tasks.append(asyncio.create_task(watch_ohlcv(exchange, sym.strip())))
        tasks.append(asyncio.create_task(watch_trades(exchange, sym.strip())))
    try:
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())
