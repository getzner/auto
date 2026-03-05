import asyncio
import os
import json
import unittest
from unittest.mock import MagicMock, patch
from execution.live_trader import LiveTrader

class TestLiveTrader(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set dummy env vars
        os.environ["BYBIT_API_KEY"] = "test_key"
        os.environ["BYBIT_API_SECRET"] = "test_secret"
        os.environ["BYBIT_TESTNET"] = "true"
        
        # Ensure data dir exists for safety.json
        self.safety_path = os.path.abspath("data/safety.json")
        os.makedirs(os.path.dirname(self.safety_path), exist_ok=True)
        with open(self.safety_path, "w") as f:
            json.dump({"kill_switch": False}, f)

    def tearDown(self):
        if os.path.exists(self.safety_path):
            os.remove(self.safety_path)

    @patch("pybit.unified_trading.HTTP")
    async def test_execute_success(self, mock_http):
        mock_session = MagicMock()
        mock_http.return_value = mock_session
        mock_session.place_order.return_value = {"result": {"orderId": "12345"}}
        
        trader = LiveTrader()
        proposal = {
            "symbol": "BTC/USDT",
            "side": "long",
            "size_qty": 0.001,
            "take_profit": 65000,
            "stop_loss": 60000
        }
        
        await trader.execute(999, proposal)
        
        mock_session.place_order.assert_called_once()
        args, kwargs = mock_session.place_order.call_args
        self.assertEqual(kwargs["symbol"], "BTCUSDT")
        self.assertEqual(kwargs["side"], "Buy")
        self.assertEqual(kwargs["qty"], "0.001")
        self.assertEqual(kwargs["orderLinkId"], "orc_999")

    async def test_kill_switch_blocks(self):
        with open(self.safety_path, "w") as f:
            json.dump({"kill_switch": True}, f)
        
        trader = LiveTrader()
        # Mock session to ensure it's not even called
        trader.session = MagicMock()
        
        proposal = {"symbol": "BTC/USDT", "side": "long"}
        await trader.execute(1001, proposal)
        
        trader.session.place_order.assert_not_called()

if __name__ == "__main__":
    unittest.main()
