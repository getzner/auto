"""
non_trade_evaluator.py
Evaluates rejected decisions to see if they were correct rejects or missed opportunities.
"""
import asyncio
from datetime import datetime, timezone
from loguru import logger

from data.db import get_db_session
from data.market_data import make_exchange

async def evaluate_pending_non_trades():
    """
    For every non_trade with outcome='pending',
    fetch current price and determine if the reject was correct.
    """
    exchange = None
    try:
        async with get_db_session() as conn:
            pending = await conn.fetch("""
                SELECT id, symbol, direction, price_at_reject, ts, price_1h_later, price_4h_later, price_24h_later, max_price_4h, min_price_4h
                FROM non_trade_outcomes
                WHERE outcome = 'pending'
            """)
            
            if not pending:
                return

            exchange = make_exchange()

            for row in pending:
                symbol       = row["symbol"]
                direction    = row["direction"]
                reject_price = row["price_at_reject"]
                
                age_hours    = (datetime.now(timezone.utc) - row["ts"]).total_seconds() / 3600
                
                try:
                    ticker = await exchange.fetch_ticker(symbol)
                    current_price = float(ticker['last'])
                except Exception as e:
                    logger.error(f"Error fetching ticker for {symbol}: {e}")
                    continue
                
                if not current_price or reject_price <= 0:
                    continue
                
                update_fields = {}
                # Fill in price checkpoints
                if age_hours >= 1  and not row["price_1h_later"]:
                    update_fields["price_1h_later"] = current_price
                if age_hours >= 4  and not row["price_4h_later"]:
                    update_fields["price_4h_later"] = current_price
                    
                if age_hours >= 4 and not row["max_price_4h"]:
                    try:
                        since_ms = int(row["ts"].timestamp() * 1000)
                        # Fetch 4 hours of 15m candles (16 candles)
                        ohlcv = await exchange.fetch_ohlcv(symbol, '15m', since=since_ms, limit=16)
                        if ohlcv:
                            update_fields["max_price_4h"] = float(max([c[2] for c in ohlcv]))
                            update_fields["min_price_4h"] = float(min([c[3] for c in ohlcv]))
                    except Exception as e:
                        logger.error(f"Error fetching historical candles for {symbol}: {e}")
                        
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
    finally:
        if exchange:
            await exchange.close()

async def run_evaluator_loop():
    logger.info("[NonTrade] Starting non-trade evaluator service")
    while True:
        await evaluate_pending_non_trades()
        await asyncio.sleep(600)  # run every 10 min

if __name__ == "__main__":
    asyncio.run(run_evaluator_loop())
