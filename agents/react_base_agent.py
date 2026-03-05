"""
react_base_agent.py — ReAct Base Class for Tool-Calling Analyst Agents
Extends BaseAnalyst with LangChain ReAct agent loop.
Agents can now call: get_indicators, get_current_price, get_orderbook,
                     search_news, run_backtest, execute_python
"""

from __future__ import annotations
import json
import re
from loguru import logger
from langchain_core.messages import HumanMessage, SystemMessage
from data.cost_tracker import record_cost


REACT_SYSTEM_SUFFIX = """
You have access to the following tools. Use them to gather additional data before making your final decision.
Think step by step. For each tool call, briefly explain WHY you are calling it.

After gathering enough data, output your final analysis as ONLY this JSON (no other text):
{json_format}

Tool-calling steps:
1. Identify what data you need
2. Call relevant tools
3. Analyze the combined data
4. Output your JSON conclusion
"""


class ReActBaseAnalyst:
    """
    ReAct analyst — uses LangChain agent executor to call tools autonomously.
    Drop-in replacement for BaseAnalyst subclasses.
    """

    name: str = "ReActBaseAnalyst"

    # Class-level cache for prompts to avoid DB overhead
    _prompt_cache: dict[str, str] = {}
    _last_cache_update: float = 0
    _CACHE_TTL: int = 300  # 5 minutes

    def __init__(self, llm, tools: list, json_format: str):
        """
        Args:
            llm:         LangChain ChatModel (DeepSeek, Claude, etc.)
            tools:       List of @tool functions the agent can call
            json_format: Expected JSON schema string for the final output
        """
        self.llm         = llm
        self.tools       = tools
        self.json_format = json_format
        self._agent      = None

    def _build_agent(self):
        """Lazily build the LangChain ReAct agent."""
        if self._agent is not None:
            return self._agent
        try:
            from langgraph.prebuilt import create_react_agent
            self._agent = create_react_agent(
                self.llm.bind_tools(self.tools),
                tools=self.tools,
            )
        except ImportError:
            logger.warning(f"[{self.name}] langgraph not available, falling back to direct LLM")
            self._agent = None
        return self._agent

    async def get_system_prompt(self) -> str:
        """Fetch system prompt from DB (with caching) or fallback to hardcoded."""
        import time
        from data.db import get_db_conn
        
        now = time.time()
        # Check cache first
        if self.name in self._prompt_cache and (now - self._last_cache_update < self._CACHE_TTL):
            return self._prompt_cache[self.name]

        try:
            conn = await get_db_conn()
            row = await conn.fetchrow(
                "SELECT prompt_text FROM agent_prompts WHERE agent_name = $1",
                self.name
            )
            await conn.close()
            
            if row:
                prompt = row["prompt_text"]
                self._prompt_cache[self.name] = prompt
                self._last_cache_update = now
                return prompt
        except Exception as e:
            logger.warning(f"[{self.name}] Could not fetch prompt from DB: {e}")

        # Fallback to class property (which subclasses should override)
        return self.default_system_prompt

    @property
    def default_system_prompt(self) -> str:
        return f"You are {self.name}, an expert trading analyst."

    async def get_data(self, symbol: str) -> dict:
        """Minimal seed data — agents fetch what they need via tools."""
        return {"symbol": symbol}

    async def analyze(self, symbol: str, decision_id: int | None = None) -> dict:
        """Run the ReAct agent loop with tool-calling."""
        import os

        # Seed data (subclasses can override get_data for initial context)
        seed_data = await self.get_data(symbol)

        # ── ChromaDB Memory Recall ────────────────────────
        memory_context = ""
        try:
            from data.chroma_memory import recall_similar, format_memories_for_prompt
            memories = await recall_similar(self.name, current_conditions=seed_data, n_results=3)
            if memories:
                memory_context = "\n\n" + format_memories_for_prompt(memories)
        except Exception as mem_err:
            logger.debug(f"[{self.name}] Memory recall skipped: {mem_err}")

        system_prompt = await self.get_system_prompt()
        system = (
            system_prompt
            + REACT_SYSTEM_SUFFIX.format(json_format=self.json_format)
            + memory_context
        )

        initial_msg = (
            f"Analyze {symbol}.\n"
            f"Initial context: {json.dumps(seed_data, default=str)}\n\n"
            "Use your tools to gather additional data, then provide your final JSON analysis."
        )

        agent = self._build_agent()

        if agent:
            # ── Full ReAct loop via langgraph ─────────────
            response_content = await self._run_react_agent(agent, system, initial_msg)
        else:
            # ── Fallback: direct LLM call ─────────────────
            response_content = await self._run_direct(system, initial_msg)

        # Track cost (approximate — langgraph doesn't expose token counts easily)
        model = self._get_model_name()
        await record_cost(
            agent_name=self.name, model=model, symbol=symbol,
            input_tokens=800, output_tokens=400,  # approximate for ReAct
            decision_id=decision_id,
        )

        return self._parse_response(symbol, response_content)

    async def _run_react_agent(self, agent, system: str, user_msg: str) -> str:
        """Execute the LangGraph ReAct agent and extract the final message."""
        try:
            messages = [
                SystemMessage(content=system),
                HumanMessage(content=user_msg),
            ]
            result = await agent.ainvoke({"messages": messages})
            final_messages = result.get("messages", [])
            # Get the last AI message
            for msg in reversed(final_messages):
                if hasattr(msg, "content") and msg.content:
                    content = msg.content
                    if isinstance(content, str) and "{" in content:
                        return content
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                return block["text"]
            return str(final_messages[-1].content) if final_messages else ""
        except Exception as e:
            logger.error(f"[{self.name}] ReAct agent error: {e}")
            return await self._run_direct(system, user_msg)

    async def _run_direct(self, system: str, user_msg: str) -> str:
        """Fallback: single direct LLM call with tool descriptions in prompt."""
        import os
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user_msg),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            err_str = str(e).lower()
            is_quota = any(k in err_str for k in ("429", "quota", "rate", "resource_exhausted"))
            if is_quota:
                ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
                ollama_url   = os.getenv("OLLAMA_URL", "http://localhost:11434")
                logger.warning(f"[{self.name}] Falling back to Ollama/{ollama_model}")
                from langchain_ollama import ChatOllama
                fallback = ChatOllama(model=ollama_model, base_url=ollama_url)
                resp = await fallback.ainvoke(messages)
                return resp.content
            raise

    def _get_model_name(self) -> str:
        for attr in ("model", "model_name", "model_id"):
            val = getattr(self.llm, attr, None)
            if val:
                return str(val)
        return "unknown"

    def _parse_response(self, symbol: str, content: str) -> dict:
        """Extract JSON from LLM output."""
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                parsed.setdefault("analyst", self.name)
                parsed.setdefault("symbol", symbol)
                return parsed
            except json.JSONDecodeError:
                pass
        return {
            "analyst":    self.name,
            "symbol":     symbol,
            "signal":     "NEUTRAL",
            "confidence": 0,
            "summary":    content[:500],
        }
