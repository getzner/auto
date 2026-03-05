import asyncio
import os
from data.db import get_db_conn
from loguru import logger

async def reset_database():
    logger.warning("Starting Database Reset (Clearing all trades and decisions)...")
    
    conn = await get_db_conn()
    try:
        # TRUNCATE tables to clear all data and reset sequences
        await conn.execute("TRUNCATE TABLE positions RESTART IDENTITY CASCADE;")
        await conn.execute("TRUNCATE TABLE decisions RESTART IDENTITY CASCADE;")
        
        # If there are any other analytical views or tables that depend on these, 
        # cascade will handle them, but let's be thorough if meta-analysis exists.
        
        logger.info("✅ Database reset successful! Decisions and Positions are cleared.")
    except Exception as e:
        logger.error(f"❌ Database reset failed: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(reset_database())
