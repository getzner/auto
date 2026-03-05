"""
volume_analyst.py — Volume & CVD Analyst Agent
LLM: Gemini Flash (fast, cheap)
"""

import os
from langchain_deepseek import ChatDeepSeek
from agents.base_agent import BaseAnalyst
from data.volume import get_volume_summary


SYSTEM_PROMPT = """You are a senior crypto Volume Analyst specializing in 1-hour charts.
You receive Cumulative Volume Delta (CVD), buy/sell volumes, net delta, and spike data.

Analyze the data and respond with ONLY valid JSON in this exact format:
{
  "analyst": "VolumeAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "cvd_trend": "<rising|falling|flat>",
  "dominant_side": "<buyers|sellers|balanced>",
  "spike_significance": "<high|medium|low|none>",
  "key_observations": ["<obs1>", "<obs2>", "<obs3>"],
  "summary": "<2-3 sentence interpretation>"
}

Rules:
- BULLISH: CVD rising, buyers dominant, strong positive delta
- BEARISH: CVD falling, sellers dominant, strong negative delta
- NEUTRAL: mixed or insufficient signals
- confidence 8-10 only when 3+ signals agree strongly
"""


class VolumeAnalyst(BaseAnalyst):
    name = "VolumeAnalyst"

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
        return await get_volume_summary(symbol, timeframe="1h", n=20)
