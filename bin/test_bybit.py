import os
import json
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

def test_connection():
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

    logger.info(f"Testing Bybit connection (Testnet={testnet})...")

    if not api_key or not api_secret:
        logger.error("❌ Missing BYBIT_API_KEY or BYBIT_API_SECRET in .env")
        return

    # Diagnostic formatting check
    logger.info(f"Key Format Check:")
    logger.info(f"  - Key Length: {len(api_key)}")
    logger.info(f"  - Secret Length: {len(api_secret)}")
    logger.info(f"  - Starts with Quote: {api_key.startswith(chr(34)) or api_key.startswith(chr(39))}")
    logger.info(f"  - Ends with space: {api_key.endswith(' ')}")
    logger.info(f"  - First 3 chars of Key: {api_key[:3]}...")
    
    try:
        from pybit.unified_trading import HTTP
        session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
        )

        # 1. Check account info
        logger.info("Fetching account info...")
        acc_info = session.get_account_info()
        acc_type = acc_info.get("result", {}).get("unifiedMarginStatus")
        
        # unifiedMarginStatus: 1=Regular, 2=Unified, 3=UTA (Unified Trading Account)
        uta_map = {1: "Regular", 2: "Unified", 3: "UTA"}
        logger.info(f"✅ Connection successful!")
        logger.info(f"Account Type: {uta_map.get(acc_type, acc_type)}")

        # 2. Check wallet balance (USDT)
        logger.info("Fetching USDT balance...")
        balance = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        usdt = balance.get("result", {}).get("list", [{}])[0].get("coin", [{}])[0]
        
        equity = usdt.get("equity", "0")
        available = usdt.get("availableToWithdraw", "0")
        
        logger.info(f"💰 Balance (USDT): Equity={equity} | Available={available}")
        
    except ImportError:
        logger.error("❌ pybit not installed. Run: pip install pybit")
    except Exception as e:
        logger.error(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    test_connection()
