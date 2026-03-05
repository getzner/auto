"""
absorption.py — Market Exhaustion & Absorption Detection
Analyzes orderflow delta vs price action at key structural levels.
"""

import asyncio
import json
from loguru import logger
from data.db import get_db_conn
import pandas as pd
import numpy as np

async def detect_absorption(symbol: str, timeframe: str = "1h") -> dict:
    """
    Detect absorption at key levels (VAH, VAL, POC).
    
    Absorption = High Delta + Price compression at a key level.
    """
    conn = await get_db_conn()
    try:
        # 1. Get latest orderflow data (footprint, delta, imbalances)
        of_rows = await conn.fetch(
            """
            SELECT ts, delta, cumulative_delta, imbalances, footprint
            FROM orderflow
            WHERE symbol=$1 AND timeframe=$2
            ORDER BY ts DESC LIMIT 5
            """,
            symbol, timeframe
        )
        
        # 2. Get latest volume profile levels
        vp_row = await conn.fetchrow(
            """
            SELECT poc, vah, val
            FROM volume_profile
            WHERE symbol=$1 AND session='1d'
            ORDER BY ts_start DESC LIMIT 1
            """,
            symbol
        )
        
        # 3. Get latest candle
        candle = await conn.fetchrow(
            """
            SELECT high, low, close, open, volume
            FROM candles
            WHERE symbol=$1 AND timeframe='5m'
            ORDER BY ts DESC LIMIT 1
            """,
            symbol
        )
    finally:
        await conn.close()

    if not of_rows or not vp_row or not candle:
        return {"status": "insufficient_data"}

    # Convert to float
    current_price = float(candle["close"])
    vah = float(vp_row["vah"])
    val = float(vp_row["val"])
    poc = float(vp_row["poc"])
    
    latest_of = of_rows[0]
    delta = float(latest_of["delta"])
    
    # ── Absorption Logic ──────────────────────────────────
    signals = []
    
    proximity_threshold = 0.002 # 0.2% proximity to level
    
    # Sell Absorption (Bullish reversal potential)
    # Price at VAL or support, high negative delta, but price holds
    if abs(current_price - val) / val < proximity_threshold and delta < 0:
        # Check if delta is "high" (e.g., > 1 std dev or fixed threshold)
        # For now, use a simple threshold or ratio
        signals.append({
            "type": "SELL_ABSORPTION",
            "level": "VAL",
            "description": f"Price at VAL {val} with negative delta {delta}. Sellers being absorbed.",
            "strength": 7 if abs(delta) > 500 else 5
        })

    # Buy Absorption (Bearish reversal potential)
    # Price at VAH or resistance, high positive delta, but price fails to break
    if abs(current_price - vah) / vah < proximity_threshold and delta > 0:
        signals.append({
            "type": "BUY_ABSORPTION",
            "level": "VAH",
            "description": f"Price at VAH {vah} with positive delta {delta}. Buyers being absorbed.",
            "strength": 7 if delta > 500 else 5
        })

    # POC Interaction
    if abs(current_price - poc) / poc < proximity_threshold:
        side = "buyers" if delta > 0 else "sellers"
        signals.append({
            "type": "POC_BATTLE",
            "level": "POC",
            "description": f"High delta {delta} at POC {poc}. {side} struggling to shift value.",
            "strength": 5
        })

    # ── CVD Divergence ────────────────────────────────────
    # Simplified version: check if price trend != CVD trend over last 3-5 candles
    prices = [float(candle["close"])] # We'd need more candles for a real trend
    # (Implementation for divergence would require a bit more historical candle data)

    return {
        "symbol": symbol,
        "current_price": current_price,
        "levels": {"vah": vah, "val": val, "poc": poc},
        "latest_delta": delta,
        "signals": signals,
        "magic_entry_recommended": any(int(s.get("strength", 0)) >= 7 for s in signals)
    }

if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
    res = asyncio.run(detect_absorption(sym))
    print(json.dumps(res, indent=2))
