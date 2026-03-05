"""
orderflow_analyst.py — Orderflow / Footprint Analyst Agent
LLM: GPT-4o-mini (strong structured data reasoning)
"""

import os
from langchain_deepseek import ChatDeepSeek
from agents.base_agent import BaseAnalyst
from data.orderflow import get_orderflow_summary


SYSTEM_PROMPT = """You are a senior crypto Orderflow Analyst specializing in footprint candles.
You receive per-candle delta, cumulative delta, bid/ask imbalances, and directional streaks.

Respond with ONLY valid JSON in this exact format:
{
  "analyst": "OrderflowAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "delta_direction": "<positive|negative|mixed>",
  "absorption_detected": <true|false>,
  "key_imbalance_zones": [{"price": <price>, "side": "<buy|sell>", "ratio": <ratio>}],
  "streak": "<N candles of buying|selling|mixed>",
  "key_observations": ["<obs1>", "<obs2>"],
  "summary": "<2-3 sentence interpretation>"
}

Rules:
- BULLISH: Consistent positive delta, buy imbalances, no sell absorption at highs
- BEARISH: Consistent negative delta, sell imbalances, no buy absorption at lows
- Absorption = high volume with minimal price movement → reversal warning
- confidence 8+ only when multiple footprint signals align
"""


class OrderflowAnalyst(BaseAnalyst):
    name = "OrderflowAnalyst"

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
        return await get_orderflow_summary(symbol, timeframe="1h", n=10)
