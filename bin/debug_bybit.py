import os, json
from dotenv import load_dotenv
from pybit.unified_trading import HTTP
load_dotenv()

def check(name, val):
    if not val: return "❌ MISSING"
    clean = val.strip()
    res = f"LEN: {len(val)}"
    if len(val) != len(clean): res += " ⚠️ HAS SPACES/TRANS"
    if val.startswith(('"', "'")): res += " ⚠️ HAS QUOTES"
    return res

key, secret = os.getenv("BYBIT_API_KEY"), os.getenv("BYBIT_API_SECRET")
print(f"BYBIT_API_KEY:    {check('KEY', key)}")
print(f"BYBIT_API_SECRET: {check('SECRET', secret)}")

# The new "Demo Trading" on Bybit Mainnet uses its own specific subdomain.
endpoints = {
    "TESTNET": "https://api-testnet.bybit.com",
    "MAINNET": "https://api.bybit.com",
    "DEMO":    "https://api-demo.bybit.com"  # New Bybit Demo Trading endpoint
}

for env, url in endpoints.items():
    print(f"\n--- Testing Environment: {env} ({url}) ---")
    try:
        # We manually set the endpoint to bypass pybit's default testnet toggle if needed
        testnet_flag = (env == "TESTNET")
        session = HTTP(
            testnet=testnet_flag,
            api_key=key,
            api_secret=secret
        )
        if env == "DEMO":
            session.endpoint = url # Force Demo endpoint
            
        info = session.get_account_info()
        print(f"✅ SUCCESS! Account status: {info.get('result', {}).get('unifiedMarginStatus')}")
        
        # Try balance specifically for DEMO
        print(f"Fetching balances...")
        bal = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        equity = bal.get("result", {}).get("list", [{}])[0].get("coin", [{}])[0].get("equity", "0")
        print(f"💰 Equity: {equity} USDT")
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
