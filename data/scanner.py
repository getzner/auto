"""
scanner.py — Event-Driven Market Scanner
Runs every 5 minutes per symbol and fires the full agent pipeline
when 2+ market triggers are detected.

Triggers:
  • Volume spike   — volume > 150% of 20-period average
  • RSI extreme    — RSI < 35 or RSI > 65
  • CVD shift      — sudden CVD direction reversal
  • Key level      — price within 0.5% of POC, VAH, or VAL
  • Funding rate   — |funding| > 0.05% (squeeze risk)
"""

from __future__ import annotations
import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from loguru import logger
from data.db import get_db_conn
from utils.config import get_env_string, get_env_int, get_env_float

# ── Configurable thresholds ────────────────────────────────────────────
SCAN_INTERVAL_S        = get_env_int("SCAN_INTERVAL",     300)
TRIGGER_THRESHOLD      = get_env_int("SCAN_TRIGGERS",     2)
COOLDOWN_MINUTES       = get_env_int("SCAN_COOLDOWN_MIN", 30)
MAX_CYCLES_PER_DAY     = get_env_int("SCAN_MAX_PER_DAY",  4)
HOURLY_FALLBACK        = get_env_string("SCAN_HOURLY_FALLBACK", "true").lower() == "true"

VOLUME_SPIKE_PCT       = get_env_float("SCAN_VOL_SPIKE",  1.5)
RSI_OVERSOLD           = get_env_float("SCAN_RSI_LOW",    35.0)
RSI_OVERBOUGHT         = get_env_float("SCAN_RSI_HIGH",   65.0)
KEY_LEVEL_DIST_PCT     = get_env_float("SCAN_LEVEL_DIST", 0.005)
FUNDING_THRESHOLD      = get_env_float("SCAN_FUNDING",    0.0005)

_scanner_active = False

def is_scanner_running() -> bool:
    return _scanner_active

# ── In-memory cooldown tracker ─────────────────────────────────────────
_last_trigger: dict[str, datetime] = {}   # symbol → last fire time
_daily_cycles: dict[str, int]      = {}   # symbol → today's count
_last_hourly:  dict[str, datetime] = {}   # symbol → last hourly fallback


# ── Individual trigger checks ──────────────────────────────────────────

async def _check_volume_spike(symbol: str, conn) -> tuple[bool, str]:
    """Volume > 150% of 20-period average."""
    rows = await conn.fetch(
        # M3 FIX: was 'ohlcv', data is written to 'candles' by market_data.py
        """SELECT volume FROM candles
           WHERE symbol=$1 AND timeframe='1h'
           ORDER BY ts DESC LIMIT 21""",
        symbol,
    )
    if len(rows) < 21:
        return False, ""
    current_vol = float(rows[0]["volume"])
    avg_vol     = sum(float(r["volume"]) for r in rows[1:]) / 20
    if avg_vol == 0:
        return False, ""
    ratio = current_vol / avg_vol
    triggered = ratio >= VOLUME_SPIKE_PCT
    msg = f"volume {ratio:.1f}x avg" if triggered else ""
    return triggered, msg


async def _check_rsi_extreme(symbol: str, conn) -> tuple[bool, str]:
    """RSI < 35 (oversold) or RSI > 65 (overbought)."""
    try:
        from data.indicators import get_indicators
        data = await get_indicators(symbol, timeframe="1h", n=30)
        rsi = data.get("rsi")
        if rsi is None:
            return False, ""
        if rsi < RSI_OVERSOLD:
            return True, f"RSI={rsi:.1f} oversold"
        if rsi > RSI_OVERBOUGHT:
            return True, f"RSI={rsi:.1f} overbought"
    except Exception as e:
        logger.warning(f"[SCANNER] Error checking RSI for {symbol}: {e}")
    return False, ""


async def _check_cvd_shift(symbol: str, conn) -> tuple[bool, str]:
    """CVD changed direction in the last 2 candles."""
    try:
        rows = await conn.fetch(
            """SELECT net_delta FROM volume_delta
               WHERE symbol=$1 AND timeframe='1h'
               ORDER BY ts DESC LIMIT 3""",
            symbol,
        )
        if len(rows) < 3:
            return False, ""
        d0, d1, d2 = float(rows[0]["net_delta"]), float(rows[1]["net_delta"]), float(rows[2]["net_delta"])
        # Detect reversal: was negative, now positive (or vice versa)
        was_negative = d2 < 0 and d1 < 0
        now_positive = d0 > 0
        was_positive = d2 > 0 and d1 > 0
        now_negative = d0 < 0
        if (was_negative and now_positive) or (was_positive and now_negative):
            direction = "↑" if now_positive else "↓"
            return True, f"CVD shift {direction} delta={d0:.0f}"
    except Exception as e:
        logger.warning(f"[SCANNER] Error checking CVD shift for {symbol}: {e}")
    return False, ""


