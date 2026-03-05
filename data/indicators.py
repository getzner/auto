"""
indicators.py — Technical Indicators for Smart Agents
Computed from candles in DB. Agents can request these via tools.
"""

import pandas as pd
import numpy as np
from loguru import logger
from data.db import get_db_conn


async def get_candles(symbol: str, timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
    """Fetch OHLCV candles from DB as DataFrame."""
    conn = await get_db_conn()
    try:
        rows = await conn.fetch(
            """SELECT ts, open, high, low, close, volume
               FROM candles
               WHERE symbol=$1 AND timeframe=$2
               ORDER BY ts DESC LIMIT $3""",
            symbol, timeframe, limit
        )
    finally:
        await conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    df = df.sort_values("ts").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_bollinger(series: pd.Series, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    sma = series.rolling(period).mean()
    std_dev = series.rolling(period).std()
    upper = sma + std * std_dev
    lower = sma - std * std_dev
    pct_b = (series - lower) / (upper - lower).replace(0, np.nan)
    return pd.DataFrame({"upper": upper, "mid": sma, "lower": lower, "pct_b": pct_b})


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return pd.DataFrame({"macd": macd, "signal": sig, "histogram": hist})


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cumvol = df["volume"].cumsum()
    cumtpvol = (typical * df["volume"]).cumsum()
    return cumtpvol / cumvol.replace(0, np.nan)

def calc_ema(series: pd.Series, period: int = 50) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high = df['high']
    low = df['low']
    close = df['close']
    
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    
    tr1 = pd.DataFrame(high - low)
    tr2 = pd.DataFrame(abs(high - close.shift(1)))
    tr3 = pd.DataFrame(abs(low - close.shift(1)))
    frames = [tr1, tr2, tr3]
    tr = pd.concat(frames, axis=1, join='inner').max(axis=1)
    atr = tr.rolling(period).mean()
    
    plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
    minus_di = abs(100 * (minus_dm.ewm(alpha=1/period).mean() / atr))
    dx = (abs(plus_di - minus_di) / abs(plus_di + minus_di)) * 100
    adx = ((dx.shift(1) * (period - 1)) + dx) / period
    adx_smooth = dx.ewm(alpha=1/period).mean()
    
    return pd.DataFrame({'adx': adx_smooth, 'plus_di': plus_di, 'minus_di': minus_di})


async def get_indicators(symbol: str, timeframe: str = "1h", limit: int = 100) -> dict:
    """
    Returns a dict of the latest indicator values for an agent.
    Used by agent tools.
    """
    df = await get_candles(symbol, timeframe, limit)
    if df.empty:
        return {"error": "No candle data available"}

    close = df["close"]
    rsi = calc_rsi(close)
    bb  = calc_bollinger(close)
    macd_df = calc_macd(close)
    atr = calc_atr(df)
    vwap = calc_vwap(df)

    latest = {
        "symbol":    symbol,
        "timeframe": timeframe,
        "close":     round(float(close.iloc[-1]), 2),
        "rsi_14":    round(float(rsi.iloc[-1]), 2) if not pd.isna(rsi.iloc[-1]) else None,
        "rsi_signal": (
            "oversold" if rsi.iloc[-1] < 30 else
            "overbought" if rsi.iloc[-1] > 70 else
            "neutral"
        ) if not pd.isna(rsi.iloc[-1]) else None,
        "bb_upper":  round(float(bb["upper"].iloc[-1]), 2) if not pd.isna(bb["upper"].iloc[-1]) else None,
        "bb_mid":    round(float(bb["mid"].iloc[-1]), 2)   if not pd.isna(bb["mid"].iloc[-1]) else None,
        "bb_lower":  round(float(bb["lower"].iloc[-1]), 2) if not pd.isna(bb["lower"].iloc[-1]) else None,
        "bb_pct_b":  round(float(bb["pct_b"].iloc[-1]), 3) if not pd.isna(bb["pct_b"].iloc[-1]) else None,
        "macd":      round(float(macd_df["macd"].iloc[-1]), 4)      if not pd.isna(macd_df["macd"].iloc[-1]) else None,
        "macd_signal": round(float(macd_df["signal"].iloc[-1]), 4)  if not pd.isna(macd_df["signal"].iloc[-1]) else None,
        "macd_hist": round(float(macd_df["histogram"].iloc[-1]), 4) if not pd.isna(macd_df["histogram"].iloc[-1]) else None,
        "atr_14":    round(float(atr.iloc[-1]), 2) if not pd.isna(atr.iloc[-1]) else None,
        "vwap":      round(float(vwap.iloc[-1]), 2) if not pd.isna(vwap.iloc[-1]) else None,
        "price_vs_vwap": (
            "above" if close.iloc[-1] > vwap.iloc[-1] else "below"
        ) if not pd.isna(vwap.iloc[-1]) else None,
        "candles_used": len(df),
    }

    logger.debug(f"[INDICATORS] {symbol} {timeframe} RSI={latest['rsi_14']} BB%={latest['bb_pct_b']}")
    return latest
