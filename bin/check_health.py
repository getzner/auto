import httpx
import os
from loguru import logger

def check_internal_health():
    url = "http://localhost:8000/health"
    try:
        r = httpx.get(url, timeout=5)
        print(f"Health Status: {r.status_code}")
        print(r.json())
    except Exception as e:
        print(f"Failed to reach health endpoint: {e}")

def check_recent_logs():
    log_file = os.getenv("LOG_FILE", "/var/log/trade_api.log")
    print(f"Checking log file: {log_file}")
    if not os.path.exists(log_file):
        # Specific path for this server based on previous logs
        log_file = "/var/log/trade_api.log"
        
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            # Look for recent scanner activity
            scanner_lines = [l.strip() for l in lines if "[SCANNER]" in l][-10:]
            print("\nLast 10 SCANNER logs:")
            for l in scanner_lines:
                print(l)
    except Exception as e:
        print(f"Could not read logs: {e}")

if __name__ == "__main__":
    check_internal_health()
    check_recent_logs()
