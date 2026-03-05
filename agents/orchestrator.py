"""
orchestrator.py — LangGraph Agent Workflow
Runs the full agent pipeline every 1h candle close:
  collect_data → analyst_team → researcher_debate → trader → risk_check → portfolio_decision → execute
"""

import asyncio
import os
import json
from dataclasses import dataclass, field
from typing import Annotated, Sequence, TypedDict

from langgraph.graph import StateGraph, END
from loguru import logger

from utils.config import get_env_string, get_env_int, get_env_float
from agents.analysts.react_volume_analyst import ReActVolumeAnalyst as VolumeAnalyst
from agents.analysts.react_orderflow_analyst import ReActOrderflowAnalyst as OrderflowAnalyst
from agents.analysts.react_volume_profile_analyst import ReActVolumeProfileAnalyst as VolumeProfileAnalyst
from agents.analysts.react_onchain_analyst import ReActOnchainAnalyst as OnchainAnalyst
from agents.analysts.react_news_analyst import ReActNewsAnalyst as NewsAnalyst
from agents.analysts.react_gametheory_analyst import ReActGameTheoryAnalyst as GameTheoryAnalyst
from agents.analysts.skill_analyst import GenericSkillAnalyst as SkillAnalyst
from agents.researchers.researchers import BullResearcher, BearResearcher
from agents.traders.trader import TraderAgent, RiskManager, PortfolioManager
from data.volume import save_volume_delta
from data.volume_profile import compute_and_save_profile
from data.orderflow import compute_and_save_orderflow
from data.onchain import collect_and_save
from data.db import get_db_conn

TRADE_MODE = get_env_string("TRADE_MODE", "paper")


# ── LangGraph State ───────────────────────────────────────

class TradingState(TypedDict):
    symbol:             str
    current_price:      float
    market_regime:      dict
    analyst_reports:    list[dict]
    researcher_reports: list[dict]
    trade_proposal:     dict
    risk_assessment:    dict
    pm_decision:        dict
    decision_id:        int | None
    challenger_reports: list[dict]


# ── Node functions ────────────────────────────────────────

async def node_collect_data(state: TradingState) -> TradingState:
    """Refresh all data sources for this symbol, unless kill switch is active."""
    symbol = state["symbol"]
    
    # Check Kill Switch
    safety_path = "/opt/trade_server/data/safety.json"
    if not os.path.exists("/opt/trade_server"):
        safety_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "safety.json"))
    
    if os.path.exists(safety_path):
        try:
            with open(safety_path, "r") as f:
                safety = json.load(f)
                if safety.get("kill_switch", False):
                    logger.warning(f"[ORC] 🛑 KILL SWITCH ACTIVE. Skipping data collection for {symbol}")
                    return state
        except Exception as e:
            logger.error(f"[ORC] Error checking safety: {e}")

    logger.info(f"[ORC] collect_data: {symbol}")
    await asyncio.gather(
        save_volume_delta(symbol, "1h"),
        compute_and_save_profile(symbol, "1h"),
        compute_and_save_profile(symbol, "4h"),
        compute_and_save_profile(symbol, "1d"),
        compute_and_save_orderflow(symbol, "1h"),
        collect_and_save(symbol),
    )
    # Fetch current price
    conn = await get_db_conn()
    try:
        row = await conn.fetchrow(
            "SELECT close FROM candles WHERE symbol=$1 ORDER BY ts DESC LIMIT 1", symbol
        )
        price = float(row["close"]) if row else 0.0
    finally:
        await conn.close()
    return {**state, "current_price": price}

async def node_market_observer(state: TradingState) -> TradingState:
    """Detect current macro market regime (Trending, Ranging, Volatility)."""
    symbol = state["symbol"]
    logger.info(f"[ORC] market_observer: {symbol}")
    try:
        from agents.analysts.market_observer import get_market_regime
        regime = await get_market_regime(symbol)
    except Exception as e:
        logger.error(f"[ORC] Market observer failed: {e}")
        regime = {"regime": "UNKNOWN", "volatility": "UNKNOWN", "weights": {}}
        
    return {**state, "market_regime": regime}

