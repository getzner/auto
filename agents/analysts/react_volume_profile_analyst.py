"""
react_volume_profile_analyst.py — ReAct Volume Profile Analyst
Combines structural POC/VAH/VAL analysis with live tools for
confirming price action context and running hypothesis backtests.
"""

import os
from agents.react_base_agent import ReActBaseAnalyst
from agents.tools.market_tools import (
    get_indicators,
    get_current_price,
    get_orderbook,
    run_backtest,
)


JSON_FORMAT = """{
  "analyst": "VolumeProfileAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "price_vs_poc": "<above|below|at>",
  "price_vs_vah": "<above|below|at>",
  "price_vs_val": "<above|below|at>",
  "value_area_status": "<inside|above|below>",
  "poc_level": <price>,
  "vah_level": <price>,
  "val_level": <price>,
  "backtest_used": true | false,
  "key_observations": ["<obs1>", "<obs2>", "<obs3>"],
  "summary": "<2-3 sentence interpretation>"
}"""


SYSTEM_PROMPT = """You are a senior crypto Volume Profile Analyst specializing in market structure.

Your workflow:
1. Use the seed Volume Profile data (POC, VAH, VAL, value area) as your base
2. Call get_current_price to see where price is relative to the profile
3. Call get_orderbook to see if current bid/ask walls align with profile levels
4. Call get_indicators to get RSI and trend context
5. Optionally call run_backtest if price is at a key level (POC/VAH/VAL rejection)
6. Output your final JSON signal

Key concepts:
- POC (Point of Control): Highest volume price level = strongest support/resistance
- VAH (Value Area High): Top of 70% volume zone
- VAL (Value Area Low): Bottom of 70% volume zone
- Price ABOVE VAH = bullish extension (may return to value area)
- Price BELOW VAL = bearish extension (may return to value area)
- Price AT POC = key battleground, watch for direction
- confidence 8+: price at key level + orderbook confirms + RSI not extreme
"""


class ReActVolumeProfileAnalyst(ReActBaseAnalyst):
    name = "VolumeProfileAnalyst"

    def __init__(self, llm=None):
        from agents.llm_factory import get_llm
        if llm is None:
            llm = get_llm(
                provider=os.getenv("VP_ANALYST_PROVIDER", "deepseek"),
                model=os.getenv("VP_ANALYST_MODEL", "deepseek-chat"),
                temperature=0.1,
                agent_name="vp_analyst"
            )
        super().__init__(
            llm=llm,
            tools=[get_current_price, get_orderbook, get_indicators, run_backtest],
            json_format=JSON_FORMAT,
        )

    @property
    def default_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def get_data(self, symbol: str) -> dict:
        """Provide seed volume profile data — agent verifies with live tools."""
        from data.volume_profile import get_vp_summary
        try:
            return await get_vp_summary(symbol)
        except Exception:
            return {"symbol": symbol, "note": "Use get_current_price and get_orderbook to analyze structure"}
