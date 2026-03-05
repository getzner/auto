import os
import json
from agents.react_base_agent import ReActBaseAnalyst
from agents.llm_factory import get_llm
from agents.tools.market_tools import (
    get_indicators,
    get_current_price,
    get_orderbook,
    search_news,
    run_backtest,
    check_absorption
)
from loguru import logger

# Map tool names to actual functions
TOOL_MAP = {
    "get_indicators": get_indicators,
    "get_current_price": get_current_price,
    "get_orderbook": get_orderbook,
    "search_news": search_news,
    "run_backtest": run_backtest,
    "check_absorption": check_absorption
}

GENERIC_JSON_FORMAT = """{
  "analyst": "<skill_name>",
  "symbol": "<symbol>",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <0-10 integer>,
  "key_findings": ["<finding1>", "<finding2>"],
  "summary": "<2-3 sentences explanation of the theory-based analysis>"
}"""

class GenericSkillAnalyst(ReActBaseAnalyst):
    def __init__(self, skill_id: str, llm=None):
        self.skill_id = skill_id
        self.skill_data = self._load_skill_data(skill_id)
        self.name = self.skill_data.get("name", "GenericAnalyst")
        
        if llm is None:
            # check for override in skill_data
            override = self.skill_data.get("model_override")
            if override and ":" in override:
                provider, model = override.split(":")
            else:
                provider = os.getenv("SKILL_ANALYST_PROVIDER", "deepseek")
                model = os.getenv("SKILL_ANALYST_MODEL", "deepseek-chat")
            
            # We pass the custom agent_name to the factory so it can be overridden live!
            # e.g., skill_elliott_wave
            llm = get_llm(
                provider=provider,
                model=model,
                temperature=0.1,
                agent_name=f"skill_{skill_id}"
            )
            
        # Select tools based on registry
        skill_tools = []
        for tool_name in self.skill_data.get("required_tools", []):
            if tool_name in TOOL_MAP:
                skill_tools.append(TOOL_MAP[tool_name])
            else:
                logger.warning(f"[SkillAnalyst] Tool {tool_name} not found in TOOL_MAP")
        
        # Fallback to standard tools if none specified
        if not skill_tools:
            skill_tools = [get_indicators, get_current_price]

        super().__init__(
            llm=llm,
            tools=skill_tools,
            json_format=GENERIC_JSON_FORMAT.replace("<skill_name>", self.name)
        )

    def _load_skill_data(self, skill_id: str) -> dict:
        registry_path = "/opt/trade_server/agents/skills/registry.json"
        if not os.path.exists("/opt/trade_server"):
             registry_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "skills", "registry.json"))
        
        try:
            with open(registry_path, "r") as f:
                registry = json.load(f)
                return registry.get(skill_id, {})
        except Exception as e:
            logger.error(f"[SkillAnalyst] Error loading registry: {e}")
            return {}

    @property
    def system_prompt(self) -> str:
        base_prompt = self.skill_data.get("system_prompt", "You are a specialized trading analyst.")
        return f"{base_prompt}\n\nStrictly follow your specific theoretical framework to provide a unique perspective."
