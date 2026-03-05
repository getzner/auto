"""
onchain.py — Market Sentiment & On-chain Data (Free Sources)
Sources:
  - Bybit API:        funding rates, open interest, long/short ratio (free, no key)
  - Alternative.me:  Fear & Greed Index (completely free, no key)
  - Coinglass:       liquidations, funding, OI (free tier, optional key)
"""

import asyncio
import os
import json
import time
from datetime import datetime, timezone, timedelta

import aiohttp
from loguru import logger
from dotenv import load_dotenv

from data.db import get_db_conn

load_dotenv()

COINGLASS_KEY = os.getenv("COINGLASS_API_KEY", "")

BYBIT_BASE    = "https://api.bybit.com/v5"
FEAR_GREED_URL = "https://api.alternative.me/fng/"
COINGLASS_BASE = "https://open-api.coinglass.com/public/v2"

# ── M7: Coinglass circuit breaker ───────────────────────
# Coinglass frequently returns 5xx. After repeated failures we back off
# exponentially (up to 1h) instead of hammering their API and flooding logs.
_cg_failure_count: int   = 0
_cg_disabled_until: float = 0.0   # unix timestamp


# ── Fear & Greed Index (alternative.me — 100% free) ──────

async def fetch_fear_greed() -> dict | None:
    """Fetch Crypto Fear & Greed Index. Free, no API key."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(FEAR_GREED_URL, params={"limit": 2}, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                latest = data["data"][0]
                return {
                    "value":       int(latest["value"]),
                    "label":       latest["value_classification"],  # e.g. "Fear", "Greed"
                    "timestamp":   latest["timestamp"],
                }
    except Exception as e:
        logger.error(f"[ONCHAIN] Fear & Greed error: {e}")
        return None


# ── Bybit Market Data (free, no key needed for public endpoints) ──

async def fetch_bybit_funding(symbol: str = "BTCUSDT") -> dict | None:
    """Fetch current funding rate + predicted from Bybit."""
    url = f"{BYBIT_BASE}/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json()
                ticker = data.get("result", {}).get("list", [{}])[0]
                fr = float(ticker.get("fundingRate", 0))
                return {
                    "funding_rate":     round(fr * 100, 5),     # in %
                    "funding_annualized": round(fr * 3 * 365 * 100, 2),  # 3x/day × 365
                    "signal": "bearish" if fr > 0.01 else ("bullish" if fr < -0.005 else "neutral"),
                }
    except Exception as e:
        logger.error(f"[ONCHAIN] Bybit funding error: {e}")
        return None


async def fetch_bybit_open_interest(symbol: str = "BTCUSDT") -> dict | None:
    """Fetch open interest history from Bybit (last 2 data points → trend)."""
    url = f"{BYBIT_BASE}/market/open-interest"
    params = {"category": "linear", "symbol": symbol, "intervalTime": "1h", "limit": 5}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json()
                rows = data.get("result", {}).get("list", [])
                if len(rows) < 2:
                    return None
                latest   = float(rows[0]["openInterest"])
                previous = float(rows[-1]["openInterest"])
                change_pct = (latest - previous) / previous * 100
                return {
                    "open_interest_usd":    round(latest, 0),
                    "oi_change_pct_5h":     round(change_pct, 3),
                    "oi_trend":             "rising" if change_pct > 0.5 else ("falling" if change_pct < -0.5 else "stable"),
                }
    except Exception as e:
        logger.error(f"[ONCHAIN] Bybit OI error: {e}")
        return None


async def fetch_bybit_long_short(symbol: str = "BTCUSDT") -> dict | None:
    """Fetch long/short ratio from Bybit."""
    url = f"{BYBIT_BASE}/market/account-ratio"
    params = {"category": "linear", "symbol": symbol, "period": "1h", "limit": 3}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                resp.raise_for_status()
                data = await resp.json()
                rows = data.get("result", {}).get("list", [])
                if not rows:
                    return None
                latest = rows[0]
                buy_ratio = float(latest.get("buyRatio", 0.5))
                return {
                    "long_ratio":       round(buy_ratio * 100, 2),
                    "short_ratio":      round((1 - buy_ratio) * 100, 2),
                    "ls_signal":        "bullish" if buy_ratio > 0.55 else ("bearish" if buy_ratio < 0.45 else "neutral"),
                }
    except Exception as e:
        logger.error(f"[ONCHAIN] Bybit L/S error: {e}")
        return None


# ── Coinglass Liquidations (free tier, optional key) ─────

async def fetch_liquidations(symbol: str = "BTC") -> dict | None:
    """Fetch recent liquidation data from Coinglass (free tier).
    M7: Circuit breaker with exponential backoff on 5xx errors.
    """
    global _cg_failure_count, _cg_disabled_until
    
    if not COINGLASS_KEY:
        return None
    
    # Circuit breaker: skip if in cooldown
    if time.time() < _cg_disabled_until:
        remaining = int(_cg_disabled_until - time.time())
        logger.debug(f"[ONCHAIN] Coinglass circuit open — skipping for {remaining}s")
        return None
    
    url = f"{COINGLASS_BASE}/liquidation_chart"
    headers = {"coinglassSecret": COINGLASS_KEY}
    params  = {"symbol": symbol, "time_type": "h1", "limit": 4}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                if resp.status >= 500:
                    _cg_failure_count += 1
                    backoff = min(60 * (2 ** _cg_failure_count), 3600)  # max 1h
                    _cg_disabled_until = time.time() + backoff
                    logger.warning(
                        f"[ONCHAIN] Coinglass HTTP {resp.status} — "
                        f"circuit open for {backoff}s (attempt {_cg_failure_count})"
                    )
                    return None
                resp.raise_for_status()
                data = await resp.json()
                # Success: reset circuit breaker
                _cg_failure_count = 0
                _cg_disabled_until = 0.0
                rows = data.get("data", [])
                if not rows:
                    return None
                total_long_liq  = sum(float(r.get("longLiquidationUsd", 0)) for r in rows)
                total_short_liq = sum(float(r.get("shortLiquidationUsd", 0)) for r in rows)
                return {
                    "long_liq_4h_usd":  round(total_long_liq, 0),
                    "short_liq_4h_usd": round(total_short_liq, 0),
                    "dominant_liq":     "longs" if total_long_liq > total_short_liq else "shorts",
                }
    except aiohttp.ClientError as e:
        logger.warning(f"[ONCHAIN] Coinglass connection error: {e}")
        return None
    except Exception as e:
        logger.error(f"[ONCHAIN] Coinglass unexpected error: {e}")
        return None


# ── Collect & Save ────────────────────────────────────────

async def collect_and_save(symbol: str = "BTC/USDT") -> None:
    """Full market sentiment collection — run hourly.
    M5: Actually saves the result to Redis so get_onchain_summary can
    serve from cache instead of making duplicate live API calls.
    """
    base      = symbol.split("/")[0]
    bybit_sym = base + "USDT"

    fg, funding, oi, ls, liq = await asyncio.gather(
        fetch_fear_greed(),
        fetch_bybit_funding(bybit_sym),
        fetch_bybit_open_interest(bybit_sym),
        fetch_bybit_long_short(bybit_sym),
        fetch_liquidations(base),
    )

    logger.info(
        f"[ONCHAIN] {symbol} | "
        f"F&G={fg['value'] if fg else 'N/A'} "
        f"| funding={funding['funding_rate'] if funding else 'N/A'}% "
        f"| OI_trend={oi['oi_trend'] if oi else 'N/A'}"
    )

    # M5: Build summary and cache to Redis (TTL = 1h = 3600s)
    result: dict = {"symbol": symbol, "cached_at": datetime.now(timezone.utc).isoformat()}
    if fg:      result["fear_greed"]    = {"value": fg["value"], "label": fg["label"],
                    "signal": "bullish" if fg["value"] < 30 else ("bearish" if fg["value"] > 70 else "neutral")}
    if funding: result["funding"]        = funding
    if oi:      result["open_interest"]  = oi
    if ls:      result["long_short"]     = ls
    if liq:     result["liquidations"]   = liq

    try:
        from data.redis_client import get_redis
        get_redis().setex(f"onchain:{symbol}", 3600, json.dumps(result, default=str))
        logger.debug(f"[ONCHAIN] {symbol} cached in Redis (TTL=1h)")
    except Exception as e:
        logger.warning(f"[ONCHAIN] Redis cache write failed: {e}")


async def get_onchain_summary(symbol: str, lookback_hours: int = 24) -> dict:
    """Agent-ready market sentiment summary — all from free APIs.
    M5: Checks Redis cache first (set by collect_and_save) to avoid
    duplicate live API calls during the same orchestrator cycle.
    """
    # Check Redis cache first
    try:
        from data.redis_client import get_redis
        cached = get_redis().get(f"onchain:{symbol}")
        if cached:
            result = json.loads(cached)
            logger.debug(f"[ONCHAIN] {symbol} served from Redis cache")
            return result
    except Exception:
        pass  # Cache miss — fall through to live fetch

    base      = symbol.split("/")[0]
    bybit_sym = base + "USDT"

    fg, funding, oi, ls, liq = await asyncio.gather(
        fetch_fear_greed(),
        fetch_bybit_funding(bybit_sym),
        fetch_bybit_open_interest(bybit_sym),
        fetch_bybit_long_short(bybit_sym),
        fetch_liquidations(base),
    )

    result: dict = {"symbol": symbol}

    if fg:
        result["fear_greed"] = {
            "value":   fg["value"],
            "label":   fg["label"],
            "signal":  "bullish" if fg["value"] < 30 else ("bearish" if fg["value"] > 70 else "neutral"),
        }

    if funding:
        result["funding"] = funding

    if oi:
        result["open_interest"] = oi

    if ls:
        result["long_short"] = ls

    if liq:
        result["liquidations"] = liq

    if not any([fg, funding, oi, ls]):
        return {"symbol": symbol, "error": "no market data available"}

    return result


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
    result = asyncio.run(get_onchain_summary(sym))
    import json
    print(json.dumps(result, indent=2))
