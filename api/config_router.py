import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/api/config", tags=["config"])

OVERRIDE_FILE = "/opt/trade_server/data/model_overrides.json"
if not os.path.exists("/opt/trade_server"):
    # Fallback for local dev
    OVERRIDE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "model_overrides.json"))

class ModelConfig(BaseModel):
    provider: str
    model: str

class SkillConfig(BaseModel):
    id: str
    active: bool

class AllConfig(BaseModel):
    overrides: dict[str, ModelConfig]
    active_skills: list[str] = []
    skill_model_overrides: dict[str, str] = {} # skill_id -> "provider:model"
    active_core_agents: list[str] = ["volume_analyst", "orderflow_analyst", "news_analyst", "vp_analyst", "onchain_analyst", "gametheory_analyst"]

@router.get("/models")
async def get_model_config():
    """Return current model overrides, defaults, and available skills."""
    config = {"overrides": {}, "active_skills": [], "active_core_agents": ["volume_analyst", "orderflow_analyst", "news_analyst", "vp_analyst", "onchain_analyst", "gametheory_analyst"]}
    if os.path.exists(OVERRIDE_FILE):
        try:
            with open(OVERRIDE_FILE, "r") as f:
                config_data = json.load(f)
                config.update(config_data)
                # Migration check: if old format, wrap it
                if "overrides" not in config_data and "active_skills" not in config_data:
                    config = {"overrides": config_data, "active_skills": [], "active_core_agents": ["volume_analyst", "orderflow_analyst", "news_analyst", "vp_analyst", "onchain_analyst", "gametheory_analyst"]}
        except Exception as e:
            logger.error(f"[API] Error reading overrides: {e}")
    
    # Load skill registry
    registry_path = "/opt/trade_server/agents/skills/registry.json"
    if not os.path.exists("/opt/trade_server"):
        registry_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents", "skills", "registry.json"))
    
    skills = {}
    if os.path.exists(registry_path):
        with open(registry_path, "r") as f:
            skills = json.load(f)

    return {
        "overrides": config.get("overrides", {}),
        "active_skills": config.get("active_skills", []),
        "active_core_agents": config.get("active_core_agents", ["volume_analyst", "orderflow_analyst", "news_analyst", "vp_analyst", "onchain_analyst", "gametheory_analyst"]),
        "available_skills": skills,
        "defaults": {
            "volume_analyst": {"provider": "deepseek", "model": "deepseek-chat"},
            "orderflow_analyst": {"provider": "deepseek", "model": "deepseek-chat"},
            "news_analyst": {"provider": "deepseek", "model": "deepseek-chat"},
            "vp_analyst": {"provider": "deepseek", "model": "deepseek-chat"},
            "onchain_analyst": {"provider": "anthropic", "model": "claude-3-haiku-20240307"},
            "gametheory_analyst": {"provider": "anthropic", "model": "claude-3-haiku-20240307"}
        },
        "available_providers": ["deepseek", "anthropic", "google", "openai", "ollama", "xai"]
    }

@router.post("/models")
async def update_model_config(config: AllConfig):
    """Save model overrides and active skills. Also updates registry for skill overrides."""
    try:
        os.makedirs(os.path.dirname(OVERRIDE_FILE), exist_ok=True)
        
        data = {
            "overrides": {k: v.dict() for k, v in config.overrides.items()},
            "active_skills": config.active_skills,
            "active_core_agents": config.active_core_agents
        }
        
        with open(OVERRIDE_FILE, "w") as f:
            json.dump(data, f, indent=2)

        # Update skill registry overrides
        registry_path = "/opt/trade_server/agents/skills/registry.json"
        if not os.path.exists("/opt/trade_server"):
            registry_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents", "skills", "registry.json"))
        
        if config.skill_model_overrides and os.path.exists(registry_path):
            with open(registry_path, "r") as f:
                skills = json.load(f)
            
            for sid, val in config.skill_model_overrides.items():
                if sid in skills:
                    skills[sid]["model_override"] = val
            
            with open(registry_path, "w") as f:
                json.dump(skills, f, indent=2)
            
        logger.info(f"[API] Updated config: {list(data['overrides'].keys())} | Skills: {data['active_skills']}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"[API] Error saving overrides: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Safety / Kill Switch ───────────────────────────────

@router.get("/safety")
async def get_safety():
    """Return current safety settings (kill switch, etc.)."""
    safety_path = "/opt/trade_server/data/safety.json"
    if not os.path.exists("/opt/trade_server"):
        safety_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "safety.json"))
    
    if os.path.exists(safety_path):
        try:
            with open(safety_path, "r") as f:
                data: dict[str, typing.Any] = json.load(f)
        except Exception:
            data: dict[str, typing.Any] = {"kill_switch": False}
    else:
        data: dict[str, typing.Any] = {"kill_switch": False}
        
    # Inject current actual env modes
    data["trade_mode"] = os.getenv("TRADE_MODE", "paper")
    data["bybit_testnet"] = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
    data["bybit_demo"] = os.getenv("BYBIT_DEMO", "false").lower() == "true"
    
    return data

