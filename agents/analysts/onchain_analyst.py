"""
onchain_analyst.py — On-chain Data Analyst Agent
LLM: Claude Haiku (good at structured data pattern recognition)
"""

import os
from langchain_anthropic import ChatAnthropic
from agents.base_agent import BaseAnalyst
from data.onchain import get_onchain_summary


SYSTEM_PROMPT = """You are a senior crypto On-chain Analyst specializing in exchange flows,
whale activity, and stablecoin dynamics.

You receive exchange inflow/outflow netflow, whale transaction counts and volumes,
and stablecoin supply changes.

Respond with ONLY valid JSON in this exact format:
{
  "analyst": "OnchainAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "smart_money_activity": "<accumulation|distribution|neutral>",
  "exchange_flow_signal": "<bullish|bearish|neutral>",
  "whale_activity": "<high|medium|low>",
  "stablecoin_signal": "<bullish|bearish|neutral>",
  "key_observations": ["<obs1>", "<obs2>", "<obs3>"],
  "summary": "<2-3 sentences>"
}

Rules:
- Exchange NETFLOW positive (inflows > outflows) = sell pressure = BEARISH
- Exchange NETFLOW negative (outflows > inflows) = accumulation = BULLISH
- Large whale inflows to exchange = potential sell = BEARISH
- Large whale outflows from exchange = hodling/accumulation = BULLISH
- Stablecoin supply increasing (minting) = dry powder entering market = BULLISH
- confidence 8+ only if 3+ signals strongly agree
"""


class OnchainAnalyst(BaseAnalyst):
    name = "OnchainAnalyst"

    def __init__(self):
        llm = ChatAnthropic(
            model="claude-3-haiku-20240307",
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0.1,
        )
        super().__init__(llm)

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def get_data(self, symbol: str) -> dict:
        return await get_onchain_summary(symbol, lookback_hours=24)
