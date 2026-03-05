"""
volume.py — CVD & Volume Delta Calculator
Reads raw trades from PostgreSQL, computes per-candle volume delta and
cumulative volume delta (CVD), detects volume spikes, and stores results.
"""

import asyncio
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
from loguru import logger

from data.db import get_db_conn


async def compute_volume_delta(
    symbol: str,
    timeframe: str = "1h",
    lookback_candles: int = 200,
) -> pd.DataFrame:
    """
    Compute CVD, buy/sell volume, net delta per candle.

    Returns a DataFrame with columns:
        ts, buy_volume, sell_volume, net_delta, cvd, volume_spike
    """
    conn = await get_db_conn()
    try:
        # Fetch candles to determine time buckets
        candles = await conn.fetch(
            """
            SELECT ts FROM candles
            WHERE symbol=$1 AND timeframe=$2
            ORDER BY ts DESC LIMIT $3
            """,
            symbol, timeframe, lookback_candles,
        )
        if not candles:
            logger.warning(f"No candles found for {symbol} {timeframe}")
            return pd.DataFrame()

        oldest_ts = candles[-1]["ts"]

        # Fetch raw trades within the lookback window
        trades = await conn.fetch(
            """
            SELECT ts, price, amount, taker_side
            FROM trades_raw
            WHERE symbol=$1 AND ts >= $2
            ORDER BY ts ASC
            """,
            symbol, oldest_ts,
        )
    finally:
        await conn.close()

    if not trades:
        logger.warning(f"No raw trades found for {symbol} since {oldest_ts}")
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in trades],
                      columns=["ts", "price", "amount", "taker_side"])  # asyncpg → named columns
    df["ts"]     = pd.to_datetime(df["ts"], utc=True)
    df["price"]  = df["price"].astype(float)   # asyncpg NUMERIC → float
    df["amount"] = df["amount"].astype(float)  # asyncpg NUMERIC → float
    df["buy_vol"]  = np.where(df["taker_side"] == "buy",  df["amount"], 0.0)
    df["sell_vol"] = np.where(df["taker_side"] == "sell", df["amount"], 0.0)

    # Resample to timeframe bucket
    freq_map = {"1h": "1h", "4h": "4h", "1d": "1D"}
    freq = freq_map.get(timeframe, "1h")
    df = df.set_index("ts").resample(freq).agg(
        buy_volume  = ("buy_vol",  "sum"),
        sell_volume = ("sell_vol", "sum"),
    ).reset_index()

    df["net_delta"] = df["buy_volume"] - df["sell_volume"]
    df["cvd"]       = df["net_delta"].cumsum()

    # Volume spike: net_delta > 2 standard deviations from rolling mean
    roll_std = df["net_delta"].rolling(20, min_periods=5).std()
    roll_mean = df["net_delta"].rolling(20, min_periods=5).mean()
    df["volume_spike"] = abs(df["net_delta"] - roll_mean) > (2 * roll_std)

    return df


async def save_volume_delta(symbol: str, timeframe: str = "1h") -> None:
    """Compute and upsert volume delta rows into the DB."""
    df = await compute_volume_delta(symbol, timeframe)
    if df.empty:
        return

    conn = await get_db_conn()
    try:
        await conn.executemany(
            """
            INSERT INTO volume_delta
                (symbol, timeframe, ts, buy_volume, sell_volume, net_delta, cvd, volume_spike)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (symbol, timeframe, ts) DO UPDATE
                SET buy_volume=EXCLUDED.buy_volume,
                    sell_volume=EXCLUDED.sell_volume,
                    net_delta=EXCLUDED.net_delta,
                    cvd=EXCLUDED.cvd,
                    volume_spike=EXCLUDED.volume_spike
            """,
            [
                (symbol, timeframe, row.ts, row.buy_volume, row.sell_volume,
                 row.net_delta, row.cvd, bool(row.volume_spike))
                for row in df.itertuples()
            ],
        )
        logger.info(f"[VOLUME] Saved {len(df)} rows for {symbol} {timeframe}")
    finally:
        await conn.close()


async def get_volume_summary(symbol: str, timeframe: str = "1h", n: int = 20) -> dict:
    """
    Return a human-readable summary dict for the Volume Analyst agent.
    Covers the last N candles.
    """
    conn = await get_db_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT ts, buy_volume, sell_volume, net_delta, cvd, volume_spike
            FROM volume_delta
            WHERE symbol=$1 AND timeframe=$2
            ORDER BY ts DESC LIMIT $3
            """,
            symbol, timeframe, n,
        )
    finally:
        await conn.close()

    if not rows:
        return {}

    df = pd.DataFrame([dict(r) for r in rows]).sort_values("ts")  # asyncpg → named columns
    recent  = df.tail(3)
    spikes  = df[df["volume_spike"]]

    return {
        "symbol":          symbol,
        "timeframe":       timeframe,
        "candles_analyzed": len(df),
        "current_cvd":     float(df["cvd"].iloc[-1]),
        "cvd_trend":       "rising" if df["cvd"].iloc[-1] > df["cvd"].iloc[0] else "falling",
        "last_3_net_delta": recent["net_delta"].tolist(),
        "last_3_buy_vol":   recent["buy_volume"].tolist(),
        "last_3_sell_vol":  recent["sell_volume"].tolist(),
        "spike_count_last_20": int(df["volume_spike"].sum()),
        "latest_spike":    spikes["ts"].iloc[-1].isoformat() if not spikes.empty else None,
        "dominant_side":   "buyers" if df["net_delta"].sum() > 0 else "sellers",
    }


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
    result = asyncio.run(get_volume_summary(sym))
    print(result)
