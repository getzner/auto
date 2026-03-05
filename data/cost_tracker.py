"""
cost_tracker.py — LLM Cost Tracker
Tracks token usage and estimated USD cost per agent call.
Stores in PostgreSQL. Prices are approximate and updated manually.
"""

from datetime import datetime, timezone
from loguru import logger
from data.db import get_db_session

# ── Pricing table (USD per 1M tokens) ────────────────────
# Update prices here when providers change their rates
LLM_PRICING: dict[str, dict] = {
    # OpenAI
    "gpt-4o":              {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":         {"input": 0.15,  "output": 0.60},
    # Anthropic
    "claude-opus-4":       {"input": 15.00, "output": 75.00},
    "claude-sonnet-3-5-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-haiku-20240307":      {"input": 0.25, "output": 1.25},
    "claude-haiku-3":             {"input": 0.25, "output": 1.25},
    # Google
    "gemini-1.5-flash":    {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro":      {"input": 1.25,  "output": 5.00},
    "gemini-2.0-flash":    {"input": 0.10,  "output": 0.40},
    # DeepSeek
    "deepseek-chat":       {"input": 0.14,  "output": 0.28},
    "deepseek-reasoner":   {"input": 0.55,  "output": 2.19},
    # xAI (Grok)
    "grok-2":              {"input": 2.00,  "output": 10.00},
    "grok-2-mini":         {"input": 0.20,  "output": 0.40},
    # Ollama (local — free)
    "llama3.2":            {"input": 0.0,   "output": 0.0},
    "llama3.2:3b":         {"input": 0.0,   "output": 0.0},
    "llama3.2:1b":         {"input": 0.0,   "output": 0.0},
    "mistral-nemo":        {"input": 0.0,   "output": 0.0},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated USD cost for a single LLM call."""
    pricing = LLM_PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost, 8)


async def record_cost(
    agent_name: str,
    model: str,
    symbol: str,
    input_tokens: int,
    output_tokens: int,
    decision_id: int | None = None,
) -> None:
    """Save a single LLM call cost record to the database."""
    cost_usd = estimate_cost(model, input_tokens, output_tokens)
    try:
        async with get_db_session() as conn:
            await conn.execute(
                """
                INSERT INTO llm_costs
                    (ts, agent_name, model, symbol, input_tokens, output_tokens, cost_usd, decision_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                datetime.now(timezone.utc),
                agent_name, model, symbol,
                input_tokens, output_tokens, cost_usd,
                decision_id,
            )
            logger.debug(
                f"[COST] {agent_name} | {model} | in={input_tokens} out={output_tokens} "
                f"| ${cost_usd:.6f}"
            )
    except Exception as e:
        logger.error(f"[COST] Failed to record cost: {e}")


async def get_cost_summary() -> dict:
    """Return cost summary stats for the dashboard."""
    try:
        async with get_db_session() as conn:
            # Total costs per agent
            by_agent = await conn.fetch(
                """
                SELECT agent_name, model,
                       COUNT(*)           AS calls,
                       SUM(input_tokens)  AS total_input_tokens,
                       SUM(output_tokens) AS total_output_tokens,
                       SUM(cost_usd)      AS total_cost_usd
                FROM llm_costs
                GROUP BY agent_name, model
                ORDER BY total_cost_usd DESC
                """
            )
            # Costs per day (last 30 days)
            by_day = await conn.fetch(
                """
                SELECT DATE(ts) AS day, SUM(cost_usd) AS daily_cost
                FROM llm_costs
                WHERE ts >= NOW() - INTERVAL '30 days'
                GROUP BY DATE(ts)
                ORDER BY day
                """
            )
            # Costs per cycle (per decision)
            by_cycle = await conn.fetch(
                """
                SELECT decision_id, SUM(cost_usd) AS cycle_cost, MIN(ts) AS ts
                FROM llm_costs
                WHERE decision_id IS NOT NULL
                GROUP BY decision_id
                ORDER BY ts DESC LIMIT 20
                """
            )
            # Totals
            totals = await conn.fetchrow(
                "SELECT SUM(cost_usd) AS total, COUNT(*) AS calls FROM llm_costs"
            )
    except Exception as e:
        logger.error(f"[COST] Failed to fetch cost summary: {e}")
        return {"by_agent":[], "by_day":[], "by_cycle":[], "total_usd":0, "total_calls":0}

    return {
        "by_agent":  [dict(r) for r in by_agent],
        "by_day":    [{"day": str(r["day"]), "cost": float(r["daily_cost"])} for r in by_day],
        "by_cycle":  [dict(r) for r in by_cycle],
        "total_usd": float(totals["total"] or 0),
        "total_calls": int(totals["calls"] or 0),
    }
