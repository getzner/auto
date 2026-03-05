"""
meta_agent.py — Meta-Agent: Orchestrates Weekly Agent Self-Improvement
Evaluates all analysts, identifies weak performers, and triggers improvement cycles.
"""

import os
import json
from datetime import datetime, timezone
from loguru import logger
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from utils.config import get_env_string


META_SYSTEM_PROMPT = """You are the MetaAgent — a senior AI trading strategist responsible for improving the performance of a team of trading analysts.

Your role:
1. Evaluate each analyst's historical accuracy and identify weaknesses
2. Design improved strategies and conditions for underperforming agents
3. Request backtests to validate improvements before deploying them
4. Write concise improvement reports

You have access to:
- Agent performance data (hit rates, accuracy, trade outcomes)
- Backtest capabilities (test conditions on historical data)
- The ability to suggest improved entry conditions and prompt modifications

Always respond in JSON format with this structure:
{
    "evaluation": {
        "agent_name": {"accuracy": 0.0, "assessment": "...", "main_weakness": "..."}
    },
    "improvement_target": "agent_name",
    "improvement_plan": {
        "problem": "...",
        "hypothesis": "...",
        "proposed_conditions": [{"indicator": "...", "op": "...", "value": ...}],
        "backtest_request": {"direction": "long", "stop_loss_pct": 0.02, "take_profit_pct": 0.04}
    },
    "summary": "..."
}"""


