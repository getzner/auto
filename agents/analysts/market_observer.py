"""
market_observer.py — Featherweight agent to detect current market regime
"""
import json
import pandas as pd
from loguru import logger
from data.indicators import get_candles, calc_adx, calc_atr, calc_ema

async def get_market_regime(symbol: str) -> dict:
    """
    Analyzes higher timeframe (HTF) data to determine the current macro regime.
    Returns a dict with regime status and agent weighting recommendations.
    """
    # Fetch 4H candles for macro view
    df = await get_candles(symbol, timeframe="4h", limit=100)
    if df.empty or len(df) < 50:
        return {"regime": "UNKNOWN", "volatility": "UNKNOWN", "weights": {}}

    close = df["close"]
    
    # Calculate ADX for trend strength
    adx_df = calc_adx(df, period=14)
    current_adx = float(adx_df["adx"].iloc[-1])
    plus_di = float(adx_df["plus_di"].iloc[-1])
    minus_di = float(adx_df["minus_di"].iloc[-1])

    # Calculate ATR for volatility
    atr_series = calc_atr(df, period=14)
    current_atr = float(atr_series.iloc[-1])
    avg_atr = float(atr_series.rolling(30).mean().iloc[-1])
    
    # Calculate EMAs for trend direction
    ema50 = float(calc_ema(close, 50).iloc[-1])
    ema200 = float(calc_ema(close, 200).iloc[-1]) if len(df) >= 200 else ema50

    current_price = float(close.iloc[-1])

    # 1. Determine Volatility
    volatility = "HIGH" if current_atr > (avg_atr * 1.5) else "LOW" if current_atr < (avg_atr * 0.7) else "NORMAL"

    # 2. Determine Trend (Ranging vs Trending)
    # ADX > 25 means strong trend, < 20 means ranging
    if current_adx < 20:
        regime = "RANGING"
    elif current_adx > 25:
        if plus_di > minus_di and current_price > ema50:
            regime = "BULL_TREND"
        elif minus_di > plus_di and current_price < ema50:
            regime = "BEAR_TREND"
        else:
            regime = "TRENDING_MIXED"
    else:
        regime = "TRANSITION"

    # 3. Dynamic Weight Recommendations based on Regime
    # For instance, RSI/Mean-reversion is better in RANGING
    # Trend-following (Volume, Orderflow) is better in TRENDING
    weights = {"volume_analyst": 1.0, "orderflow_analyst": 1.0, "vp_analyst": 1.0, "news_analyst": 1.0, "onchain_analyst": 1.0, "gametheory_analyst": 1.0}
    
    if regime == "RANGING":
        weights["vp_analyst"] = 1.5  # Volume Profile works well in ranges (value area)
        weights["gametheory_analyst"] = 1.5 # Liquidity hunting at range extremes
        weights["volume_analyst"] = 0.7 # Breakouts fail often
    elif regime in ["BULL_TREND", "BEAR_TREND"]:
        weights["volume_analyst"] = 1.5  # Trend riding
        weights["orderflow_analyst"] = 1.2
        weights["vp_analyst"] = 0.8
        
    if volatility == "HIGH":
        # News is often the driver of high vol, let's value its context
        weights["news_analyst"] = 1.5
        weights["orderflow_analyst"] = 1.5 # Micro-structure is key during high vol
        weights["gametheory_analyst"] = 2.0 # Whales manipulate highest during volatility

    report = {
        "regime": regime,
        "volatility": volatility,
        "metrics": {
            "adx_14": round(current_adx, 2),
            "atr_14": round(current_atr, 2),
            "price": current_price,
            "ema50": round(ema50, 2)
        },
        "weights": weights
    }
    
    logger.info(f"[OBSERVER] 🌍 Market Regime detected for {symbol}: {regime} (Vol: {volatility}, ADX: {round(current_adx,1)})")
    
    # Store in Redis for dashboard viewing
    try:
        from data.redis_client import get_redis
        redis_client = get_redis()
        if redis_client:
            redis_client.set(f"regime:{symbol}", json.dumps(report))
    except Exception as e:
        logger.error(f"[OBSERVER] Failed to save regime to redis: {e}")
        
    return report