async def node_analyst_team(state: TradingState) -> TradingState:
    """Run core analysts + dynamic skill analysts + challengers in parallel."""
    symbol = state["symbol"]
    logger.info(f"[ORC] analyst_team: {symbol}")
    
    # 1. Map core agents to their configuration keys
    analyst_map = {
        "volume_analyst": VolumeAnalyst,
        "orderflow_analyst": OrderflowAnalyst,
        "vp_analyst": VolumeProfileAnalyst,
        "onchain_analyst": OnchainAnalyst,
        "news_analyst": NewsAnalyst,
        "gametheory_analyst": GameTheoryAnalyst,
    }
    
    overrides_path = "/opt/trade_server/data/model_overrides.json"
    if not os.path.exists("/opt/trade_server"):
        overrides_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "model_overrides.json"))
        
    active_core_keys = list(analyst_map.keys()) # default all
    active_skills = []
    
    if os.path.exists(overrides_path):
        try:
            with open(overrides_path, "r") as f:
                config = json.load(f)
                active_skills = config.get("active_skills", [])
                active_core_keys = config.get("active_core_agents", list(analyst_map.keys()))
        except Exception: pass

    # 2. Queue standard analysts if active
    tasks = []
    for key, c_class in analyst_map.items():
        if key in active_core_keys:
            tasks.append(c_class().analyze(symbol))

    # 3. Queue Dynamic Skill analysts
    for skill_id in active_skills:
        tasks.append(SkillAnalyst(skill_id).analyze(symbol))

    # 3. Challenger agents from DB
    challenger_tasks = []
    conn = await get_db_conn()
    try:
        row = await conn.fetchrow("SELECT value FROM system_config WHERE key = 'active_challengers'")
        active_challengers = json.loads(row["value"]) if row else []
        for c_name in active_challengers:
            # Format: ParentName_Challenger
            parent_name = c_name.split("_")[0]
            if parent_name in analyst_map:
                logger.info(f"[ORC] Running challenger: {c_name}")
                inst = analyst_map[parent_name]()
                inst.name = c_name # Override name so it fetches challenger prompt
                challenger_tasks.append(inst.analyze(symbol))
    except Exception as e:
        logger.error(f"[ORC] Challenger loop error: {e}")
    finally:
        await conn.close()

    # Run everything in parallel
    all_results = list(await asyncio.gather(*(tasks + challenger_tasks)))
    
    reports = all_results[:len(tasks)]
    challenger_reports = all_results[len(tasks):]
    
    logger.info(f"[ORC] analyst_team complete: {len(reports)} primary, {len(challenger_reports)} challengers")
    return {**state, "analyst_reports": list(reports), "challenger_reports": list(challenger_reports)}


async def node_researcher_debate(state: TradingState) -> TradingState:
    """Bull and Bear researchers debate the analyst findings."""
    symbol  = state["symbol"]
    reports = state["analyst_reports"]
    logger.info(f"[ORC] researcher_debate: {symbol}")
    bull, bear = await asyncio.gather(
        BullResearcher().research(symbol, reports),
        BearResearcher().research(symbol, reports),
    )
    logger.info(f"[ORC] bull={bull.get('conviction')} bear={bear.get('conviction')}")
    return {**state, "researcher_reports": [bull, bear]}


async def node_trader(state: TradingState) -> TradingState:
    """Trader synthesizes all reports into a trade proposal."""
    logger.info(f"[ORC] trader: {state['symbol']}")
    proposal = await TraderAgent().decide(
        symbol=state["symbol"],
        current_price=state["current_price"],
        analyst_reports=state["analyst_reports"],
        researcher_reports=state["researcher_reports"],
        market_regime=state.get("market_regime", {})
    )
    logger.info(f"[ORC] trader decision: {proposal.get('direction')} conviction={proposal.get('conviction')}")
    return {**state, "trade_proposal": proposal}


