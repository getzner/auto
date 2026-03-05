"""
absorption_backtest.py — Backtest Absorption Reversals
Simulates trades based on high delta absorption at key structural levels (POC, VAH, VAL).
"""

import asyncio
import pandas as pd
import numpy as np
from loguru import logger
from data.db import get_db_conn
from data.indicators import get_candles

async def run_absorption_backtest(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    days: int = 14,
    sl_pct: float = 0.01,
    tp_pct: float = 0.02
):
    """
    Backtests the hypothesis: 
    High Delta near VAH/VAL/POC + subsequent price rejection = high probability reversal.
    """
    conn = await get_db_conn()
    try:
        # 1. Fetch historical data joined with volume delta
        # We join on ts and symbol
        rows = await conn.fetch(
            """
            SELECT c.ts, c.open, c.high, c.low, c.close, c.volume, 
                   vd.net_delta, vd.cvd, vd.volume_spike
            FROM candles c
            LEFT JOIN volume_delta vd ON c.ts = vd.ts AND c.symbol = vd.symbol AND vd.timeframe = $2
            WHERE c.symbol = $1 AND c.timeframe = $2
            AND c.ts >= NOW() - $3 * INTERVAL '1 day'
            ORDER BY c.ts ASC
            """,
            symbol, timeframe, days
        )
        
        # 2. Fetch volume profile snapshots (we'll use the one active at time t)
        vp_rows = await conn.fetch(
            """
            SELECT ts_start, ts_end, poc, vah, val
            FROM volume_profile
            WHERE symbol = $1 AND session = '1d'
            ORDER BY ts_start ASC
            """,
            symbol
        )
    finally:
        await conn.close()

    if not rows or not vp_rows:
        return {"error": "Insufficient data in DB for absorption backtest"}

    df = pd.DataFrame([dict(r) for r in rows])
    vp_df = pd.DataFrame([dict(r) for r in vp_rows])

    trades = []
    in_trade = None # 'long' | 'short' | None
    entry_price = 0
    sl_price = 0
    tp_price = 0

    logger.info(f"[BACKTEST] Starting absorption analysis on {len(df)} candles...")

    for i in range(1, len(df)):
        row = df.iloc[i]
        ts = row["ts"]
        
        # Find active VP for this timestamp
        current_vp = vp_df[vp_df["ts_start"] <= ts].tail(1)
        if current_vp.empty:
            continue
        
        vah = float(current_vp["vah"].iloc[0])
        val = float(current_vp["val"].iloc[0])
        poc = float(current_vp["poc"].iloc[0])
        
        price = float(row["close"])
        delta = float(row["net_delta"] or 0)
        
        if not in_trade:
            # ── Check for Buy Absorption at Highs (Bearish Signal) ──
            # Positive delta at VAH but price doesn't break out
            dist_vah = abs(price - vah) / vah
            if dist_vah < 0.005 and delta > 0:
                # Potential short entry on next candle
                entry_price = float(df.iloc[i]["close"])
                sl_price = entry_price * (1 + sl_pct)
                tp_price = entry_price * (1 - tp_pct)
                in_trade = 'short'
                entry_ts = ts
                
            # ── Check for Sell Absorption at Lows (Bullish Signal) ──
            # Negative delta at VAL but price holds
            dist_val = abs(price - val) / val
            if dist_val < 0.005 and delta < 0:
                # Potential long entry on next candle
                entry_price = float(df.iloc[i]["close"])
                sl_price = entry_price * (1 - sl_pct)
                tp_price = entry_price * (1 + tp_pct)
                in_trade = 'long'
                entry_ts = ts
        else:
            # ── Manage Trade ──
            high = float(row["high"])
            low = float(row["low"])
            
            if in_trade == 'long':
                if low <= sl_price:
                    trades.append({"type": "long", "result": "SL", "pnl": -sl_pct, "entry_ts": entry_ts, "exit_ts": ts})
                    in_trade = None
                elif high >= tp_price:
                    trades.append({"type": "long", "result": "TP", "pnl": tp_pct, "entry_ts": entry_ts, "exit_ts": ts})
                    in_trade = None
            elif in_trade == 'short':
                if high <= tp_price: # wait, short TP is low
                    pass
                if high >= sl_price:
                    trades.append({"type": "short", "result": "SL", "pnl": -sl_pct, "entry_ts": entry_ts, "exit_ts": ts})
                    in_trade = None
                elif low <= tp_price:
                    trades.append({"type": "short", "result": "TP", "pnl": tp_pct, "entry_ts": entry_ts, "exit_ts": ts})
                    in_trade = None

    if not trades:
        return {"n_trades": 0, "msg": "No absorption triggers found in this period."}

    # ── Summary ──────────────────────────────────────────
    n = len(trades)
    wins = len([t for t in trades if t["result"] == "TP"])
    wr = wins / n
    total_pnl = sum(t["pnl"] for t in trades)

    result = {
        "symbol": symbol,
        "n_trades": n,
        "win_rate": round(wr * 100, 1),
        "total_pnl_pct": round(total_pnl * 100, 2),
        "trades": trades[-5:] # last 5 trades
    }
    
    logger.info(f"[BACKTEST] Done: {n} trades, {wr:.1%} winrate, {total_pnl*100:.1f}% PnL")
    return result

if __name__ == "__main__":
    import sys, json
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
    res = asyncio.run(run_absorption_backtest(sym))
    print(json.dumps(res, indent=2, default=str))
