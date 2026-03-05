"""
react_volume_analyst.py — ReAct Volume Analyst
Can autonomously call: get_indicators, get_current_price, get_orderbook, run_backtest
Before giving its signal, it fetches live data and can test its hypothesis via backtest.
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
  "analyst": "VolumeAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "cvd_trend": "<rising|falling|flat>",
  "dominant_side": "<buyers|sellers|balanced>",
  "key_observations": ["<obs1>", "<obs2>", "<obs3>"],
  "backtest_used": true | false,
  "backtest_assessment": "<STRONG|GOOD|WEAK|REJECT|N/A>",
  "summary": "<2-3 sentence interpretation>"
}"""


SYSTEM_PROMPT = """You are a senior crypto Volume Analyst specializing in CVD, order flow, and volume dynamics.

Your workflow:
1. Call get_indicators to get RSI, MACD, Bollinger Bands for context
2. Call get_orderbook to see current buy/sell walls
3. Call get_current_price to confirm live price
4. If you have a strong hypothesis, optionally call run_backtest to validate it
5. Output your final JSON signal

Rules:
- BULLISH: CVD rising, buyers dominant, RSI < 70, strong positive delta
- BEARISH: CVD falling, sellers dominant, RSI > 30, strong negative delta  
- NEUTRAL: mixed or insufficient signals
- confidence 8-10 ONLY when 3+ signals agree AND backtest supports it
- Always include what tools you called and what you found in key_observations
"""


class ReActVolumeAnalyst(ReActBaseAnalyst):
    name = "VolumeAnalyst"

    def __init__(self, llm=None):
        from agents.llm_factory import get_llm
        if llm is None:
            llm = get_llm(
                provider=os.getenv("VOLUME_ANALYST_PROVIDER", "deepseek"),
                model=os.getenv("VOLUME_ANALYST_MODEL", "deepseek-chat"),
                temperature=0.1,
                agent_name="volume_analyst"
            )
        super().__init__(
            llm=llm,
            tools=[get_indicators, get_current_price, get_orderbook, run_backtest],
            json_format=JSON_FORMAT,
        )

    @property
    def default_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def get_data(self, symbol: str) -> dict:
        """Provide minimal seed data — agent fetches live data via tools."""
        from data.volume import get_volume_summary
        try:
            return await get_volume_summary(symbol, timeframe="1h", n=20)
        except Exception:
            return {"symbol": symbol, "note": "Use tools to fetch live data"}