async def node_risk_check(state: TradingState) -> TradingState:
    """Risk manager validates the trade proposal."""
    logger.info(f"[ORC] risk_check")
    conn = await get_db_conn()
    try:
        open_cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM positions WHERE status='open'"
        )
        balance_row = await conn.fetchrow(
            "SELECT COALESCE(SUM(pnl_usdt), 0) FROM positions WHERE status='closed'"
        )
    finally:
        await conn.close()

    starting = get_env_float("PAPER_STARTING_BALANCE", 10000.0)
    balance  = starting + (float(balance_row[0]) if balance_row and balance_row[0] else 0.0)

    assessment = await RiskManager().evaluate(
        trade_proposal=state["trade_proposal"],
        portfolio_balance=balance,
        open_positions_count=int(open_cnt or 0),
    )
    return {**state, "risk_assessment": assessment}


async def node_portfolio_decision(state: TradingState) -> TradingState:
    """Portfolio manager makes final call and saves to DB."""
    logger.info(f"[ORC] portfolio_decision")
    pm = PortfolioManager()
    decision = await pm.approve(state["trade_proposal"], state["risk_assessment"])
    decision_id = await pm.save_decision(
        symbol=state["symbol"],
        trade_proposal=state["trade_proposal"],
        risk_assessment=state["risk_assessment"],
        pm_decision=decision,
        analyst_reports=state["analyst_reports"],
        researcher_reports=state["researcher_reports"],
    )
    logger.info(f"[ORC] final_decision={decision.get('final_decision')} id={decision_id}")
    return {**state, "pm_decision": decision, "decision_id": decision_id}


async def node_execute(state: TradingState) -> TradingState:
    """Route to paper or live executor with portfolio risk guards."""
    # Check Kill Switch (Double Check)
    safety_path = "/opt/trade_server/data/safety.json"
    if not os.path.exists("/opt/trade_server"):
        safety_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "safety.json"))
        
    if os.path.exists(safety_path):
        try:
            with open(safety_path, "r") as f:
                if json.load(f).get("kill_switch", False):
                    logger.error("[ORC] 🛑 KILL SWITCH ACTIVE at execution step. Aborting.")
                    return state
        except: pass

    if state["pm_decision"].get("final_decision") != "EXECUTE":
        logger.info("[ORC] Decision: HOLD/REJECT — no trade")
        return state

    proposal = state["trade_proposal"]
    symbol   = state["symbol"]

    # ── Portfolio Risk Guards ─────────────────────────────
    MAX_OPEN_POSITIONS   = get_env_int("MAX_OPEN_POSITIONS", 3)
    MIN_CONFIDENCE       = get_env_int("MIN_CONFIDENCE", 7)
    DAILY_DRAWDOWN_LIMIT = get_env_float("DAILY_DRAWDOWN_LIMIT", -0.05)
    MAX_SAME_SYMBOL      = get_env_int("MAX_SAME_SYMBOL", 1)

    conn = await get_db_conn()
    try:
        # Load dynamic overrides
        config_row = await conn.fetchrow("SELECT value FROM system_config WHERE key = 'risk_limits'")
        if config_row:
            limits = json.loads(config_row["value"])
            MAX_OPEN_POSITIONS = int(limits.get("max_positions", MAX_OPEN_POSITIONS))
            MIN_CONFIDENCE = float(limits.get("min_confidence", MIN_CONFIDENCE))

        open_positions = await conn.fetch("SELECT symbol FROM positions WHERE status='open'")
        total_open     = len(open_positions)
        same_symbol    = sum(1 for p in open_positions if p["symbol"] == symbol)

        # Check daily drawdown
        daily_pnl_row  = await conn.fetchrow(
            """SELECT COALESCE(SUM(pnl_usdt), 0) AS pnl
               FROM positions WHERE status='closed'
               AND closed_at >= NOW() - INTERVAL '24 hours'"""
        )
        starting   = get_env_float("PAPER_STARTING_BALANCE", 10000.0)
        daily_pnl  = float(daily_pnl_row["pnl"] or 0)
        daily_pct  = daily_pnl / starting
    finally:
        await conn.close()

    # Confidence from analyst reports
    reports    = state.get("analyst_reports", [])
    avg_conf   = (sum(r.get("confidence", 0) for r in reports) / len(reports)) if reports else 0

    if total_open >= MAX_OPEN_POSITIONS:
        logger.warning(f"[RISK] ❌ Max positions reached ({total_open}/{MAX_OPEN_POSITIONS}) — skip")
        return state
    if same_symbol >= MAX_SAME_SYMBOL:
        logger.warning(f"[RISK] ❌ Already have {same_symbol} {symbol} position — skip")
        return state
    if avg_conf < MIN_CONFIDENCE:
        logger.warning(f"[RISK] ❌ Avg confidence {avg_conf:.1f} < {MIN_CONFIDENCE} — skip")
        return state
    if daily_pct <= DAILY_DRAWDOWN_LIMIT:
        logger.warning(f"[RISK] ❌ Daily drawdown {daily_pct:.1%} hit limit {DAILY_DRAWDOWN_LIMIT:.1%} — skip")
        return state

    logger.info(f"[RISK] ✅ Guards passed | open={total_open} | conf={avg_conf:.1f} | dd={daily_pct:.1%}")

    if TRADE_MODE == "paper":
        from execution.paper_trader import PaperTrader
        await PaperTrader().execute(state["decision_id"], state["trade_proposal"])
    else:
        from execution.live_trader import LiveTrader
        await LiveTrader().execute(state["decision_id"], state["trade_proposal"])

    return state


