"""
react_orderflow_analyst.py — ReAct Orderflow / Footprint Analyst
Uses tools to cross-reference orderbook depth with CVD and indicators
before giving its delta/absorption signal.
"""

import os
from agents.react_base_agent import ReActBaseAnalyst
from agents.tools.market_tools import (
    get_indicators,
    get_current_price,
    get_orderbook,
    run_backtest,
    check_absorption,
)


JSON_FORMAT = """{
  "analyst": "OrderflowAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "delta_direction": "<positive|negative|mixed>",
  "absorption_detected": true | false,
  "key_imbalance_zones": [{"price": <price>, "side": "<buy|sell>", "ratio": <ratio>}],
  "streak": "<N candles of buying|selling|mixed>",
  "absorption_report": <result from check_absorption or null>,
  "backtest_used": true | false,
  "key_observations": ["<obs1>", "<obs2>", "<obs3>"],
  "summary": "<2-3 sentence interpretation>"
}"""


SYSTEM_PROMPT = """You are a senior crypto Orderflow Analyst specializing in footprint candles and delta analysis.

 Your workflow:
 1. Call get_orderbook to see current bid/ask walls and imbalances
 2. Call check_absorption to see if aggressive orders are being absorbed at key levels (POC/VAH/VAL)
 3. Call get_indicators to get RSI, MACD, ATR for context
 4. Call get_current_price for reference
 5. If you have a clear hypothesis, optionally call run_backtest to validate
 6. Output your final JSON signal
 
 Rules:
 - BULLISH: Consistent positive delta, buy imbalances, NO buy absorption at highs, or SELL absorption at lows (reversal)
 - BEARISH: Consistent negative delta, sell imbalances, NO sell absorption at lows, or BUY absorption at highs (reversal)
 - Absorption = high volume with minimal price movement at key levels -> STRONG reversal signal
 - Large bid walls = support; large ask walls = resistance
 - confidence 8+ only when orderbook + absorption + technicals all align
- Always note the strongest bid/ask imbalance zone in key_imbalance_zones
"""


class ReActOrderflowAnalyst(ReActBaseAnalyst):
    name = "OrderflowAnalyst"

    def __init__(self, llm=None):
        from agents.llm_factory import get_llm
        if llm is None:
            llm = get_llm(
                provider=os.getenv("ORDERFLOW_ANALYST_PROVIDER", "deepseek"),
                model=os.getenv("ORDERFLOW_ANALYST_MODEL", "deepseek-chat"),
                temperature=0.1,
                agent_name="orderflow_analyst"
            )
        super().__init__(
            llm=llm,
            tools=[get_orderbook, get_indicators, get_current_price, run_backtest, check_absorption],
            json_format=JSON_FORMAT,
        )

    @property
    def default_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def get_data(self, symbol: str) -> dict:
        """Provide seed orderflow data — agent supplements via tools."""
        from data.orderflow import get_orderflow_summary
        try:
            return await get_orderflow_summary(symbol, timeframe="1h", n=10)
        except Exception:
            return {"symbol": symbol, "note": "Use get_orderbook tool for live data"}
