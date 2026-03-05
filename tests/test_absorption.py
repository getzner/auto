import asyncio
import json
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data.absorption import detect_absorption

async def test_absorption():
    print("Testing Absorption Detection Logic...")
    
    # This requires a live DB connection or we need to mock it.
    # Since I'm in an agentic environment, I can try to run it 
    # and see if it fails due to connectivity or insufficient data.
    
    try:
        result = await detect_absorption("BTC/USDT")
        print(f"Result: {json.dumps(result, indent=2)}")
        
        if result.get("status") == "insufficient_data":
            print("Note: Insufficient data in DB to produce signals (common on fresh setups).")
        else:
            print("Success: Absorption detection produced a status report.")
            
    except Exception as e:
        print(f"Error during test: {e}")

if __name__ == "__main__":
    asyncio.run(test_absorption())