async def node_record_challengers(state: TradingState) -> TradingState:
    """Persist challenger signals to DB for shadow testing analysis."""
    reports = state.get("challenger_reports", [])
    if not reports:
        return state

    symbol = state["symbol"]
    conn = await get_db_conn()
    try:
        for r in reports:
            c_name = r.get("agent_name", "Unknown_Challenger")
            parent = c_name.split("_")[0]
            await conn.execute("""
                INSERT INTO challenger_results (challenger_name, parent_name, symbol, signal, confidence)
                VALUES ($1, $2, $3, $4, $5)
            """, c_name, parent, symbol, r.get("signal"), r.get("confidence", 0))
    except Exception as e:
        logger.error(f"[ORC] Failed to record challenger results: {e}")
    finally:
        await conn.close()
    return state


# ── Build Graph ───────────────────────────────────────────

def build_graph() -> StateGraph:
    g = StateGraph(TradingState)
    g.add_node("collect_data",        node_collect_data)
    g.add_node("market_observer",     node_market_observer)
    g.add_node("analyst_team",        node_analyst_team)
    g.add_node("record_challengers",  node_record_challengers)
    g.add_node("researcher_debate",   node_researcher_debate)
    g.add_node("trader",              node_trader)
    g.add_node("risk_check",          node_risk_check)
    g.add_node("portfolio_decision",  node_portfolio_decision)
    g.add_node("execute",             node_execute)

    g.set_entry_point("collect_data")
    g.add_edge("collect_data",       "market_observer")
    g.add_edge("market_observer",    "analyst_team")
    g.add_edge("analyst_team",       "record_challengers")
    g.add_edge("record_challengers", "researcher_debate")
    g.add_edge("researcher_debate",  "trader")
    g.add_edge("trader",             "risk_check")
    g.add_edge("risk_check",         "portfolio_decision")
    g.add_edge("portfolio_decision", "execute")
    g.add_edge("execute",            END)

    return g.compile()


# ── Runner ────────────────────────────────────────────────

async def run_cycle(symbol: str, dry_run: bool = False) -> TradingState:
    """Run one full agent cycle for a symbol."""
    graph = build_graph()
    initial_state: TradingState = {
        "symbol":             symbol,
        "current_price":      0.0,
        "market_regime":      {},
        "analyst_reports":    [],
        "researcher_reports": [],
        "trade_proposal":     {},
        "risk_assessment":    {},
        "pm_decision":        {},
        "decision_id":        None,
        "challenger_reports": [],
    }
    logger.info(f"[ORC] ═══ Starting cycle: {symbol} mode={TRADE_MODE} ═══")
    final_state = await graph.ainvoke(initial_state)
    logger.info(f"[ORC] ═══ Cycle complete: {symbol} ═══")
    return final_state


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
    result = asyncio.run(run_cycle(sym))
    import json
    print(json.dumps({
        "direction":   result["trade_proposal"].get("direction"),
        "conviction":  result["trade_proposal"].get("conviction"),
        "decision":    result["pm_decision"].get("final_decision"),
        "decision_id": result["decision_id"],
    }, indent=2))
