"""
react_onchain_analyst.py — ReAct On-chain Analyst
Uses Claude Haiku for on-chain pattern recognition, with tools to
cross-reference exchange flows with technical indicators and news.
"""

import os
from agents.react_base_agent import ReActBaseAnalyst
from agents.tools.market_tools import (
    get_indicators,
    get_current_price,
    search_news,
)


JSON_FORMAT = """{
  "analyst": "OnchainAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "smart_money_activity": "<accumulation|distribution|neutral>",
  "exchange_flow_signal": "<bullish|bearish|neutral>",
  "whale_activity": "<high|medium|low>",
  "stablecoin_signal": "<bullish|bearish|neutral>",
  "news_confirmation": true | false,
  "key_observations": ["<obs1>", "<obs2>", "<obs3>"],
  "summary": "<2-3 sentences>"
}"""


SYSTEM_PROMPT = """You are a senior crypto On-chain Analyst specializing in exchange flows,
whale activity, and stablecoin dynamics.

Your workflow:
1. Start with the on-chain seed data provided (exchange flows, whale txns)
2. Call get_current_price for market context
3. Call get_indicators to see if technicals confirm the on-chain signal
4. Call search_news to check for any news events explaining whale movements
5. Output your final JSON signal with news_confirmation=true if news backs it up

Rules:
- Exchange NETFLOW positive (inflows > outflows) = sell pressure = BEARISH
- Exchange NETFLOW negative (outflows > inflows) = accumulation = BULLISH
- Large whale inflows to exchange = potential sell = BEARISH
- Large whale outflows from exchange = hodling = BULLISH
- Stablecoin supply increasing = dry powder entering = BULLISH
- confidence 8+ only if on-chain + technicals + news ALL confirm
- news_confirmation = true if news explains or supports the on-chain signal
"""


class ReActOnchainAnalyst(ReActBaseAnalyst):
    name = "OnchainAnalyst"

    def __init__(self, llm=None):
        from agents.llm_factory import get_llm
        if llm is None:
            llm = get_llm(
                provider=os.getenv("ONCHAIN_ANALYST_PROVIDER", "anthropic"),
                model=os.getenv("ONCHAIN_ANALYST_MODEL", "claude-3-haiku-20240307"),
                temperature=0.1,
                agent_name="onchain_analyst"
            )
        super().__init__(
            llm=llm,
            tools=[get_current_price, get_indicators, search_news],
            json_format=JSON_FORMAT,
        )

    @property
    def default_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def get_data(self, symbol: str) -> dict:
        """Provide seed on-chain data — agent cross-checks via tools."""
        from data.onchain import get_onchain_summary
        try:
            return await get_onchain_summary(symbol, lookback_hours=24)
        except Exception:
            return {"symbol": symbol, "note": "Use tools to gather market context"}
