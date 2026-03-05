"""
react_news_analyst.py — ReAct News & Sentiment Analyst
Autonomously searches news, checks indicators, and cross-references market data
before giving its sentiment signal.
"""

import os
from agents.react_base_agent import ReActBaseAnalyst
from agents.tools.market_tools import (
    search_news,
    get_indicators,
    get_current_price,
)


JSON_FORMAT = """{
  "analyst": "NewsAnalyst",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "sentiment_score": <-1.0 to 1.0>,
  "key_themes": ["<theme1>", "<theme2>", "<theme3>"],
  "risk_events": ["<event1>"] or [],
  "catalyst": "<main catalyst or null>",
  "news_sources_checked": <integer>,
  "summary": "<2-3 sentence synthesis>"
}"""


SYSTEM_PROMPT = """You are a senior Crypto News & Sentiment Analyst.

Your workflow:
1. Call search_news to get the latest news and sentiment for the symbol
2. Call get_current_price to understand current market context
3. Call get_indicators to see if technicals confirm or contradict news sentiment
4. Synthesize everything into your final JSON signal

Rules:
- BULLISH: ETF approvals, institutional buys, protocol upgrades, adoption news
- BEARISH: regulatory crackdowns, hacks, exchange failures, negative macro
- NEUTRAL: mixed signals, routine updates, no major news
- confidence 8+: only if news + technicals BOTH confirm the direction
- Ignore FUD or hype with no substance
- Focus on news from the LAST 7 DAYS
- Cross-check: if news is BULLISH but RSI > 75, reduce confidence (overbought)
"""


class ReActNewsAnalyst(ReActBaseAnalyst):
    name = "NewsAnalyst"

    def __init__(self, llm=None):
        from agents.llm_factory import get_llm
        if llm is None:
            llm = get_llm(
                provider=os.getenv("NEWS_ANALYST_PROVIDER", "deepseek"),
                model=os.getenv("NEWS_ANALYST_MODEL", "deepseek-chat"),
                temperature=0.1,
                agent_name="news_analyst"
            )
        super().__init__(
            llm=llm,
            tools=[search_news, get_current_price, get_indicators],
            json_format=JSON_FORMAT,
        )

    @property
    def default_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def get_data(self, symbol: str) -> dict:
        """Provide seed context — agent fetches full news via search_news tool."""
        from data.search import search_news as fetch_news
        try:
            return await fetch_news(symbol)
        except Exception:
            return {"symbol": symbol, "note": "Use search_news tool to fetch latest news"}