class MetaAgent:
    """Orchestrates weekly review and improvement cycles for all analyst agents."""

    def __init__(self, model_name: str = "llama3.2"):
        self.model_name = model_name
        self.model = ChatOllama(
            base_url=get_env_string("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=model_name,
            temperature=0.1
        )
        # For senior strategy, we can use DeepSeek if API key is available, else fallback to Ollama
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if api_key:
            from langchain_deepseek import ChatDeepSeek
            self.llm = ChatDeepSeek(model="deepseek-chat", api_key=api_key, temperature=0.3)
        else:
            self.llm = self.model

    async def get_agent_performance(self) -> dict:
        """Load hit rates and decision history for all agents from DB."""
        from data.db import get_db_conn
        conn = await get_db_conn()
        try:
            # Get agent-level signals from decisions (from reasoning JSON)
            rows = await conn.fetch("""
                SELECT d.symbol, d.direction as final_direction,
                       p.pnl_usdt, p.status,
                       d.reasoning, d.ts
                FROM decisions d
                LEFT JOIN positions p ON p.decision_id = d.id
                WHERE d.approved = true
                ORDER BY d.ts DESC
                LIMIT 100
            """)
        finally:
            await conn.close()

        if not rows:
            return {"note": "No completed trades yet — run more cycles first"}

        # Parse analyst signals vs final outcome
        agent_stats = {}
        for row in rows:
            try:
                reasoning = json.loads(row["reasoning"]) if isinstance(row["reasoning"], str) else row["reasoning"]
                analyst_reports = reasoning.get("analyst_reports", [])
                trade_won = row["pnl_usdt"] is not None and float(row["pnl_usdt"] or 0) > 0
                final_dir = row["final_direction"]

                for report in analyst_reports:
                    name   = report.get("analyst", "unknown")
                    signal = report.get("signal", "NEUTRAL")
                    conf   = report.get("confidence", 0)

                    if name not in agent_stats:
                        agent_stats[name] = {"correct": 0, "total": 0, "signals": []}

                    agent_stats[name]["total"] += 1
                    # Correct if signal direction matches final outcome
                    signal_dir = "LONG" if signal == "BULLISH" else "SHORT" if signal == "BEARISH" else None
                    if signal_dir and signal_dir == final_dir and trade_won:
                        agent_stats[name]["correct"] += 1
                    elif signal == "NEUTRAL":
                        pass  # neutrals don't count as wrong
                    agent_stats[name]["signals"].append({"signal": signal, "confidence": conf})
            except Exception:
                continue

        # Compute accuracy
        performance = {}
        for name, stats in agent_stats.items():
            if stats["total"] > 0:
                accuracy = stats["correct"] / stats["total"]
                performance[name] = {
                    "accuracy":   round(accuracy, 3),
                    "total":      stats["total"],
                    "correct":    stats["correct"],
                    "assessment": (
                        "STRONG" if accuracy >= 0.65 else
                        "OK"     if accuracy >= 0.50 else
                        "WEAK"   if accuracy >= 0.35 else
                        "POOR"
                    )
                }
        return performance

    async def review_and_improve(self, symbol: str = "BTC/USDT") -> dict:
        """
        Weekly review: evaluate agents and trigger improvement for weakest performer.
        Returns improvement plan + backtest results.
        """
        from backtest.auto_backtest import run_backtest
        from data.discord_notifier import notify_system

        logger.info("[META] Starting weekly review cycle")

        performance = await self.get_agent_performance()
        if "note" in performance:
            logger.info(f"[META] {performance['note']}")
            return performance

        # Ask LLM to evaluate and design improvement
        perf_str = json.dumps(performance, indent=2)
        messages = [
            SystemMessage(content=META_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Symbol: {symbol}\n"
                f"Agent performance data:\n{perf_str}\n\n"
                f"Date: {datetime.now(timezone.utc).date()}\n\n"
                "Evaluate all agents, identify the weakest performer, "
                "and design an improved set of entry conditions to backtest."
            )),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            content = response.content
            json_match = __import__("re").search(r'\{[\s\S]*\}', content)
            plan = json.loads(json_match.group()) if json_match else {"raw": content}
        except Exception as e:
            logger.error(f"[META] LLM error: {e}")
            return {"error": str(e)}

        # Auto-run backtest if plan includes one
        backtest_result = None
        if "improvement_plan" in plan and "proposed_conditions" in plan.get("improvement_plan", {}):
            imp = plan["improvement_plan"]
            strategy = {
                "name":              f"MetaAgent_Improved_{plan.get('improvement_target', 'unknown')}",
                "direction":         imp.get("backtest_request", {}).get("direction", "long"),
                "entry_conditions":  imp["proposed_conditions"],
                "stop_loss_pct":     imp.get("backtest_request", {}).get("stop_loss_pct", 0.02),
                "take_profit_pct":   imp.get("backtest_request", {}).get("take_profit_pct", 0.04),
            }
            logger.info(f"[META] Running backtest for: {strategy['name']}")
            backtest_result = await run_backtest(strategy, symbol)
            plan["backtest_result"] = backtest_result

        # Save improvement plan to DB
        await self._save_review(plan, performance)

        # Discord notification
        assessment = backtest_result.get("assessment", "N/A") if backtest_result else "pending"
        winrate    = backtest_result.get("winrate", 0) if backtest_result else 0
        target     = plan.get("improvement_target", "unknown")
        summary    = plan.get("summary", "Weekly review complete")

        await notify_system(
            f"🧠 Meta-Agent Weekly Review",
            f"**Target:** {target}\n**Backtest:** {assessment} ({winrate:.0%} winrate)\n{summary}",
            level="info"
        )

        logger.info(f"[META] Review complete. Target: {target}, Backtest: {assessment}")
        return plan

    async def apply_improvement(self, target_agent: str, new_prompt: str) -> bool:
        """Update an agent's system prompt in the database."""
        from data.db import get_db_conn
        conn = await get_db_conn()
        try:
            logger.info(f"[META] Applying improved prompt to {target_agent}")
            await conn.execute("""
                UPDATE agent_prompts 
                SET prompt_text = $1, version = version + 1, ts_updated = NOW()
                WHERE agent_name = $2
            """, new_prompt, target_agent)
            return True
        except Exception as e:
            logger.error(f"[META] Failed to apply improvement: {e}")
            return False
        finally:
            await conn.close()

    async def spawn_challenger(self, parent_agent: str, experimental_prompt: str) -> bool:
        """Register a challenger agent for shadow testing."""
        from data.db import get_db_conn
        conn = await get_db_conn()
        try:
            challenger_name = f"{parent_agent}_Challenger"
            logger.info(f"[META] Spawning challenger for {parent_agent}")
            
            # 1. Update/Insert into agent_prompts (using a specific naming convention)
            await conn.execute("""
                INSERT INTO agent_prompts (agent_name, prompt_text, version)
                VALUES ($1, $2, 1)
                ON CONFLICT (agent_name) DO UPDATE SET prompt_text = EXCLUDED.prompt_text, version = agent_prompts.version + 1
            """, challenger_name, experimental_prompt)
            
            # 2. Add to active challengers in system_config
            row = await conn.fetchrow("SELECT value FROM system_config WHERE key = 'active_challengers'")
            active = json.loads(row["value"]) if row else []
            if challenger_name not in active:
                active.append(challenger_name)
                await conn.execute("""
                    INSERT INTO system_config (key, value) VALUES ('active_challengers', $1)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, json.dumps(active))
            
            return True
        except Exception as e:
            logger.error(f"[META] Failed to spawn challenger: {e}")
            return False
        finally:
            await conn.close()

    async def process_human_feedback(self) -> dict:
        """Processes pending human feedback and updates agent prompts."""
        from data.db import get_db_conn
        conn = await get_db_conn()
        try:
            feedbacks = await conn.fetch("SELECT * FROM human_feedback WHERE status = 'pending'")
            if not feedbacks:
                return {"message": "No pending feedback found"}
            
            processed = 0
            for fb in feedbacks:
                decision_id = fb["decision_id"]
                feedback_text = fb["feedback_text"]
                
                # Fetch original decision reasoning
                row = await conn.fetchrow("SELECT reasoning FROM decisions WHERE id = $1", decision_id)
                if not row:
                    await conn.execute("UPDATE human_feedback SET status='failed', optimizer_note='Decision not found' WHERE id=$1", fb["id"])
                    continue
                
                reasoning = json.loads(row["reasoning"]) if isinstance(row["reasoning"], str) else row["reasoning"]
                
                prompt = f"""You are the Meta Optimizer.
A human trader gave feedback on a past trade decision.
Feedback: "{feedback_text}"
Original AI Reasoning: {json.dumps(reasoning)}

1. Identify which analyst(s) contributed to the mistake according to the feedback.
2. Formulate a 1-sentence prompt rule to append to that analyst's core system prompt to prevent this in the future.
3. If multiple analysts are wrong, pick the most directly responsible one (e.g., 'VolumeAnalyst', 'OrderflowAnalyst', 'NewsAnalyst', 'VolumeProfileAnalyst', 'OnchainAnalyst').

Respond ONLY in JSON:
{{
    "target_agent": "AgentName",
    "prompt_addition": "Rule to add...",
    "explanation": "Why this rule helps"
}}
"""
                resp = await self.llm.ainvoke([SystemMessage(content=prompt)])
                try:
                    json_str = __import__("re").search(r'\{[\s\S]*\}', resp.content).group()
                    correction = json.loads(json_str)
                    target = correction.get("target_agent")
                    addition = correction.get("prompt_addition")
                    
                    if target and addition:
                        # Append to agent's current prompt
                        curr_prompt = await conn.fetchval("SELECT prompt_text FROM agent_prompts WHERE agent_name = $1", target)
                        if not curr_prompt:
                            from agents.react_base_agent import ReactBaseAgent
                            # Rough fallback, real agents subclass this but we just need a base if missing
                            curr_prompt = f"You are {target}, an expert trading analyst."
                            
                        new_prompt = curr_prompt + "\n\nCRITICAL HUMAN FEEDBACK RULE:\n- " + addition
                        
                        await conn.execute("""
                            INSERT INTO agent_prompts (agent_name, prompt_text) VALUES ($1, $2)
                            ON CONFLICT (agent_name) DO UPDATE SET prompt_text = EXCLUDED.prompt_text, updated_at = NOW()
                        """, target, new_prompt)
                        
                        await conn.execute("UPDATE human_feedback SET status='processed', optimizer_note=$1 WHERE id=$2",
                                           f"Updated {target}: {addition}", fb["id"])
                        processed += 1
                        logger.info(f"[META] Human feedback applied to {target}")
                except Exception as e:
                    logger.error(f"[META] Failed to parse correction: {e}")
                    await conn.execute("UPDATE human_feedback SET status='failed', optimizer_note=$1 WHERE id=$2", str(e), fb["id"])
                    
            return {"message": f"Processed {processed} feedback items"}
        finally:
            await conn.close()

    async def tune_parameters(self, metrics: dict, market_context: dict) -> dict:
        """
        Analyze performance vs market context to propose new scanner/risk params.
        Proposals are saved to system_config.
        """
        prompt = f"""You are an expert quantitative strategist tuning a trading system.
Recent Performance: {json.dumps(metrics)}
Market Context (Volatility/Trend): {json.dumps(market_context)}

Current logic:
- If volatility is high, we should tighten risk and widen scanner thresholds to avoid noise.
- If win rate is low, we might need more conservative entry thresholds.

Proposed changes for 'scanner_thresholds' and 'risk_limits'.
Respond with ONLY JSON:
{{
  "scanner_thresholds": {{ "volatility_zscore": <float>, "volume_spike_multi": <float> }},
  "risk_limits": {{ "max_risk_pct": <float>, "max_positions": <int> }},
  "reasoning": "<string>"
}}
"""
        response = await self.model.ainvoke([SystemMessage(content=prompt)])
        try:
            tuning = json.loads(response.content)
            from data.db import get_db_conn
            conn = await get_db_conn()
            
            # Save to system_config
            for key in ["scanner_thresholds", "risk_limits"]:
                if key in tuning:
                    await conn.execute("""
                        INSERT INTO system_config (key, value) VALUES ($1, $2)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """, key, json.dumps(tuning[key]))
            
            await conn.close()
            logger.info(f"[META] Hyperparameters tuned: {tuning.get('reasoning')}")
            return tuning
        except Exception as e:
            logger.error(f"[META] Failed to parse/save tuning: {e}")
            return {}

    async def _save_review(self, plan: dict, performance: dict) -> None:
        """Persist the review to the DB for audit trail."""
        from data.db import get_db_conn
        conn = await get_db_conn()
        try:
            await conn.execute("""
                INSERT INTO meta_reviews (ts, plan, performance_snapshot)
                VALUES ($1, $2, $3)
            """,
                datetime.now(timezone.utc),
                json.dumps(plan),
                json.dumps(performance),
            )
        except Exception as e:
            logger.warning(f"[META] Could not save review (table may not exist yet): {e}")
        finally:
            await conn.close()