async def _check_key_level(symbol: str, conn) -> tuple[bool, str]:
    """Price within 0.5% of POC, VAH, or VAL."""
    try:
        price_row = await conn.fetchrow(
            # M3 FIX: was 'ohlcv', data is written to 'candles' by market_data.py
            """SELECT close FROM candles
               WHERE symbol=$1 AND timeframe='1h'
               ORDER BY ts DESC LIMIT 1""",
            symbol,
        )
        if not price_row:
            return False, ""
        price = float(price_row["close"])

        profile_row = await conn.fetchrow(
            """SELECT poc, vah, val FROM volume_profile
               WHERE symbol=$1 ORDER BY ts DESC LIMIT 1""",
            symbol,
        )
        if not profile_row:
            return False, ""

        for level_name, level_val in [
            ("POC", profile_row["poc"]),
            ("VAH", profile_row["vah"]),
            ("VAL", profile_row["val"]),
        ]:
            if level_val is None:
                continue
            level = float(level_val)
            dist = abs(price - level) / level
            if dist <= KEY_LEVEL_DIST_PCT:
                return True, f"price within {dist:.2%} of {level_name} ${level:,.0f}"
    except Exception as e:
        logger.warning(f"[SCANNER] Error checking key level for {symbol}: {e}")
    return False, ""


async def _check_funding_rate(symbol: str) -> tuple[bool, str]:
    """|funding| > 0.05% (squeeze risk)."""
    try:
        from data.onchain import fetch_bybit_funding
        bybit_sym = symbol.replace("/", "")
        data = await fetch_bybit_funding(bybit_sym)
        if not data:
            return False, ""
        # data["funding_rate"] is in %, e.g. 0.01 for 0.01%
        fr = data["funding_rate"]
        if abs(fr) >= FUNDING_THRESHOLD * 100:
            return True, f"funding extreme: {fr:.3f}%"
    except Exception as e:
        logger.error(f"[SCANNER] Funding check error for {symbol}: {e}")
    return False, ""


async def _check_absorption(symbol: str, conn) -> tuple[bool, str]:
    """Check for market absorption/exhaustion at key levels."""
    try:
        from data.absorption import detect_absorption
        res = await detect_absorption(symbol)
        if res.get("magic_entry_recommended"):
            # Find the strongest signal description
            signals = res.get("signals", [])
            msg = signals[0]["description"] if signals else "Absorption detected"
            return True, f"✨ MAGIC ENTRY: {msg}"
    except Exception as e:
        logger.error(f"[SCANNER] Absorption check error: {e}")
    return False, ""


# ── Cooldown helpers ───────────────────────────────────────────────────

def _is_on_cooldown(symbol: str) -> bool:
    last = _last_trigger.get(symbol)
    if last is None:
        return False
    return (datetime.now(timezone.utc) - last).total_seconds() < COOLDOWN_MINUTES * 60


def _daily_limit_reached(symbol: str) -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    key   = f"{symbol}_{today}"
    return _daily_cycles.get(key, 0) >= MAX_CYCLES_PER_DAY


def _record_trigger(symbol: str) -> None:
    now   = datetime.now(timezone.utc)
    today = now.date().isoformat()
    key   = f"{symbol}_{today}"
    _last_trigger[symbol]    = now
    _daily_cycles[key]       = _daily_cycles.get(key, 0) + 1


def _should_hourly_fallback(symbol: str) -> bool:
    """Return True if 1h has passed since last cycle (safety net)."""
    if not HOURLY_FALLBACK:
        return False
    last = _last_hourly.get(symbol)
    if last is None:
        return True
    return (datetime.now(timezone.utc) - last).total_seconds() >= 3600


# ── Main scanner ──────────────────────────────────────────────────────

