"""
volume_profile.py — Volume Profile Calculator
Builds POC, VAH/VAL, HVN/LVN from raw trade data per session.
Stores results in the volume_profile table.
"""

import asyncio
import json
from collections import defaultdict
from datetime import timezone

import pandas as pd
import numpy as np
from loguru import logger

from data.db import get_db_conn


def _build_profile(df: pd.DataFrame, tick_size: float = 10.0) -> dict:
    """
    Build a volume-at-price histogram from a trades DataFrame.

    Args:
        df:        DataFrame with columns [price, amount]
        tick_size: Size of each price bucket in USDT (default $10)

    Returns:
        {
            "profile": {price_level: volume, ...},
            "poc": float,
            "vah": float,
            "val": float,
            "total_volume": float,
        }
    """
    if df.empty:
        return {}

    df = df.copy()
    # Round price to nearest tick bucket
    df["bucket"] = (df["price"] / tick_size).round() * tick_size
    profile = df.groupby("bucket")["amount"].sum().to_dict()

    if not profile:
        return {}

    total_volume = sum(profile.values())
    poc = max(profile, key=profile.get)

    # Value Area: 70% of total volume around POC
    sorted_levels = sorted(profile.keys())
    vah, val = _compute_value_area(profile, sorted_levels, poc, total_volume, target_pct=0.70)

    return {
        "profile":      {str(k): float(v) for k, v in profile.items()},
        "poc":          float(poc),
        "vah":          float(vah),
        "val":          float(val),
        "total_volume": float(total_volume),
    }


def _compute_value_area(
    profile: dict, sorted_levels: list, poc: float,
    total_volume: float, target_pct: float = 0.70
) -> tuple[float, float]:
    """Expand outward from POC until 70% of volume is captured."""
    included_volume = profile.get(poc, 0.0)
    lo = hi = poc

    poc_idx = sorted_levels.index(poc)
    lo_idx  = poc_idx
    hi_idx  = poc_idx

    while included_volume / total_volume < target_pct:
        lo_candidate = sorted_levels[lo_idx - 1] if lo_idx > 0 else None
        hi_candidate = sorted_levels[hi_idx + 1] if hi_idx < len(sorted_levels) - 1 else None

        lo_vol = profile.get(lo_candidate, 0.0) if lo_candidate else 0.0
        hi_vol = profile.get(hi_candidate, 0.0) if hi_candidate else 0.0

        if lo_vol == 0 and hi_vol == 0:
            break

        if hi_vol >= lo_vol and hi_candidate:
            hi = hi_candidate
            hi_idx += 1
            included_volume += hi_vol
        elif lo_candidate:
            lo = lo_candidate
            lo_idx -= 1
            included_volume += lo_vol
        else:
            break

    return hi, lo   # VAH, VAL


async def compute_and_save_profile(
    symbol: str,
    session: str = "1d",
    tick_size: float = 10.0,
) -> dict:
    """
    Compute volume profile for the most recent completed session and save.

    session: '1h' | '4h' | '1d'
    """
    freq_map = {"1h": "1h", "4h": "4h", "1d": "1D"}
    freq = freq_map.get(session, "1D")

    conn = await get_db_conn()
    try:
        # Get last 1000 raw trades (enough for a daily profile)
        limit_map = {"1h": 500, "4h": 2000, "1d": 8000}
        limit = limit_map.get(session, 8000)
        rows = await conn.fetch(
            """
            SELECT ts, price, amount FROM trades_raw
            WHERE symbol=$1
            ORDER BY ts DESC LIMIT $2
            """,
            symbol, limit,
        )
    finally:
        await conn.close()

    if not rows:
        logger.warning(f"[VP] No trades for {symbol}")
        return {}

    df = pd.DataFrame([dict(r) for r in rows])  # asyncpg → named columns
    df["ts"]     = pd.to_datetime(df["ts"], utc=True)
    df["price"]  = df["price"].astype(float)   # asyncpg NUMERIC → float
    df["amount"] = df["amount"].astype(float)  # asyncpg NUMERIC → float
    df = df.sort_values("ts")

    # Group by session bucket
    groups = df.groupby(pd.Grouper(key="ts", freq=freq))
    result = None
    for period_start, group in groups:
        if group.empty:
            continue
        period_end = group["ts"].max()
        vp = _build_profile(group, tick_size=tick_size)
        if not vp:
            continue
        result = vp
        await _upsert_profile(symbol, session, period_start, period_end, vp)

    return result or {}


async def _upsert_profile(
    symbol: str, session: str,
    ts_start, ts_end, vp: dict,
) -> None:
    conn = await get_db_conn()
    try:
        await conn.execute(
            """
            INSERT INTO volume_profile
                (symbol, session, ts_start, ts_end, poc, vah, val, total_volume, profile_json)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (symbol, session, ts_start) DO UPDATE
                SET poc=EXCLUDED.poc, vah=EXCLUDED.vah, val=EXCLUDED.val,
                    total_volume=EXCLUDED.total_volume, profile_json=EXCLUDED.profile_json
            """,
            symbol, session, ts_start, ts_end,
            vp["poc"], vp["vah"], vp["val"], vp["total_volume"],
            json.dumps(vp["profile"]),
        )
    finally:
        await conn.close()


async def get_vp_summary(symbol: str) -> dict:
    """
    Return structured VP summary for the VP Analyst agent.
    Includes 1h, 4h, 1d POC/VAH/VAL and price-vs-value-area context.
    """
    conn = await get_db_conn()
    try:
        # Latest close price from candles
        price_row = await conn.fetchrow(
            "SELECT close FROM candles WHERE symbol=$1 ORDER BY ts DESC LIMIT 1",
            symbol,
        )
        current_price = float(price_row["close"]) if price_row else None

        sessions = {}
        for session in ["1h", "4h", "1d"]:
            row = await conn.fetchrow(
                """
                SELECT poc, vah, val, total_volume, ts_start
                FROM volume_profile
                WHERE symbol=$1 AND session=$2
                ORDER BY ts_start DESC LIMIT 1
                """,
                symbol, session,
            )
            if row:
                sessions[session] = {
                    "poc": float(row["poc"]),
                    "vah": float(row["vah"]),
                    "val": float(row["val"]),
                    "total_volume": float(row["total_volume"]),
                    "ts": row["ts_start"].isoformat(),
                }
    finally:
        await conn.close()

    if not current_price or not sessions:
        return {}

    context = {}
    for s, vp in sessions.items():
        inside_va = vp["val"] <= current_price <= vp["vah"]
        above_poc = current_price > vp["poc"]
        context[s] = {
            **vp,
            "price_vs_poc": "above" if above_poc else "below",
            "price_in_value_area": inside_va,
            "distance_to_poc_pct": round(
                (current_price - vp["poc"]) / vp["poc"] * 100, 3
            ),
        }

    return {
        "symbol":        symbol,
        "current_price": current_price,
        "profiles":      context,
    }
