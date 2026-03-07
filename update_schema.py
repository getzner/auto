import asyncio
from data.db import get_db_session

async def main():
    try:
        async with get_db_session() as conn:
            try:
                await conn.execute("ALTER TABLE non_trade_outcomes ADD COLUMN max_price_4h NUMERIC;")
                print("Added max_price_4h")
            except Exception as e:
                print("max_price_4h exists:", e)
            try:
                await conn.execute("ALTER TABLE non_trade_outcomes ADD COLUMN min_price_4h NUMERIC;")
                print("Added min_price_4h")
            except Exception as e:
                print("min_price_4h exists:", e)
            
            # Check schema
            out = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='non_trade_outcomes'")
            for r in out:
                print(r['column_name'], r['data_type'])
    except Exception as e:
        print("DB Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