async def scan_symbol(symbol: str) -> list[str]:
    """
    Run all trigger checks for one symbol.
    Returns list of active trigger descriptions.
    """
    triggers = []
    conn = await get_db_conn()
    try:
        checks = await asyncio.gather(
            _check_volume_spike(symbol, conn),
            _check_rsi_extreme(symbol, conn),
            _check_cvd_shift(symbol, conn),
            _check_key_level(symbol, conn),
            _check_absorption(symbol, conn),
            return_exceptions=True,
        )
        for result in checks:
            if isinstance(result, Exception):
                continue
            hit, msg = result
            if hit:
                triggers.append(msg)
    finally:
        await conn.close()

    # Funding check (external API — no DB conn needed)
    hit, msg = await _check_funding_rate(symbol)
    if hit:
        triggers.append(msg)

    return triggers


async def scanner_loop(symbols: list[str]) -> None:
    """
    Main scanner loop — runs every SCAN_INTERVAL_S seconds.
    Fires run_cycle() when 2+ triggers detected.
    """
    from agents.orchestrator import run_cycle

    global _scanner_active, VOLUME_SPIKE_PCT, TRIGGER_THRESHOLD
    _scanner_active = True
    logger.info(
        f"[SCANNER] 🔍 Started "
        f"(interval={SCAN_INTERVAL_S}s, threshold={TRIGGER_THRESHOLD} triggers, "
        f"cooldown={COOLDOWN_MINUTES}m)"
    )

    while True:
        await asyncio.sleep(SCAN_INTERVAL_S)

        # Update dynamic thresholds from DB
        conn = await get_db_conn()
        try:
            row = await conn.fetchrow("SELECT value FROM system_config WHERE key = 'scanner_thresholds'")
            if row:
                t = json.loads(row["value"])
                # We use globals here to override the default constants for this module
                if "volume_spike_multi" in t:
                    VOLUME_SPIKE_PCT = float(t["volume_spike_multi"])
                if "trigger_threshold" in t:
                    TRIGGER_THRESHOLD = int(t["trigger_threshold"])
        except Exception as e:
            logger.error(f"[SCANNER] Threshold update error: {e}")
        finally:
            await conn.close()

        for symbol in symbols:
            symbol = symbol.strip()

            # ── Hourly fallback ────────────────────────────
            if _should_hourly_fallback(symbol) and not _daily_limit_reached(symbol):
                logger.info(f"[SCANNER] ⏰ Hourly fallback → {symbol}")
                _last_hourly[symbol] = datetime.now(timezone.utc)
                _record_trigger(symbol)
                asyncio.create_task(_safe_run_cycle(symbol, run_cycle, reason="hourly"))
                continue

            # ── Event-driven triggers ─────────────────────
            if _is_on_cooldown(symbol):
                remain = int(COOLDOWN_MINUTES * 60 - (
                    datetime.now(timezone.utc) - _last_trigger[symbol]
                ).total_seconds())
                logger.debug(f"[SCANNER] {symbol} on cooldown ({remain}s remaining)")
                continue

            if _daily_limit_reached(symbol):
                logger.debug(f"[SCANNER] {symbol} daily limit reached")
                continue

            triggers = await scan_symbol(symbol)

            if len(triggers) >= TRIGGER_THRESHOLD:
                logger.info(
                    f"[SCANNER] 🚨 {symbol} — {len(triggers)} triggers: "
                    + " | ".join(triggers)
                )
                _record_trigger(symbol)
                asyncio.create_task(
                    _safe_run_cycle(symbol, run_cycle, reason=", ".join(triggers))
                )
            else:
                logger.debug(
                    f"[SCANNER] {symbol} — {len(triggers)}/{TRIGGER_THRESHOLD} triggers "
                    + ("(" + " | ".join(triggers) + ")" if triggers else "(none)")
                )


async def _safe_run_cycle(symbol: str, run_cycle, reason: str) -> None:
    """Run cycle with error handling."""
    logger.info(f"[SCANNER] ▶ Firing pipeline for {symbol} | reason: {reason}")
    try:
        await run_cycle(symbol)
        logger.info(f"[SCANNER] ✅ Cycle complete for {symbol}")
    except Exception as e:
        logger.error(f"[SCANNER] ❌ Cycle failed for {symbol}: {e}")


def is_scanner_running() -> bool:
    """Check if scanner loop is active."""
    return _scanner_active

def start_scanner(symbols: list[str]) -> asyncio.Task | None:
    """Start scanner as background task — call from server lifespan."""
    if is_scanner_running():
        logger.warning("[SCANNER] Already running, skipping duplicate start.")
        return None
    return asyncio.create_task(scanner_loop(symbols))
