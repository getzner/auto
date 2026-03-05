"""
orderflow.py — Footprint Candle & Orderflow Delta Engine
Reconstructs footprint candles from raw trades, calculates per-candle delta,
detects bid/ask imbalances, and provides agent-ready summaries.
"""

import asyncio
import json
from collections import defaultdict

import pandas as pd
import numpy as np
from loguru import logger

from data.db import get_db_conn

# Price bucket size — $10 per level  (override via config)
DEFAULT_TICK = 10.0
# Imbalance threshold: buy_vol / sell_vol > this = imbalance
IMBALANCE_THRESHOLD = 3.0


def _build_footprint(df: pd.DataFrame, tick_size: float = DEFAULT_TICK) -> dict:
    """
    Build a footprint candle from a dataframe of trades.

    Returns: {
        "footprint":  {price_level: {"buy": vol, "sell": vol}},
        "delta":      float,          # total buy_vol - sell_vol
        "buy_vol":    float,
        "sell_vol":   float,
        "imbalances": [{"price": ..., "ratio": ..., "side": "buy"|"sell"}]
    }
    """
    if df.empty:
        return {"footprint": {}, "delta": 0.0, "buy_vol": 0.0, "sell_vol": 0.0, "imbalances": []}

    df = df.copy()
    df["bucket"] = (df["price"] / tick_size).round() * tick_size

    footprint: dict[float, dict] = defaultdict(lambda: {"buy": 0.0, "sell": 0.0})
    for _, row in df.iterrows():
        side = "buy" if row["taker_side"] == "buy" else "sell"
        footprint[row["bucket"]][side] += float(row["amount"])

    total_buy  = sum(v["buy"]  for v in footprint.values())
    total_sell = sum(v["sell"] for v in footprint.values())
    delta = total_buy - total_sell

    # Detect imbalances: ratio of buy vs sell (or inverse) > threshold
    imbalances = []
    for price, vols in footprint.items():
        b, s = vols["buy"], vols["sell"]
        if s > 0 and b / s >= IMBALANCE_THRESHOLD:
            imbalances.append({"price": price, "ratio": round(b / s, 1), "side": "buy"})
        elif b > 0 and s / b >= IMBALANCE_THRESHOLD:
            imbalances.append({"price": price, "ratio": round(s / b, 1), "side": "sell"})

    return {
        "footprint":  {str(k): {"buy": round(v["buy"], 4), "sell": round(v["sell"], 4)}
                       for k, v in footprint.items()},
        "delta":      round(delta, 4),
        "buy_vol":    round(total_buy, 4),
        "sell_vol":   round(total_sell, 4),
        "imbalances": sorted(imbalances, key=lambda x: x["ratio"], reverse=True)[:10],
    }


async def compute_and_save_orderflow(
    symbol: str,
    timeframe: str = "1h",
    tick_size: float = DEFAULT_TICK,
    lookback: int = 50,
) -> None:
    """
    Compute footprint candles for the last `lookback` periods and upsert to DB.
    """
    conn = await get_db_conn()
    try:
        candle_rows = await conn.fetch(
            """
            SELECT ts FROM candles
            WHERE symbol=$1 AND timeframe=$2
            ORDER BY ts DESC LIMIT $3
            """,
            symbol, timeframe, lookback,
        )
        if not candle_rows:
            return

        oldest_ts = candle_rows[-1]["ts"]
        trades    = await conn.fetch(
            """
            SELECT ts, price, amount, taker_side FROM trades_raw
            WHERE symbol=$1 AND ts >= $2
            ORDER BY ts ASC LIMIT 50000
            """,
            symbol, oldest_ts,
        )
    finally:
        await conn.close()

    if not trades:
        return

    df = pd.DataFrame([dict(r) for r in trades])  # asyncpg → named columns
    df["ts"]     = pd.to_datetime(df["ts"], utc=True)
    df["price"]  = df["price"].astype(float)   # asyncpg NUMERIC → float
    df["amount"] = df["amount"].astype(float)  # asyncpg NUMERIC → float

    freq_map = {"1h": "1h", "4h": "4h", "1d": "1D"}
    freq = freq_map.get(timeframe, "1h")

    cumulative_delta = 0.0
    for period_start, group in df.groupby(pd.Grouper(key="ts", freq=freq)):
        if group.empty:
            continue
        fp = _build_footprint(group, tick_size=tick_size)
        cumulative_delta += fp["delta"]

        conn2 = await get_db_conn()
        try:
            await conn2.execute(
                """
                INSERT INTO orderflow
                    (symbol, timeframe, ts, delta, cumulative_delta, imbalances, footprint)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (symbol, timeframe, ts) DO UPDATE
                    SET delta=EXCLUDED.delta,
                        cumulative_delta=EXCLUDED.cumulative_delta,
                        imbalances=EXCLUDED.imbalances,
                        footprint=EXCLUDED.footprint
                """,
                symbol, timeframe, period_start,
                fp["delta"], cumulative_delta,
                json.dumps(fp["imbalances"]),
                json.dumps(fp["footprint"]),
            )
        finally:
            await conn2.close()

    logger.info(f"[ORDERFLOW] Updated {symbol} {timeframe} — cum_delta={cumulative_delta:.2f}")


async def get_orderflow_summary(symbol: str, timeframe: str = "1h", n: int = 10) -> dict:
    """
    Return structured orderflow summary for the Orderflow Analyst agent.
    """
    conn = await get_db_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT ts, delta, cumulative_delta, imbalances
            FROM orderflow
            WHERE symbol=$1 AND timeframe=$2
            ORDER BY ts DESC LIMIT $3
            """,
            symbol, timeframe, n,
        )
        price_row = await conn.fetchrow(
            "SELECT close FROM candles WHERE symbol=$1 ORDER BY ts DESC LIMIT 1",
            symbol,
        )
    finally:
        await conn.close()

    if not rows:
        return {}

    df = pd.DataFrame([dict(r) for r in rows]).sort_values("ts")  # asyncpg → named columns
    current_price = float(price_row["close"]) if price_row else None

    # Directional delta streak
    deltas = df["delta"].tolist()
    streak = 0
    sign = 1 if deltas[-1] >= 0 else -1
    for d in reversed(deltas):
        if (d >= 0) == (sign == 1):
            streak += 1
        else:
            break

    # Aggregate imbalance zones
    all_imbalances = []
    for row in rows[:3]:  # last 3 candles
        imbs = json.loads(row["imbalances"]) if row["imbalances"] else []
        all_imbalances.extend(imbs)

    return {
        "symbol":              symbol,
        "timeframe":           timeframe,
        "current_price":       current_price,
        "last_candle_delta":   float(df["delta"].iloc[-1]),
        "cumulative_delta":    float(df["cumulative_delta"].iloc[-1]),
        "delta_trend":         "positive" if df["delta"].iloc[-1] > 0 else "negative",
        "consecutive_streak":  streak,
        "streak_direction":    "buying" if sign == 1 else "selling",
        "recent_deltas":       [round(float(d), 2) for d in deltas[-5:]],
        "top_imbalances":      sorted(all_imbalances, key=lambda x: x["ratio"], reverse=True)[:5],
    }