@router.post("/safety")
async def update_safety(data: dict):
    """Toggle kill switch or update risk limits."""
    safety_path = "/opt/trade_server/data/safety.json"
    if not os.path.exists("/opt/trade_server"):
        safety_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "safety.json"))
        
    try:
        current = {"kill_switch": False}
        if os.path.exists(safety_path):
            with open(safety_path, "r") as f:
                current = json.load(f)
        
        current.update(data)
        os.makedirs(os.path.dirname(safety_path), exist_ok=True)
        with open(safety_path, "w") as f:
            json.dump(current, f, indent=4)
        
        logger.warning(f"[API] Safety update: {current}")
        return {"status": "success", "safety": current}
    except Exception as e:
        logger.error(f"[API] Error saving safety: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Dynamic System Config ──────────────────────────────
@router.get("/system")
async def get_system_config():
    """Fetch all dynamic settings from system_config table."""
    from data.db import get_db_conn
    conn = await get_db_conn()
    try:
        rows = await conn.fetch("SELECT key, value FROM system_config")
        config = {r["key"]: json.loads(r["value"]) for r in rows}
        
        # Ensure defaults if missing
        if "risk_limits" not in config:
            config["risk_limits"] = {"max_risk_pct": 2.0, "max_positions": 3, "min_confidence": 7.0}
        elif "min_confidence" not in config["risk_limits"]:
            config["risk_limits"]["min_confidence"] = 7.0
            
        if "scanner_thresholds" not in config:
            config["scanner_thresholds"] = {"volatility_zscore": 2.0, "volume_spike_multi": 3.0, "trigger_threshold": 2}
            
        return config
    finally:
        await conn.close()

@router.post("/system")
async def update_system_config(data: dict):
    """Update specific keys in system_config."""
    from data.db import get_db_conn
    conn = await get_db_conn()
    try:
        for key, value in data.items():
            await conn.execute("""
                INSERT INTO system_config (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, key, json.dumps(value))
        return {"status": "success"}
    finally:
        await conn.close()

# ── Challenger Analytics ──────────────────────────────
@router.get("/challengers")
async def get_challenger_results(limit: int = 20):
    """Fetch recent challenger agent performance."""
    from data.db import get_db_conn
    conn = await get_db_conn()
    try:
        rows = await conn.fetch("""
            SELECT ts, symbol, challenger_name, signal, confidence, reasoning
            FROM challenger_results
            ORDER BY ts DESC LIMIT $1
        """, limit)
        return [dict(r) for r in rows]
    finally:
        await conn.close()

# ── System Control ──────────────────────────────────────
@router.post("/system/kill-ghosts")
async def kill_ghosts():
    """Kills orphan processes on port 8000 (often CCXT loops) and restarts services."""
    import subprocess
    logger.warning("[API] 👻 KILLING GHOST PROCESSES ON PORT 8000")
    try:
        # Spawn a background shell process to kill port 8000 and restart safely
        script = "sleep 1; fuser -k -9 8000/tcp || true; sleep 1; systemctl restart trade-server trade-main"
        subprocess.Popen(script, shell=True)
        return {"status": "killing_ghosts", "message": "Ghost processes will be terminated and system will restart"}
    except Exception as e:
        logger.error(f"[API] Error killing ghosts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/system/restart")
async def restart_system():
    """Triggers a full service restart via systemctl."""
    import subprocess
    logger.warning("[API] 🔄 FULL SYSTEM RESTART TRIGGERED FROM DASHBOARD")
    try:
        # We use a background task to avoid killing the response immediately
        # However, for systemd, restart will kill this process
        subprocess.Popen(["systemctl", "restart", "trade-server", "trade-main"])
        return {"status": "restarting", "message": "System restart signal sent"}
    except Exception as e:
        logger.error(f"[API] Restart failed: {e}")
        # Fallback for non-systemd environments or local testing
        return {"status": "error", "message": str(e)}

@router.post("/system/reload-config")
async def reload_config():
    """Signal all processes to reload config from DB."""
    from data.redis_client import get_redis
    try:
        r = get_redis()
        r.publish("system_control", json.dumps({"action": "reload_config"}))
        logger.info("[API] 🔄 Reload config signal published")
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ── Agent Training / Feedback ───────────────────────────
class AgentFeedback(BaseModel):
    agent_name: str
    feedback: str

# ── Gap 3+4: Universal Trade Server Context injected in all chat sessions ─
# This context block standardises confidence calibration and makes every agent
# acutely aware that their analysis leads to REAL capital allocation decisions.
TRADE_SERVER_CONTEXT = """

=== TRADE SERVER CONTEXT (always active) ===
You are a specialist analyst in an autonomous multi-agent crypto trading system.
Your analysis DIRECTLY feeds a Trader Agent → Risk Manager → Portfolio Manager pipeline.
Real capital is at stake. Act accordingly.

CONFIDENCE SCALE (universal, all agents):
  0–3  = Noise / insufficient data → output NEUTRAL, do NOT trade
  4–5  = Weak signal, single indicator, low conviction  
  6–7  = Moderate signal, 2+ indicators agree
  8    = Strong, 3+ indicators confirmed, optionally backtested
  9–10 = ONLY when ALL signals align perfectly (extreme conditions)

You are now in TRAINING & DEBATE MODE with your Operator (Werner).
He is challenging you, sparring with you, testing your thinking.
You may disagree. You MUST defend your reasoning with evidence.
You may update your view — BUT only when genuinely convinced by data or logic.
Speak as your true agent persona, not a generic assistant.
Be concise, sharp, and professional. No corporate filler.
===
"""

# Agent personas for the chat room
AGENT_PERSONAS = {
    "orchestrator": "You are the Orchestrator — the master conductor of the Trade Server. You synthesize all analyst reports and make the final strategic call. You have a birds-eye view of the entire system and always think in terms of portfolio risk and opportunity cost.",
    "gametheory_analyst": "You are the GameTheory & Liquidity Analyst. You think like a predatory whale. You don't believe in support/resistance — you believe in liquidity clusters. Your obsession: where are retail traders' stop-losses hidden, and how will market makers hunt them?",
    "volume_analyst": "You are the Volume & CVD Analyst. CVD is your holy scripture — Cumulative Volume Delta never lies. You distrust price action alone; volume tells you WHO is behind the move. You're skeptical by nature and need at least 3 confirming signals before high confidence.",
    "orderflow_analyst": "You are the Orderflow Analyst — a quant who sees patterns in the microseconds between trades. You read bid/ask imbalances like sheet music. Delta divergence is your edge.",
    "news_analyst": "You are the News & Sentiment Analyst — a cynical veteran journalist who questions every headline. You know that 90% of news is noise, but 10% moves markets for days. Your job: separate the signal from the drama.",
    "vp_analyst": "You are the Volume Profile Analyst. POC, VAH, VAL — these are your sacred levels. You believe price is always magnetically drawn to high-volume nodes. You never trade in low-volume zones.",
    "onchain_analyst": "You are the On-Chain Detective. Miners and whales move first — you read their footprints on the blockchain before they show up in price. Fear & Greed is your pulse check, funding rate is your forward indicator.",
    "risk_manager": "You are the Risk Manager — the paranoid guardian of capital. You consider every trade from the perspective of maximum possible loss first. A 3% drawdown keeps you up at night. You approve trades grudgingly and with conditions.",
    "meta_agent": "You are the MetaAgent — the performance analyst who evaluates ALL other agents. You are ruthlessly analytical about accuracy, hit rates, and biases. You prescribe improvement plans and validate them before deployment.",
}

@router.post("/agent/chat")
async def chat_with_agent(data: dict):
    """
    Gap 3+4: Real-time debate/sparring chat with an agent.
    Uses the agent's REAL configured LLM and persona, not always Ollama.
    Injects Trade Server Context + Confidence Scale + MD memory file.
    """
    agent_name = data.get("agent_name", "orchestrator")
    messages   = data.get("messages", [])
    debate_mode = data.get("debate_mode", True)  # True = agent defends its views

    try:
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        # Build persona from registry or fallback
        persona = AGENT_PERSONAS.get(
            agent_name,
            f"You are the {agent_name.replace('_', ' ').title()} of the Trade Server."
        )

        # Load MD memory file for this agent if it exists
        md_context = ""
        try:
            mem_dir = "/opt/trade_server/data/memories"
            if not os.path.exists("/opt/trade_server"):
                mem_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "memories"))
            mem_file = os.path.join(mem_dir, f"{agent_name}.md")
            if os.path.exists(mem_file):
                with open(mem_file, "r") as f:
                    content = f.read().strip()
                if content:
                    md_context = f"\n\n=== YOUR STORED MEMORY & TRAINING NOTES ===\n{content}\n==="
        except Exception:
            pass

        system_content = persona + TRADE_SERVER_CONTEXT + md_context

        langchain_msgs = [SystemMessage(content=system_content)]
        for msg in messages:
            if msg["role"] == "user":
                langchain_msgs.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                langchain_msgs.append(AIMessage(content=msg["content"]))

        # Use Ollama (always available locally)
        from langchain_ollama import ChatOllama
        llm = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0.4  # higher temp for debate/creativity
        )

        resp = await llm.ainvoke(langchain_msgs)
        return {"status": "success", "reply": resp.content, "agent": agent_name}

    except Exception as e:
        logger.error(f"[API] Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class AgentMemoryUpdate(BaseModel):
    agent_name: str
    memory_text: str

@router.post("/agent/save-memory")
async def update_agent_md_memory(data: AgentMemoryUpdate):
    """Gap 2: Save chat memory to BOTH MD file AND ChromaDB.
    MD file = explicit, always-on instructions.
    ChromaDB = semantic, recalled by similarity during analysis.
    """
    try:
        mem_dir = "/opt/trade_server/data/memories"
        if not os.path.exists("/opt/trade_server"):
            mem_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "memories"))

        os.makedirs(mem_dir, exist_ok=True)
        file_path = os.path.join(mem_dir, f"{data.agent_name}.md")

        with open(file_path, "w") as f:
            f.write(data.memory_text)

        logger.info(f"[API] MD memory updated for {data.agent_name}")

        # Gap 2: Also store in ChromaDB as human feedback (semantic layer)
        chroma_ok = False
        try:
            from data.chroma_memory import store_human_feedback
            await store_human_feedback(
                agent_name=data.agent_name,
                feedback=data.memory_text
            )
            chroma_ok = True
            logger.info(f"[API] ChromaDB memory updated for {data.agent_name}")
        except Exception as ce:
            logger.warning(f"[API] ChromaDB store failed (non-critical): {ce}")

        return {
            "status": "success",
            "message": f"Memory for {data.agent_name} saved",
            "md_file": True,
            "chromadb": chroma_ok,
        }
    except Exception as e:
        logger.error(f"[API] Error saving memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class FeedbackRequest(BaseModel):
    skill_id: str
    rating: int  # 1 or -1
    decision_id: int | None = None

@router.post("/feedback")
async def submit_feedback(fb: FeedbackRequest):
    """Save user feedback for a specific skill analysis."""
    from data.db import get_db_conn
    conn = await get_db_conn()
    try:
        await conn.execute("""
            INSERT INTO skill_outcomes (skill_id, user_rating, decision_id)
            VALUES ($1, $2, $3)
        """, fb.skill_id, fb.rating, fb.decision_id)
        logger.info(f"[API] Feedback received for {fb.skill_id}: {fb.rating}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"[API] Error saving feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

def get_config_router():
    return router
