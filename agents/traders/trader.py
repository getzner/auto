"""
trader.py — Trader, Risk Manager, and Portfolio Manager Agents
All run on Ollama (local, free, no latency).
"""

import os
import json
import re
from datetime import datetime, timezone

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from data.db import get_db_conn
from utils.config import get_env_string, get_env_int, get_env_float

OLLAMA_BASE = get_env_string("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = get_env_string("OLLAMA_MODEL", "llama3.2")
MAX_RISK_PCT = get_env_float("MAX_RISK_PER_TRADE_PCT", 2.0)
MAX_POSITIONS = get_env_int("MAX_OPEN_POSITIONS", 3)


def _make_ollama() -> ChatOllama:
    return ChatOllama(base_url=OLLAMA_BASE, model=OLLAMA_MODEL, temperature=0.1)


# ── Helper for Dynamic Prompts ──────────────────────────

async def get_dynamic_prompt(agent_name: str, default_prompt: str) -> str:
    """Fetch prompt from DB with fallback."""
    from data.db import get_db_conn
    try:
        conn = await get_db_conn()
        row = await conn.fetchrow(
            "SELECT prompt_text FROM agent_prompts WHERE agent_name = $1",
            agent_name
        )
        await conn.close()
        if row:
            return row["prompt_text"]
    except Exception as e:
        logger.warning(f"[{agent_name}] Prompt fetch failed: {e}")
    return default_prompt


# ── Trader ────────────────────────────────────────────────

TRADER_SYSTEM_DEFAULT = """You are a decisive crypto trader synthesizing analyst and researcher reports.
Based on the bull and bear theses and analyst signals, make a trade decision.

Respond with ONLY valid JSON:
{
  "direction": "LONG" | "SHORT" | "HOLD",
  "conviction": <0-10>,
  "entry_price": <number or null>,
  "stop_loss": <number or null>,
  "take_profit": <number or null>,
  "risk_reward": <ratio float>,
  "position_size_pct": <% of portfolio, max 100>,
  "reasoning": "<2-3 sentences explaining why>"
}

Rules:
- HOLD if conviction < 6 OR signals conflict strongly
- Always set stop_loss (hard rule)
- Risk/reward must be >= 1.5 minimum to take a trade
- position_size_pct max 25% of portfolio per trade
"""


class TraderAgent:
    def __init__(self):
        self.llm = _make_ollama()

    async def decide(
        self,
        symbol: str,
        current_price: float,
        analyst_reports: list[dict],
        researcher_reports: list[dict],
        market_regime: dict = None,
    ) -> dict:
        payload = {
            "symbol": symbol,
            "current_price": current_price,
            "market_regime": market_regime or {},
            "analyst_reports": analyst_reports,
            "researcher_reports": researcher_reports,
        }
        
        system_prompt = await get_dynamic_prompt("TraderAgent", TRADER_SYSTEM_DEFAULT)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(payload, indent=2)),
        ]
        try:
            resp = await self.llm.ainvoke(messages)
            m = re.search(r'\{[\s\S]*\}', resp.content)
            if m:
                result = json.loads(m.group())
                result["symbol"] = symbol
                result["current_price"] = current_price
                return result
        except Exception as e:
            logger.error(f"[Trader] Error: {e}")
        return {"direction": "HOLD", "conviction": 0, "reasoning": "Error in trader agent"}


# ── Risk Manager ──────────────────────────────────────────

RISK_SYSTEM_DEFAULT = f"""You are a strict risk manager for a crypto trading system.
Max risk per trade: {MAX_RISK_PCT}% of portfolio.
Max open positions: {MAX_POSITIONS}.

Review the trade proposal and APPROVE or REJECT it.

Respond with ONLY valid JSON:
{{
  "approved": true | false,
  "adjusted_position_size_pct": <float>,
  "rejection_reason": "<string or null>",
  "risk_notes": "<1-2 sentences>"
}}

Reject if:
- No stop loss defined
- Risk/reward < 1.5
- Position size implies > {MAX_RISK_PCT}% account risk
- Conviction < 5
"""


