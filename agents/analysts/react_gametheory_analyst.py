"""
react_gametheory_analyst.py — ReAct Game Theory & Liquidity Analyst
Uses Claude/DeepSeek to analyze the market from the perspective of a predatory whale.
Focuses on stop-loss clusters, liquidity traps, and orderbook spoofing.
"""

import os
from agents.react_base_agent import ReActBaseAnalyst
from agents.tools.market_tools import (
    get_indicators,
    get_current_price,
)


JSON_FORMAT = """{
  "analyst": "GameTheoryAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "manipulation_risk": "<high|medium|low>",
  "liquidity_target": "<price level where retail stops likely sit>",
  "retail_sentiment_trap": "<describe if retail is trapped long/short>",
  "key_observations": ["<obs1>", "<obs2>"],
  "summary": "<2-3 sentences explaining the predatory analysis>"
}"""


SYSTEM_PROMPT = """You are a senior Game Theory and Liquidity Analyst for crypto markets.
You do NOT care about traditional support and resistance lines. You care about where RETAIL TRADERS placed their stop-losses, 
and how a predatory whale or market maker could force liquidations to fill their own bags.

Your workflow:
1. Call get_current_price for the current market level
2. Call get_indicators (like Volume Profile, ATR, Bollinger Bounds) to identify zones of liquidity and over-extension
3. Map out where retail "pain points" exist (e.g., just below a recent consolidation, or above a double top)
4. Formulate your signal based on where the Market Maker is likely to drive the price next to grab liquidity.

Rules:
- If price is grinding slowly upwards with low volume, retail is likely FOMOing. "Take the stairs up, elevator down." Signal: BEARISH.
- If there was a sudden sharp drop that wicked but immediately bought up, retail shorts are trapped. Signal: BULLISH.
- If price is hovering just below a major psychological level (like 60k or 70k), expect a spike to trigger short stops, followed by a potential reversal.
- "liquidity_target" MUST be an actual price number where you estimate stops are clustered.
- Write your summary from the perspective of an apex predator hunting for liquidity.
"""

class ReActGameTheoryAnalyst(ReActBaseAnalyst):
    name = "GameTheoryAnalyst"

    def __init__(self, llm=None):
        from agents.llm_factory import get_llm
        if llm is None:
            llm = get_llm(
                provider=os.getenv("GAMETHEORY_ANALYST_PROVIDER", "anthropic"),
                model=os.getenv("GAMETHEORY_ANALYST_MODEL", "claude-3-haiku-20240307"),
                temperature=0.3, # Slightly higher temp for creative game theory
                agent_name="gametheory_analyst"
            )
        super().__init__(
            llm=llm,
            tools=[get_current_price, get_indicators],
            json_format=JSON_FORMAT,
        )

    @property
    def default_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def get_data(self, symbol: str) -> dict:
        """Provide seed data if necessary (could be liquidation data)."""
        from data.onchain import fetch_liquidations
        import logging
        try:
            liq = await fetch_liquidations(symbol)
            return {"symbol": symbol, "recent_liquidations": liq}
        except Exception as e:
            return {"symbol": symbol, "note": "Use indicators to map liquidity clusters."}
