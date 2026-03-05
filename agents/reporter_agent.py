import json
from datetime import datetime, timezone
from loguru import logger
from data.db import get_db_conn
from agents.llm_factory import get_llm
from utils.config import get_env_string

class ReporterAgent:
    """
    Analyzes closed trades and generates a "Post-Mortem" Trade Journal entry.
    """
    def __init__(self):
        self.llm = get_llm(agent_name="reporter")

    async def generate_journal_entry(self, position_id: int):
        """
        Gathers data for a closed trade and generates an AI reflection.
        """
        logger.info(f"[REPORTER] Generating post-mortem for position {position_id}...")
        
        conn = await get_db_conn()
        try:
            # 1. Fetch position and its decision
            pos = await conn.fetchrow(
                "SELECT * FROM positions WHERE id=$1 AND status='closed'",
                position_id
            )
            if not pos:
                logger.warning(f"[REPORTER] Position {position_id} not found or not closed.")
                return

            decision = await conn.fetchrow(
                "SELECT * FROM decisions WHERE id=$1",
                pos["decision_id"]
            )
            
            # 2. Prepare context for LLM
            context = {
                "symbol": pos["symbol"],
                "side": pos["side"],
                "entry_price": float(pos["entry_price"]),
                "close_price": float(pos["close_price"]),
                "pnl_usdt": float(pos["pnl_usdt"] or 0),
                "duration": str(pos["closed_at"] - pos["opened_at"]),
                "planned_sl": float(pos["stop_loss"]) if pos["stop_loss"] else None,
                "planned_tp": float(pos["take_profit"]) if pos["take_profit"] else None,
                "analyst_logic": decision["reasoning"] if decision else "No decision data found"
            }

            # 3. Request AI reflection
            prompt = f"""
            You are the Head of Risk & Strategy. Examine this closed trade and provide a critical post-mortem.
            
            TRADE DATA:
            {json.dumps(context, indent=2, default=str)}
            
            Generate a JSON response with the following keys:
            - summary: A 2-sentence recap of what happened.
            - performance_score: 0-100 rating based on how well the trade followed the logic vs the outcome.
            - lessons_learned: a list of 3 bullet points for future improvement.
            - agent_critique: how well did the analysts predict the move? Were they blindsided?
            """

            resp = await self.llm.ainvoke(prompt)
            # Remove markdown formatting if present
            content = resp.content.replace("```json", "").replace("```", "").strip()
            reflection = json.loads(content)

            # 4. Save to trade_journal
            await conn.execute(
                """
                INSERT INTO trade_journal 
                    (position_id, decision_id, summary, performance_score, 
                     lessons_learned, agent_critique, market_context)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (position_id) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    performance_score = EXCLUDED.performance_score,
                    lessons_learned = EXCLUDED.lessons_learned,
                    agent_critique = EXCLUDED.agent_critique
                """,
                position_id, pos["decision_id"], 
                reflection["summary"], reflection["performance_score"],
                json.dumps(reflection["lessons_learned"]),
                reflection["agent_critique"],
                json.dumps({"exit_price": float(pos["close_price"]), "pnl": float(pos["pnl_usdt"] or 0)})
            )
            
            logger.info(f"[REPORTER] ✅ Journal entry saved for position {position_id}")
            return reflection

        except Exception as e:
            logger.error(f"[REPORTER] ❌ Failed to generate journal: {e}")
        finally:
            await conn.close()
