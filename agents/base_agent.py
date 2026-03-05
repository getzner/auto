"""
base_agent.py — Base class for all analyst agents.
Each analyst receives its data summary, runs an LLM call, and returns
a structured JSON report. Token usage and cost are automatically tracked.

Key safeguards:
  - LLM_SEMAPHORE: limits concurrent LLM calls to prevent OOM on the VPS
  - LLM_TIMEOUT:   per-call timeout to prevent infinite hangs
"""

from __future__ import annotations
import asyncio
import os
from abc import ABC, abstractmethod

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from data.cost_tracker import record_cost

# ── Concurrency guard (prevent OOM on 8GB VPS) ───────────
# Each Ollama call uses ~400MB RAM. With 6+ agents running in parallel, 
# this causes OOM kills. Limit to 3 concurrent LLM calls max.
_MAX_CONCURRENT_LLM = int(os.getenv("MAX_CONCURRENT_LLM", "3"))
_LLM_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT_LLM)

# ── Per-call timeout (prevent infinite hangs) ────────────
_LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT_SECONDS", "90"))


class BaseAnalyst(ABC):
    """Shared interface for all analyst agents."""

    # Class-level cache for prompts to avoid DB overhead
    _prompt_cache: dict[str, str] = {}
    _last_cache_update: float = 0
    _CACHE_TTL: int = 300  # 5 minutes

    def __init__(self, llm):
        self.llm = llm

    @abstractmethod
    async def get_data(self, symbol: str) -> dict:
        """Fetch the relevant data summary dict for this analyst."""
        ...

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
        return self.system_prompt  # Subclasses should still provide a property

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The analyst's persona and reporting instructions."""
        ...

    def _build_user_message(self, symbol: str, data: dict) -> str:
        import json
        return (
            f"Symbol: {symbol}\n"
            f"Data:\n{json.dumps(data, indent=2, default=str)}\n\n"
            "Provide your analysis report."
        )

    def _get_model_name(self) -> str:
        """Extract model name from LLM instance."""
        for attr in ("model", "model_name", "model_id"):
            val = getattr(self.llm, attr, None)
            if val:
                return str(val)
        return "unknown"

    async def analyze(self, symbol: str, decision_id: int | None = None) -> dict:
        """Run the full analyst pipeline, track cost, and return a structured report.
        If the primary LLM fails with a quota/rate-limit error, falls back to Ollama.
        Automatically recalls relevant past memories from ChromaDB.
        """
        import os
        data = await self.get_data(symbol)
        if not data:
            logger.warning(f"[{self.name}] No data for {symbol}")
            return {"analyst": self.name, "symbol": symbol, "signal": "NEUTRAL",
                    "confidence": 0, "summary": "No data available."}

        # ── ChromaDB Memory Recall ────────────────────────
        memory_context = ""
        try:
            from data.chroma_memory import recall_similar, format_memories_for_prompt
            memories = await recall_similar(self.name, current_conditions=data, n_results=3)
            if memories:
                memory_context = "\n\n" + format_memories_for_prompt(memories)
        except Exception as mem_err:
            logger.debug(f"[{self.name}] Memory recall skipped: {mem_err}")

        # ── Explicit Markdown Instruction Recal ────────────────
        md_memory_path = f"/opt/trade_server/data/memories/{self.name}.md"
        if not os.path.exists("/opt/trade_server"):
            md_memory_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "memories", f"{self.name}.md"))
            
        md_instructions = ""
        if os.path.exists(md_memory_path):
            try:
                with open(md_memory_path, "r") as f:
                    md_instructions = "\n\n" + f.read()
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to read MD memory: {e}")

        system_prompt = await self.get_system_prompt()
        messages = [
            SystemMessage(content=system_prompt + memory_context + md_instructions),
            HumanMessage(content=self._build_user_message(symbol, data)),
        ]

        llm_to_use = self.llm
        model = self._get_model_name()

        try:
            # ── H1: Per-call timeout to prevent infinite hangs ───
            # ── K3: Semaphore to limit concurrent calls and prevent OOM ─
            async with _LLM_SEMAPHORE:
                response = await asyncio.wait_for(
                    llm_to_use.ainvoke(messages),
                    timeout=_LLM_TIMEOUT
                )

        except asyncio.TimeoutError:
            logger.error(f"[{self.name}] LLM timeout ({_LLM_TIMEOUT}s) — returning NEUTRAL")
            return {"analyst": self.name, "symbol": symbol, "signal": "NEUTRAL",
                    "confidence": 0, "summary": f"LLM timeout after {_LLM_TIMEOUT}s"}

        except Exception as primary_err:
            err_str = str(primary_err).lower()
            is_quota = any(k in err_str for k in ("429", "quota", "rate", "insufficient_quota",
                                                   "resource_exhausted", "unauthorized", "401"))
            if is_quota:
                # ── Fallback to local Ollama ──────────────────
                ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
                ollama_url   = os.getenv("OLLAMA_URL", "http://localhost:11434")
                logger.warning(
                    f"[{self.name}] Primary LLM failed ({primary_err.__class__.__name__}), "
                    f"falling back to Ollama/{ollama_model}"
                )
                try:
                    from langchain_ollama import ChatOllama
                    fallback_llm = ChatOllama(model=ollama_model, base_url=ollama_url)
                    async with _LLM_SEMAPHORE:
                        response = await asyncio.wait_for(
                            fallback_llm.ainvoke(messages),
                            timeout=_LLM_TIMEOUT
                        )
                    model = ollama_model
                except asyncio.TimeoutError:
                    logger.error(f"[{self.name}] Ollama fallback timeout ({_LLM_TIMEOUT}s)")
                    return {"analyst": self.name, "symbol": symbol, "signal": "NEUTRAL",
                            "confidence": 0, "summary": f"Ollama fallback timeout"}
                except Exception as fallback_err:
                    logger.error(f"[{self.name}] Ollama fallback also failed: {fallback_err}")
                    return {"analyst": self.name, "symbol": symbol, "signal": "NEUTRAL",
                            "confidence": 0, "summary": f"All LLMs failed: {primary_err}"}
            else:
                logger.error(f"[{self.name}] LLM error: {primary_err}")
                return {"analyst": self.name, "symbol": symbol, "signal": "NEUTRAL",
                        "confidence": 0, "summary": f"LLM error: {primary_err}"}

        content = response.content

        # ── Extract token usage ───────────────────────
        usage         = getattr(response, "usage_metadata", None) or {}
        input_tokens  = int(usage.get("input_tokens",  0) or usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0) or usage.get("completion_tokens", 0))

        await record_cost(
            agent_name=self.name,
            model=model,
            symbol=symbol,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            decision_id=decision_id,
        )

        return self._parse_response(symbol, content)

    def _parse_response(self, symbol: str, content: str) -> dict:
        """Try to parse JSON from LLM output, fall back to raw text."""
        import json, re
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
            "summary":    content,
        }