class RiskManager:
    def __init__(self):
        self.llm = _make_ollama()

    async def evaluate(
        self,
        trade_proposal: dict,
        portfolio_balance: float,
        open_positions_count: int,
    ) -> dict:
        # 1. Fetch dynamic limits
        from data.db import get_db_conn
        conn = await get_db_conn()
        try:
            row = await conn.fetchrow("SELECT value FROM system_config WHERE key = 'risk_limits'")
            limits = json.loads(row["value"]) if row else {}
            curr_max_risk = float(limits.get("max_risk_pct", MAX_RISK_PCT))
            curr_max_pos = int(limits.get("max_positions", MAX_POSITIONS))
        except Exception:
            curr_max_risk = MAX_RISK_PCT
            curr_max_pos = MAX_POSITIONS
        finally:
            await conn.close()

        if open_positions_count >= curr_max_pos:
            return {
                "approved": False,
                "adjusted_position_size_pct": 0,
                "rejection_reason": f"Max positions ({curr_max_pos}) already open",
                "risk_notes": "Wait for existing positions to close before opening new ones.",
            }

        payload = {
            "trade_proposal": trade_proposal,
            "portfolio_balance_usdt": portfolio_balance,
            "open_positions": open_positions_count,
            "max_positions": curr_max_pos,
            "max_risk_pct": curr_max_risk,
        }
        
        system_prompt = await get_dynamic_prompt("RiskManager", RISK_SYSTEM_DEFAULT)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(payload, indent=2)),
        ]
        try:
            resp = await self.llm.ainvoke(messages)
            m = re.search(r'\{[\s\S]*\}', resp.content)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logger.error(f"[RiskManager] Error: {e}")
        return {"approved": False, "rejection_reason": "Risk manager error", "risk_notes": ""}


# ── Portfolio Manager ─────────────────────────────────────

PORTFOLIO_SYSTEM_DEFAULT = """You are the portfolio manager — the final gatekeeper before a trade executes.
Review the trade proposal and risk assessment. Make the final decision.

Respond with ONLY valid JSON:
{
  "final_decision": "EXECUTE" | "REJECT",
  "reason": "<brief reason>",
  "priority": "high" | "medium" | "low"
}
"""


class PortfolioManager:
    def __init__(self):
        self.llm = _make_ollama()

    async def approve(
        self,
        trade_proposal: dict,
        risk_assessment: dict,
    ) -> dict:
        if not risk_assessment.get("approved", False):
            return {
                "final_decision": "REJECT",
                "reason": risk_assessment.get("rejection_reason", "Risk rejected"),
                "priority": "low",
            }

        payload = {
            "trade_proposal": trade_proposal,
            "risk_assessment": risk_assessment,
        }
        
        system_prompt = await get_dynamic_prompt("PortfolioManager", PORTFOLIO_SYSTEM_DEFAULT)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(payload, indent=2)),
        ]
        try:
            resp = await self.llm.ainvoke(messages)
            m = re.search(r'\{[\s\S]*\}', resp.content)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logger.error(f"[PortfolioManager] Error: {e}")
        return {"final_decision": "REJECT", "reason": "PM error", "priority": "low"}

    async def save_decision(
        self,
        symbol: str,
        trade_proposal: dict,
        risk_assessment: dict,
        pm_decision: dict,
        analyst_reports: list[dict],
        researcher_reports: list[dict],
    ) -> int | None:
        """Save full decision chain to DB and return decision ID."""
        approved  = pm_decision.get("final_decision") == "EXECUTE"
        direction = trade_proposal.get("direction", "HOLD")

        conn = await get_db_conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO decisions
                    (ts, symbol, direction, confidence, entry_price, stop_loss, take_profit,
                     position_size, reasoning, approved)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                RETURNING id
                """,
                datetime.now(timezone.utc),
                symbol,
                direction,
                float(trade_proposal.get("conviction", 0)) / 10.0,
                trade_proposal.get("entry_price"),
                trade_proposal.get("stop_loss"),
                trade_proposal.get("take_profit"),
                trade_proposal.get("position_size_pct"),
                json.dumps({
                    "analyst_reports":    analyst_reports,
                    "researcher_reports": researcher_reports,
                    "risk_assessment":    risk_assessment,
                    "pm_decision":        pm_decision,
                }),
                approved,
            )
            decision_id = row["id"]
            
            # Save to non_trade tracking if rejected
            if not approved:
                reject_reason = pm_decision.get("reason", risk_assessment.get("rejection_reason", "Rejected"))
                price_at_reject = trade_proposal.get("entry_price") or trade_proposal.get("current_price") or 0.0
                await conn.execute(
                    """
                    INSERT INTO non_trade_outcomes
                        (decision_id, ts, symbol, direction, reject_reason, price_at_reject, analyst_signals)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    decision_id,
                    datetime.now(timezone.utc),
                    symbol,
                    direction,
                    reject_reason,
                    price_at_reject,
                    json.dumps(analyst_reports)
                )
                
            logger.info(f"[Portfolio] Decision saved: id={decision_id} {symbol} {direction} approved={approved}")
            return decision_id
        except Exception as e:
            logger.error(f"[Portfolio] DB save error: {e}")
            return None
        finally:
            await conn.close()
