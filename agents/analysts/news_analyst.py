"""
news_analyst.py — News & Sentiment Analyst Agent
LLM: DeepSeek (cheap, fast, great at summarizing news)
Data: Tavily + Brave Search (real-time web news)
"""

import os
from langchain_deepseek import ChatDeepSeek
from agents.base_agent import BaseAnalyst
from data.search import search_news


SYSTEM_PROMPT = """You are a senior Crypto News & Sentiment Analyst.

You receive a set of recent news articles and web search results about a cryptocurrency.

Respond with ONLY valid JSON in this exact format:
{
  "analyst": "NewsAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "sentiment_score": <-1.0 to 1.0, where -1=very bearish, 0=neutral, 1=very bullish>,
  "key_themes": ["<theme1>", "<theme2>", "<theme3>"],
  "risk_events": ["<event1>"] or [],
  "catalyst": "<main bullish or bearish catalyst if any, else null>",
  "summary": "<2-3 sentences synthesizing the news sentiment>"
}

Rules:
- BULLISH: ETF approvals, institutional buys, protocol upgrades, adoption news
- BEARISH: regulatory crackdowns, hacks, exchange failures, negative macro
- NEUTRAL: mixed signals, routine updates, no major news
- confidence 8+: only if 3+ major outlets agree on a clear direction
- Ignore FUD or hype with no substance
- Focus on news from the LAST 7 DAYS
"""


class NewsAnalyst(BaseAnalyst):
    name = "NewsAnalyst"

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
        return await search_news(symbol)
