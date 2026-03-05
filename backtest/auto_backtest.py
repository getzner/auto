"""
auto_backtest.py — Autonomous Backtesting Engine
Agents can call this to test any strategy rule on historical data.
Strategy is defined as a dict of conditions — no code required from agent.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from loguru import logger

from data.indicators import get_candles, calc_rsi, calc_bollinger, calc_macd, calc_atr
from data.db import get_db_conn


# ── Strategy format ───────────────────────────────────────
# A strategy is a dict with:
#   entry_conditions: list of condition dicts
#   direction: "long" | "short"
#   stop_loss_pct: float  (e.g. 0.02 = 2%)
#   take_profit_pct: float (e.g. 0.04 = 4%)
#
# Condition format:
#   {"indicator": "rsi_14", "op": "<", "value": 30}
#   {"indicator": "bb_pct_b", "op": "<", "value": 0.1}
#   {"indicator": "close", "op": ">", "value": "vwap"}

CONDITION_OPS = {
    "<":  lambda a, b: a < b,
    ">":  lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
}


def _evaluate_condition(row: dict, condition: dict) -> bool:
    indicator = condition["indicator"]
    op        = condition["op"]
    value     = condition["value"]

    lhs = row.get(indicator)
    rhs = row.get(value) if isinstance(value, str) else value

    if lhs is None or rhs is None:
        return False
    try:
        return CONDITION_OPS[op](float(lhs), float(rhs))
    except (ValueError, KeyError):
        return False


async def run_backtest(
    strategy: dict,
    symbol:   str  = "BTC/USDT",
    timeframe: str = "1h",
    limit: int     = 500,
) -> dict:
    """
    Run a strategy backtest on historical candles.

    Args:
        strategy: {
            "name": str,
            "direction": "long" | "short",
            "entry_conditions": [{"indicator": ..., "op": ..., "value": ...}],
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.04
        }
        symbol, timeframe, limit: data parameters

    Returns:
        dict with winrate, sharpe, max_drawdown, n_trades, avg_rr, trade_log
    """
    import pandas as pd
    import numpy as np

    # Fetch candles + compute indicators
    df = await get_candles(symbol, timeframe, limit)
    if df.empty or len(df) < 50:
        return {"error": "Insufficient candle data for backtest"}

    close = df["close"]
    rsi_series = calc_rsi(close)
    bb          = calc_bollinger(close)
    macd_df     = calc_macd(close)
    atr         = calc_atr(df)

    df["rsi_14"]     = rsi_series
    df["bb_upper"]   = bb["upper"]
    df["bb_lower"]   = bb["lower"]
    df["bb_pct_b"]   = bb["pct_b"]
    df["macd"]       = macd_df["macd"]
    df["macd_hist"]  = macd_df["histogram"]
    df["atr_14"]     = atr
    df["vwap"]       = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()

    direction      = strategy.get("direction", "long")
    sl_pct         = float(strategy.get("stop_loss_pct",   0.02))
    tp_pct         = float(strategy.get("take_profit_pct", 0.04))
    conditions     = strategy.get("entry_conditions", [])

    trades = []
    in_trade = False
    entry_price = 0.0
    sl_price = tp_price = 0.0

    for i in range(20, len(df) - 1):
        row = df.iloc[i].to_dict()

        if not in_trade:
            # Check entry conditions
            if all(_evaluate_condition(row, c) for c in conditions):
                entry_price = float(df["close"].iloc[i + 1])  # fill on next open
                if direction == "long":
                    sl_price = entry_price * (1 - sl_pct)
                    tp_price = entry_price * (1 + tp_pct)
                else:
                    sl_price = entry_price * (1 + sl_pct)
                    tp_price = entry_price * (1 - tp_pct)
                in_trade = True
        else:
            # Check exit
            high = float(df["high"].iloc[i])
            low  = float(df["low"].iloc[i])

            if direction == "long":
                if low <= sl_price:
                    trades.append({"result": "sl", "pnl_pct": -sl_pct})
                    in_trade = False
                elif high >= tp_price:
                    trades.append({"result": "tp", "pnl_pct": tp_pct})
                    in_trade = False
            else:
                if high >= sl_price:
                    trades.append({"result": "sl", "pnl_pct": -sl_pct})
                    in_trade = False
                elif low <= tp_price:
                    trades.append({"result": "tp", "pnl_pct": tp_pct})
                    in_trade = False

    if not trades:
        return {
            "strategy":  strategy.get("name", "unnamed"),
            "symbol":    symbol,
            "n_trades":  0,
            "winrate":   0,
            "note":      "No trades triggered. Relax entry conditions."
        }

    n         = len(trades)
    winners   = [t for t in trades if t["result"] == "tp"]
    winrate   = len(winners) / n
    pnl_list  = [t["pnl_pct"] for t in trades]
    avg_pnl   = np.mean(pnl_list)
    equity    = np.cumprod([1 + p for p in pnl_list])
    drawdowns = 1 - equity / np.maximum.accumulate(equity)
    max_dd    = float(np.max(drawdowns))
    avg_rr    = tp_pct / sl_pct
    sharpe    = (avg_pnl / (np.std(pnl_list) + 1e-9)) * (252 ** 0.5 / (8760 / len(pnl_list)) ** 0.5)

    result = {
        "strategy":        strategy.get("name", "unnamed"),
        "symbol":          symbol,
        "timeframe":       timeframe,
        "n_trades":        n,
        "winrate":         round(winrate, 3),
        "avg_pnl_pct":     round(avg_pnl * 100, 2),
        "max_drawdown":    round(max_dd, 3),
        "sharpe":          round(float(sharpe), 2),
        "avg_rr":          round(avg_rr, 1),
        "sl_pct":          sl_pct,
        "tp_pct":          tp_pct,
        "win_trades":      len(winners),
        "loss_trades":     n - len(winners),
        "assessment":      (
            "STRONG" if winrate > 0.60 and sharpe > 1.5 else
            "GOOD"   if winrate > 0.50 and sharpe > 1.0 else
            "WEAK"   if winrate > 0.40 else
            "REJECT"
        )
    }

    logger.info(
        f"[BACKTEST] {strategy.get('name')} | {symbol} | "
        f"n={n} winrate={winrate:.0%} sharpe={sharpe:.1f} dd={max_dd:.1%}"
    )
    return result


async def compare_strategies(strategies: list[dict], symbol: str = "BTC/USDT") -> list[dict]:
    """Run multiple strategies and rank by Sharpe ratio."""
    results = await asyncio.gather(*[run_backtest(s, symbol) for s in strategies])
    ranked = sorted(
        [r for r in results if "sharpe" in r],
        key=lambda x: x["sharpe"],
        reverse=True
    )
    return ranked
