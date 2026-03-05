"""
volume_profile_analyst.py — Volume Profile Analyst Agent
LLM: Gemini Flash (fast, cheap)
"""

import os
from langchain_deepseek import ChatDeepSeek
from agents.base_agent import BaseAnalyst
from data.volume_profile import get_vp_summary


SYSTEM_PROMPT = """You are a senior crypto Volume Profile Analyst.
You receive POC (Point of Control), VAH/VAL (Value Area), and price-vs-value-area context
across 1h, 4h, and 1d sessions.

Respond with ONLY valid JSON in this exact format:
{
  "analyst": "VolumeProfileAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "key_levels": {
    "poc_1d": <price>,
    "vah_1d": <price>,
    "val_1d": <price>
  },
  "price_context": "<above_poc|below_poc|at_poc|in_value_area|outside_value_area>",
  "structure": "<bullish_structure|bearish_structure|range_bound>",
  "key_observations": ["<obs1>", "<obs2>"],
  "summary": "<2-3 sentences>"
}

Rules:
- Price above POC + inside Value Area = balanced/neutral
- Price above POC + above VAH = breakout bullish
- Price below POC + below VAL = breakdown bearish
- HVN near price = strong support/resistance (slow movement expected)
- LVN near price = thin area (fast movement expected)
"""


class VolumeProfileAnalyst(BaseAnalyst):
    name = "VolumeProfileAnalyst"

    def __init__(self):
        llm = ChatDeepSeek(
            model="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.1,
        )
        super().__init__(llm)

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def get_data(self, symbol: str) -> dict:
        return await get_vp_summary(symbol)
