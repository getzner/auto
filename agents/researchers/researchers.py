"""
researchers.py — Bull & Bear Researcher Agents
Bull: GPT-4o  |  Bear: Claude Sonnet
Both receive all analyst reports and build opposing theses via structured debate.
"""

import os
import json
from langchain_deepseek import ChatDeepSeek
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger


BULL_SYSTEM = """You are a bullish crypto researcher. Your job is to construct the strongest
possible LONG case from the analyst reports provided, challenging the bear case.

Respond with ONLY valid JSON:
{
  "researcher": "BullResearcher",
  "thesis": "LONG",
  "conviction": <0-10 integer>,
  "strongest_signals": ["<signal1>", "<signal2>", "<signal3>"],
  "entry_zone": "<price range or level>",
  "target": "<price target>",
  "invalidation": "<what would kill this thesis>",
  "rebuttal_to_bears": "<1-2 sentences>",
  "summary": "<2-3 sentence bull thesis>"
}
"""

BEAR_SYSTEM = """You are a bearish crypto researcher. Your job is to construct the strongest
possible SHORT/STAY-OUT case from the analyst reports provided, challenging the bull case.

Respond with ONLY valid JSON:
{
  "researcher": "BearResearcher",
  "thesis": "SHORT",
  "conviction": <0-10 integer>,
  "strongest_signals": ["<signal1>", "<signal2>", "<signal3>"],
  "entry_zone": "<price range or level>",
  "target": "<price target>",
  "invalidation": "<what would kill this thesis>",
  "rebuttal_to_bulls": "<1-2 sentences>",
  "summary": "<2-3 sentence bear thesis>"
}
"""


class BullResearcher:
    def __init__(self):
        self.llm = ChatDeepSeek(
            model="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.2,
        )

    async def research(self, symbol: str, analyst_reports: list[dict]) -> dict:
        reports_text = json.dumps(analyst_reports, indent=2)
        messages = [
            SystemMessage(content=BULL_SYSTEM),
            HumanMessage(content=f"Symbol: {symbol}\n\nAnalyst Reports:\n{reports_text}"),
        ]
        try:
            resp = await self.llm.ainvoke(messages)
            content = resp.content
        except Exception as e:
            logger.error(f"[BullResearcher] Error: {e}")
            return {"researcher": "BullResearcher", "thesis": "LONG",
                    "conviction": 0, "summary": str(e)}

        import re
        m = re.search(r'\{[\s\S]*\}', content)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return {"researcher": "BullResearcher", "thesis": "LONG",
                "conviction": 0, "summary": content}


class BearResearcher:
    def __init__(self):
        self.llm = ChatDeepSeek(
            model="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.2,
        )

    async def research(self, symbol: str, analyst_reports: list[dict]) -> dict:
        reports_text = json.dumps(analyst_reports, indent=2)
        messages = [
            SystemMessage(content=BEAR_SYSTEM),
            HumanMessage(content=f"Symbol: {symbol}\n\nAnalyst Reports:\n{reports_text}"),
        ]
        try:
            resp = await self.llm.ainvoke(messages)
            content = resp.content
        except Exception as e:
            logger.error(f"[BearResearcher] Error: {e}")
            return {"researcher": "BearResearcher", "thesis": "SHORT",
                    "conviction": 0, "summary": str(e)}

        import re
        m = re.search(r'\{[\s\S]*\}', content)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return {"researcher": "BearResearcher", "thesis": "SHORT",
                "conviction": 0, "summary": content}
