import os
import asyncio
import json
from loguru import logger

class LiveTrader:
    """
    Executes trades on Bybit Unified Trading Account.
    Supports both Testnet and Mainnet via BYBIT_TESTNET env var.
    """
    def __init__(self):
        self.api_key = os.getenv("BYBIT_API_KEY")
        self.api_secret = os.getenv("BYBIT_API_SECRET")
        self.testnet = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
        self.is_demo = os.getenv("BYBIT_DEMO", "false").lower() == "true"
        
        try:
            from pybit.unified_trading import HTTP
            if not self.api_key or not self.api_secret:
                logger.warning("[LIVE] Bybit credentials missing. Live trading will fail.")
                self.session = None
            else:
                # Initialize session
                self.session = HTTP(
                    testnet=self.testnet,
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                )
                # Override for the new Bybit Demo Trading (api-demo)
                if self.is_demo:
                    logger.info("[LIVE] 🧪 Using Bybit DEMO TRADING endpoint (api-demo.bybit.com)")
                    self.session.endpoint = "https://api-demo.bybit.com"
                else:
                    env_name = "TESTNET" if self.testnet else "MAINNET"
                    logger.info(f"[LIVE] 🔌 Connected to Bybit {env_name}")
        except ImportError:
            logger.warning("[LIVE] pybit not installed. Run 'pip install pybit'")
            self.session = None

    def _check_kill_switch(self) -> bool:
        safety_path = "/opt/trade_server/data/safety.json"
        if not os.path.exists("/opt/trade_server"):
            safety_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "safety.json"))
        
        if os.path.exists(safety_path):
            try:
                with open(safety_path, "r") as f:
                    data = json.load(f)
                    return data.get("kill_switch", False)
            except:
                pass
        return False

    def get_balance(self) -> float:
        """
        Fetches the current USDT equity from Bybit Unified Account.
        NOTE: This is sync — wrap in run_in_executor when calling from async context.
        """
        if not self.session:
            return 0.0
        try:
            resp = self.session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            if resp.get("retCode") == 0:
                coins = resp.get("result", {}).get("list", [{}])[0].get("coin", [])
                for c in coins:
                    if c.get("coin") == "USDT":
                        return float(c.get("equity", 0.0))
            return 0.0
        except Exception as e:
            logger.error(f"[LIVE] Failed to fetch balance: {e}")
            return 0.0

    async def get_balance_async(self) -> float:
        """Async wrapper: runs sync get_balance in a thread executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_balance)

    async def get_active_positions(self) -> list[dict]:
        """
        Fetches all currently open positions from Bybit.
        H2 Fix: runs sync pybit call in thread executor to avoid blocking event loop.
        """
        if not self.session:
            return []
        loop = asyncio.get_running_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                lambda: self.session.get_positions(category="linear", settleCoin="USDT")
            )
            if resp.get("retCode") == 0:
                return resp.get("result", {}).get("list", [])
            return []
        except Exception as e:
            logger.error(f"[LIVE] Failed to fetch positions: {e}")
            return []

    async def execute(self, decision_id: int, proposal: dict):
        """
        Executes a trade on Bybit based on the PM decision.
        H2 Fix: place_order runs in thread executor (pybit is sync).
        H3 Fix: accepts both 'direction' (orchestrator) and 'side' (direct).
        """
        if self._check_kill_switch():
            logger.error(f"[LIVE] 🛑 KILL SWITCH ACTIVE. Aborting trade for decision {decision_id}")
            return

        if not self.session:
            logger.error(f"[LIVE] ❌ Cannot execute trade {decision_id}: Session not initialized.")
            return

        # H3: Normalise direction — orchestrator sends 'direction' (LONG/SHORT),
        # but some callers may send 'side' (long/short). Handle both gracefully.
        direction = (proposal.get("direction") or proposal.get("side") or "HOLD").upper()
        if direction == "HOLD":
            logger.info(f"[LIVE] HOLD decision {decision_id} — skipping execution")
            return

        symbol = proposal["symbol"].replace("/", "")  # Bybit uses BTCUSDT
        side   = "Buy" if direction == "LONG" else "Sell"
        qty = str(proposal.get("size_qty", 0))

        # In Live, we use the TP/SL suggested by the trader
        tp = str(proposal.get("take_profit", "") or "")
        sl = str(proposal.get("stop_loss",   "") or "")

        logger.info(f"[LIVE] 🚀 Executing {side} on {symbol} | Qty: {qty} | TP: {tp} | SL: {sl}")

        try:
            # H2 Fix: run synchronous pybit call in a thread executor
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: self.session.place_order(
                    category="linear",
                    symbol=symbol,
                    side=side,
                    orderType="Market",
                    qty=qty,
                    takeProfit=tp if tp else None,
                    stopLoss=sl   if sl else None,
                    tpTriggerBy="MarkPrice",
                    slTriggerBy="MarkPrice",
                    tpslMode="Full",
                    orderLinkId=f"orc_{decision_id}"
                )
            )
            order_id = resp.get('result', {}).get('orderId')
            logger.info(f"[LIVE] ✅ Order placed: {order_id}")

            # Record in DB for monitoring and journaling
            from data.db import get_db_conn
            from datetime import datetime, timezone
            conn = await get_db_conn()
            try:
                await conn.execute(
                    """
                    INSERT INTO positions
                        (decision_id, symbol, side, entry_price, size_usdt,
                         stop_loss, take_profit, opened_at, status, is_live)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'open', TRUE)
                    """,
                    decision_id, proposal["symbol"], proposal["side"], 
                    float(proposal.get("entry_price") or 0), 
                    float(proposal.get("size_usdt") or 0),
                    float(tp) if tp else None, 
                    float(sl) if sl else None,
                    datetime.now(timezone.utc)
                )
                # Mark decision as executed
                await conn.execute(
                    "UPDATE decisions SET executed=true WHERE id=$1", decision_id
                )
            finally:
                await conn.close()
            
        except Exception as e:
            logger.error(f"[LIVE] ❌ Bybit Order Failed: {e}")
