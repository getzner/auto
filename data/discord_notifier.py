"""
discord_notifier.py — Discord Trade Notifications
Sends rich embed messages to a Discord channel when trades open/close.
Uses webhook URL (preferred) or bot token as fallback.
"""

import os
import aiohttp
from datetime import datetime, timezone
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")   # preferred
BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN", "")     # fallback
CHANNEL_ID  = os.getenv("DISCORD_CHANNEL_ID", "")

DISCORD_API = "https://discord.com/api/v10"

# Embed colours
COLOR_LONG    = 0x00C851   # green
COLOR_SHORT   = 0xFF4444   # red
COLOR_CLOSE_W = 0x00C851   # green  (profit)
COLOR_CLOSE_L = 0xFF4444   # red    (loss)
COLOR_INFO    = 0x33B5E5   # blue


async def _send_embed(embed: dict) -> None:
    """POST an embed — tries webhook first, falls back to bot token."""
    payload = {"embeds": [embed]}

    if WEBHOOK_URL:
        url, headers = WEBHOOK_URL, {"Content-Type": "application/json"}
    elif BOT_TOKEN and CHANNEL_ID:
        url     = f"{DISCORD_API}/channels/{CHANNEL_ID}/messages"
        headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
    else:
        logger.warning("[DISCORD] No webhook URL or bot token set — skipping")
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                if resp.status not in (200, 201, 204):
                    text = await resp.text()
                    logger.error(f"[DISCORD] Failed ({resp.status}): {text}")
                else:
                    logger.debug(f"[DISCORD] Notification sent (status={resp.status})")
    except Exception as e:
        logger.error(f"[DISCORD] Error sending notification: {e}")


async def notify_trade_open(
    symbol: str,
    side: str,
    fill_price: float,
    size_usdt: float,
    stop_loss: float | None,
    take_profit: float | None,
    position_id: int,
    decision_id: int | None,
) -> None:
    """Send a Discord embed when a new paper/live trade is opened."""
    direction = "🟢 LONG" if side == "long" else "🔴 SHORT"
    sl_str    = f"${stop_loss:,.2f}"  if stop_loss   else "—"
    tp_str    = f"${take_profit:,.2f}" if take_profit else "—"

    embed = {
        "title":       f"📈 Trade Opened — {direction} {symbol}",
        "color":       COLOR_LONG if side == "long" else COLOR_SHORT,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "fields": [
            {"name": "Symbol",       "value": symbol,                    "inline": True},
            {"name": "Direction",    "value": side.upper(),              "inline": True},
            {"name": "Fill Price",   "value": f"${fill_price:,.2f}",     "inline": True},
            {"name": "Size",         "value": f"${size_usdt:,.2f} USDT", "inline": True},
            {"name": "Stop Loss",    "value": sl_str,                    "inline": True},
            {"name": "Take Profit",  "value": tp_str,                    "inline": True},
        ],
        "footer": {"text": f"Position #{position_id} | Decision #{decision_id}"},
    }

    await _send_embed(embed)


async def notify_trade_close(
    symbol: str,
    side: str,
    entry_price: float,
    close_price: float,
    size_usdt: float,
    pnl: float,
    reason: str,
    position_id: int,
) -> None:
    """Send a Discord embed when a position is closed."""
    pnl_emoji  = "✅" if pnl >= 0 else "❌"
    pnl_str    = f"{pnl_emoji} ${pnl:+,.2f}"
    pnl_pct    = (pnl / size_usdt * 100) if size_usdt else 0
    color      = COLOR_CLOSE_W if pnl >= 0 else COLOR_CLOSE_L

    reason_labels = {
        "stop_loss":   "🛑 Stop Loss Hit",
        "take_profit": "🎯 Take Profit Hit",
        "manual":      "🤚 Manual Close",
        "signal":      "🔄 Signal Reversal",
    }
    reason_str = reason_labels.get(reason, reason.replace("_", " ").title())

    embed = {
        "title":     f"📉 Trade Closed — {symbol}",
        "color":     color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": [
            {"name": "Symbol",      "value": symbol,                    "inline": True},
            {"name": "Side",        "value": side.upper(),              "inline": True},
            {"name": "Reason",      "value": reason_str,                "inline": True},
            {"name": "Entry",       "value": f"${entry_price:,.2f}",   "inline": True},
            {"name": "Close",       "value": f"${close_price:,.2f}",   "inline": True},
            {"name": "P&L",         "value": f"{pnl_str} ({pnl_pct:+.2f}%)", "inline": True},
        ],
        "footer": {"text": f"Position #{position_id}"},
    }

    await _send_embed(embed)


async def notify_system(title: str, message: str, level: str = "info") -> None:
    """Send a general system notification (startup, errors, etc.)."""
    colors = {"info": COLOR_INFO, "warning": 0xFFBB33, "error": 0xFF4444}
    icons  = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}

    embed = {
        "title":       f"{icons.get(level, 'ℹ️')} {title}",
        "description": message,
        "color":       colors.get(level, COLOR_INFO),
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "footer":      {"text": "Trade Server"},
    }

    await _send_embed(embed)
