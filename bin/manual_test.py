import os
import json
from pybit.unified_trading import HTTP

# This script helps debug IF the issue is in the loading of keys or the keys themselves.
# Run it with: python3 bin/manual_test.py "YOUR_API_KEY" "YOUR_API_SECRET"

def manual_test(key, secret):
    print(f"Manual Test with provided keys:")
    print(f"  - Key: {key[:4]}... (Length: {len(key)})")
    
    for environment in [True, False]:
        env_msg = "TESTNET" if environment else "MAINNET"
        print(f"\n--- Trying {env_msg} ---")
        try:
            session = HTTP(
                testnet=environment,
                api_key=key,
                api_secret=secret,
            )
            # Try a very basic wallet check first
            res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            print(f"✅ Success on {env_msg}!")
            print(f"Wallet Balance: {res.get('result', {}).get('list', [{}])[0].get('coin', [{}])[0].get('equity', 'N/A')}")
        except Exception as e:
            print(f"❌ Failed on {env_msg}: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python3 bin/manual_test.py <API_KEY> <API_SECRET>")
    else:
        manual_test(sys.argv[1], sys.argv[2])
