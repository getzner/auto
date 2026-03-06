"""
non_trade_evaluator.py
Evaluates rejected decisions to see if they were correct rejects or missed opportunities.
"""
import asyncio
from datetime import datetime, timezone
from loguru import logger

from data.db import get_db_session
from data.market_data import get_current_price

async def evaluate_pending_non_trades():
    """
    For every non_trade with outcome='pending',
    fetch current price and determine if the reject was correct.
    """
    try:
        async with get_db_session() as conn:
            pending = await conn.fetch("""
                SELECT id, symbol, direction, price_at_reject, ts, price_1h_later, price_4h_later, price_24h_later
                FROM non_trade_outcomes
                WHERE outcome = 'pending'
                  AND ts < NOW() - INTERVAL '1 hour'
            """)
            
            for row in pending:
                symbol       = row["symbol"]
                direction    = row["direction"]
                reject_price = row["price_at_reject"]
                
                age_hours    = (datetime.now(timezone.utc) - row["ts"]).total_seconds() / 3600
                
                current_price = await get_current_price(symbol)
                
                if not current_price or reject_price <= 0:
                    continue
                
                update_fields = {}
                # Fill in price checkpoints
                if age_hours >= 1  and not row["price_1h_later"]:
                    update_fields["price_1h_later"] = current_price
                if age_hours >= 4  and not row["price_4h_later"]:
                    update_fields["price_4h_later"] = current_price
                if age_hours >= 24 and not row["price_24h_later"]:
                    update_fields["price_24h_later"] = current_price
                
                # Determine outcome after 4 hours
                if age_hours >= 4 and (row["price_4h_later"] or "price_4h_later" in update_fields):
                    price_4h = row["price_4h_later"] or update_fields["price_4h_later"]
                    pct_change_4h = (price_4h - reject_price) / reject_price * 100
                    
                    bullish_rejected = direction == "BULLISH" and pct_change_4h < -1.5
                    bearish_rejected = direction == "BEARISH" and pct_change_4h > +1.5
                    
                    if bullish_rejected or bearish_rejected:
                        outcome = "correct_reject"    # ✅ goed gedaan
                    elif direction == "BULLISH" and pct_change_4h > 1.5:
                        outcome = "missed_opportunity" # ❌ had moeten traden
                    elif direction == "BEARISH" and pct_change_4h < -1.5:
                        outcome = "missed_opportunity"
                    else:
                        outcome = "neutral"            # prijs bewoog niet genoeg
                    
                    update_fields["outcome"] = outcome
                
                if update_fields:
                    set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(update_fields))
                    values = list(update_fields.values())
                    await conn.execute(
                        f"UPDATE non_trade_outcomes SET {set_clause} WHERE id=$1",
                        row["id"], *values
                    )
                    if "outcome" in update_fields:
                        logger.info(f"[NonTrade] Evaluated {symbol}: {update_fields['outcome']}")
    except Exception as e:
        logger.error(f"[NonTrade] Error evaluating non-trades: {e}")

async def run_evaluator_loop():
    logger.info("[NonTrade] Starting non-trade evaluator service")
    while True:
        await evaluate_pending_non_trades()
        await asyncio.sleep(600)  # run every 10 min

if __name__ == "__main__":
    asyncio.run(run_evaluator_loop())
