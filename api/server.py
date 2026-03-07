"""
server.py — FastAPI Internal API Server
Provides status, decision history, manual trigger, and health endpoints.
"""

import os
import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from api.auth import verify
from pydantic import BaseModel
import uvicorn
from loguru import logger
import sys

# Configure logger to respect LOG_LEVEL from .env (robustly)
log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
logger.remove()
logger.add(sys.stderr, level=log_level)
logger.info(f"[SERVER] Logger initialized with level: {log_level}")

import time
START_TIME = time.time()
PID_FILE = "/opt/trade_server/data/server.pid"
if not os.path.exists("/opt/trade_server/data"):
    PID_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "server.pid")

from data.db import get_db_conn
from agents.orchestrator import run_cycle
from api.dashboard import get_dashboard_router
from api.config_router import get_config_router
from utils.config import get_env_string, get_env_int, get_env_float

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    """Start background tasks on server startup."""
    # ── PID Lock ──────────────────────────────────────────
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0) # Check if process exists
            logger.error(f"[SERVER] 🛑 Server already running with PID {old_pid}. Exiting.")
            sys.exit(1)
        except (OSError, ValueError):
            try:
                os.remove(PID_FILE)
            except OSError as e:
                logger.warning(f"[SERVER] Could not remove old PID file: {e}")

    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError as e:
        logger.warning(f"[SERVER] Could not write new PID file: {e}")

    # ── Database Migration ────────────────────────────────
    from data.db import get_db_session
    try:
        async with get_db_session() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS skill_outcomes (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    decision_id INTEGER,
                    skill_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal TEXT,
                    confidence INTEGER,
                    reasoning TEXT,
                    price_at_analysis FLOAT,
                    price_after_1h FLOAT,
                    price_after_4h FLOAT,
                    user_rating INTEGER DEFAULT 0,
                    is_gold_standard BOOLEAN DEFAULT FALSE
                );
                CREATE INDEX IF NOT EXISTS idx_skill_outcomes_skill_id ON skill_outcomes(skill_id);
                CREATE INDEX IF NOT EXISTS idx_skill_outcomes_decision_id ON skill_outcomes(decision_id);

                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value JSONB,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS challenger_results (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT NOT NULL,
                    challenger_name TEXT NOT NULL,
                    signal TEXT,
                    confidence INTEGER,
                    reasoning TEXT
                );

                CREATE TABLE IF NOT EXISTS agent_prompts (
                    agent_name TEXT PRIMARY KEY,
                    prompt_text TEXT NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS human_feedback (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    decision_id INTEGER,
                    feedback_text TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    optimizer_note TEXT
                );
            """)
            logger.info("[SERVER] Database migrations complete.")
    except Exception as e:
        logger.error(f"[SERVER] Migration error: {e}")

    symbols = os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT").split(",")
    
    # Background monitor and scanner loops have been moved to decoupled services
    # `trade-data`, `trade-monitor`, and `trade-scanner` to prevent port 8000 ghosts.
    
    from data.db import log_pool_stats
    pool_stats_task = asyncio.create_task(log_pool_stats())
    hb_monitor_task = asyncio.create_task(check_heartbeat_loop())
    logger.info("[SERVER] Self-healing heartbeat monitor & DB Pool Stats started")
    yield
    # ── Cleanup ───────────────────────────────────────────
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    hb_monitor_task.cancel()
    pool_stats_task.cancel()
    logger.info("[SERVER] API Shutdown complete")

async def check_heartbeat_loop():
    """Self-healing: restart system if main heartbeat is lost for > 10 minutes."""
    while True:
        await asyncio.sleep(300) # Check every 5 mins
        try:
            from data.redis_client import get_redis
            r = get_redis()
            hb = r.get("main_heartbeat")
            if hb:
                last_hb = datetime.fromisoformat(hb)
                diff = (datetime.now(timezone.utc) - last_hb).total_seconds()
                if diff > 600: # 10 minutes stale
                    logger.error(f"[SERVER] 🚨 MAIN ENGINE STALE ({int(diff)}s). Triggering self-restart.")
                    import subprocess
                    subprocess.Popen(["systemctl", "restart", "trade-server", "trade-main"])
            else:
                logger.warning("[SERVER] ⚠️ Main heartbeat not found in Redis.")
        except Exception as e:
            logger.error(f"[SERVER] Heartbeat monitor error: {e}")

app = FastAPI(title="Trade Server API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SYMBOLS = [s.strip() for s in get_env_string("SYMBOLS", "BTC/USDT,ETH/USDT").split(",")]

# verify dependency now imported from api.auth

app.include_router(get_dashboard_router(), dependencies=[Depends(verify)])
app.include_router(get_config_router(), dependencies=[Depends(verify)])


# ── Health ────────────────────────────────────────────────

@app.get("/api/regime/{symbol:path}")
async def get_market_regime(symbol: str):
    import json
    from data.redis_client import get_redis
    redis = get_redis()
    if not redis:
        return {"regime": "UNKNOWN", "volatility": "UNKNOWN"}
    
    data = redis.get(f"regime:{symbol}")
    if data:
        return json.loads(data)
    return {"regime": "UNKNOWN", "volatility": "UNKNOWN"}

@app.get("/health")
async def health():
    services = {"server": "ok"}
    # Check Main Heartbeat (Redis)
    try:
        from data.redis_client import get_redis
        r = get_redis()
        hb = r.get("main_heartbeat")
        if hb:
            from datetime import datetime, timezone
            last_hb = datetime.fromisoformat(hb)
            diff = (datetime.now(timezone.utc) - last_hb).total_seconds()
            services["main"] = "ok" if diff < 60 else f"stale ({int(diff)}s)"
        else:
            services["main"] = "not_found"
    except Exception as e:
        services["main"] = f"error: {e}"

    # Check DB
    try:
        from data.db import get_db_session
        async with get_db_session(timeout=3.0) as conn:
            await conn.fetchval("SELECT 1")
        services["postgres"] = "ok"
    except Exception as e:
        services["postgres"] = f"error: {e}"
    # Check Redis
    try:
        from data.redis_client import get_redis
        get_redis().ping()
        services["redis"] = "ok"
    except Exception as e:
        services["redis"] = f"error: {e}"
    # Check Ollama
    try:
        import httpx
        r = httpx.get(f"{os.getenv('OLLAMA_BASE_URL','http://localhost:11434')}/api/tags", timeout=3)
        services["ollama"] = "ok" if r.status_code == 200 else f"status={r.status_code}"
    except Exception as e:
        services["ollama"] = f"error: {e}"
    # Check stop monitor + scanner using decoupled systemctl status
    try:
        import asyncio
        proc_mon = await asyncio.create_subprocess_exec("systemctl", "is-active", "trade-monitor", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out_mon, _ = await proc_mon.communicate()
        services["stop_monitor"] = "ok" if out_mon.decode().strip() == "active" else "error"
    except Exception:
        services["stop_monitor"] = "error"
        
    try:
        import asyncio
        proc_scan = await asyncio.create_subprocess_exec("systemctl", "is-active", "trade-scanner", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out_scan, _ = await proc_scan.communicate()
        services["scanner"] = "ok" if out_scan.decode().strip() == "active" else "error"
    except Exception:
        services["scanner"] = "error"

    all_ok = all(v == "ok" for v in services.values())
    return {"status": "healthy" if all_ok else "degraded", "services": services}


@app.get("/recent-trades")
async def recent_trades(user: str = Depends(verify)):
    """Last 20 closed positions with trade details."""
    from data.db import get_db_session
    try:
        async with get_db_session() as conn:
            rows = await conn.fetch("""
                SELECT id, symbol, side, entry_price, pnl_usdt, opened_at, closed_at
                FROM positions
                WHERE status='closed'
                ORDER BY closed_at DESC NULLS LAST
                LIMIT 20
            """)
            trades = []
            for r in rows:
                entry = float(r["entry_price"] or 0)
                pnl   = float(r["pnl_usdt"]   or 0)
                trades.append({
                    "id":        r["id"],
                    "symbol":    r["symbol"],
                    "side":      r["side"],
                    "entry":     round(entry, 2),
                    "close":     0,
                    "size_usdt": 0,
                    "pnl_usdt":  round(pnl, 2),
                    "pnl_pct":   0,
                    "fee_usdt":  0,
                    "reason":    "closed",
                    "opened_at": r["opened_at"].isoformat() if r["opened_at"] else None,
                    "closed_at": r["closed_at"].isoformat() if r["closed_at"] else None,
                })
            wins       = sum(1 for t in trades if t["pnl_usdt"] > 0)
            total      = len(trades)
            total_pnl  = sum(t["pnl_usdt"]  for t in trades)
            total_fees = sum(t["fee_usdt"]   for t in trades)
            return {
                "trades":     trades,
                "total":      total,
                "wins":       wins,
                "win_rate":   round(wins / total * 100, 1) if total else 0,
                "total_pnl":  round(total_pnl,  2),
                "total_fees": round(total_fees, 4),
            }
    except Exception as e:
        return {"trades": [], "total": 0, "wins": 0, "win_rate": 0,
                "total_pnl": 0, "total_fees": 0, "error": str(e)}

@app.get("/non-trades")
async def non_trades(limit: int = 10, user: str = Depends(verify)):
    """Fetch recent non-trades (rejected decisions) and their outcomes."""
    from data.db import get_db_session
    try:
        async with get_db_session() as conn:
            rows = await conn.fetch("""
                SELECT id, decision_id, ts, symbol, direction, reject_reason,
                       price_at_reject, price_1h_later, price_4h_later, price_24h_later,
                       outcome, human_verdict, human_note
                FROM non_trade_outcomes
                ORDER BY ts DESC
                LIMIT $1
            """, limit)
            
            nt_list = []
            for r in rows:
                p_reject = float(r["price_at_reject"] or 0)
                p_4h = float(r["price_4h_later"] or 0)
                pct_change = ((p_4h - p_reject)/p_reject*100) if p_reject > 0 and p_4h > 0 else 0
                
                nt_list.append({
                    "id": r["id"],
                    "decision_id": r["decision_id"],
                    "ts": r["ts"].isoformat() if r["ts"] else None,
                    "symbol": r["symbol"],
                    "direction": r["direction"],
                    "reject_reason": r["reject_reason"],
                    "price_at_reject": round(p_reject, 4) if p_reject else None,
                    "price_4h_later": round(p_4h, 4) if p_4h else None,
                    "pct_change": round(pct_change, 2),
                    "outcome": r["outcome"],
                    "human_verdict": r["human_verdict"]
                })
            return nt_list
    except Exception as e:
        logger.error(f"Error fetching non-trades: {e}")
        return []

# ── Live Log Viewer ───────────────────────────────────────

@app.get("/logs")
async def get_logs(n: int = 40, filter: str = "SCANNER|MONITOR|RISK|ORC|LLM|SKILL", user: str = Depends(verify)):
    """Return last N filtered log lines efficiently from systemd journal."""
    import subprocess
    keywords = [k.strip() for k in filter.split("|") if k.strip()]
    lines = []
    try:
        # Fetch the last 1000 lines from both services to ensure we have enough context after filtering
        result = subprocess.run(
            ["journalctl", "-u", "trade-api", "-u", "trade-main", "-n", "1000", "--no-pager"],
            capture_output=True, text=True, timeout=5
        )
        all_lines = result.stdout.splitlines()
        
        if keywords:
            filtered = [l for l in all_lines if any(kw in l for kw in keywords)]
        else:
            filtered = all_lines
        lines = filtered[-n:]
    except Exception as e:
        lines = [f"Error reading journalctl logs: {e}"]
        
    return {"lines": lines, "total": len(lines)}


# ── Status / Positions ────────────────────────────────────

@app.get("/status")
async def get_status(user: str = Depends(verify)):
    from data.db import get_db_session
    async with get_db_session() as conn:
            open_pos = await conn.fetch(
                "SELECT * FROM positions WHERE status='open' ORDER BY opened_at DESC"
            )
            closed_today = await conn.fetch(
                """
                SELECT symbol, side, pnl_usdt FROM positions
                WHERE status='closed' AND closed_at >= NOW() - INTERVAL '24 hours'
                """
            )
            balance_row = await conn.fetchrow(
                "SELECT COALESCE(SUM(pnl_usdt), 0) AS p FROM positions WHERE status='closed'"
            )

    import decimal, json
    from datetime import datetime, date

    def _safe(val):
        if isinstance(val, decimal.Decimal): return float(val)
        if isinstance(val, (datetime, date)): return val.isoformat()
        if val is None: return None
        return val

    starting  = get_env_float("PAPER_STARTING_BALANCE", 10000.0)
    # If using Bybit Demo Trading, the starting balance is typically 50,000 USDT
    is_bybit_demo = get_env_string("BYBIT_DEMO", "false").lower() == "true"
    if is_bybit_demo:
        starting = 50000.0

    trade_mode = get_env_string("TRADE_MODE", "paper")
    
    if trade_mode == "live":
        try:
            from execution.live_trader import LiveTrader
            trader = LiveTrader()
            equity = trader.get_balance()
            if equity == 0: # Fallback if fetch fails or balance is 0
                equity = starting + float(balance_row["p"] or 0)
        except Exception as e:
            logger.error(f"[API] Error fetching live balance: {e}")
            equity = starting + float(balance_row["p"] or 0)
    else:
        equity = starting + float(balance_row["p"] or 0)

    daily_pnl = sum(float(r["pnl_usdt"] or 0) for r in closed_today)

    uptime_sec = int(time.time() - START_TIME)
    uptime_fmt = f"{uptime_sec//3600}h {(uptime_sec%3600)//60}m {uptime_sec%60}s"

    payload = {
        "mode":          trade_mode,
        "equity_usdt":   round(float(equity), 2),
        "starting_usdt": float(starting),
        "pnl_total":     round(float(equity - starting) if trade_mode == "paper" else 0, 2), # PnL total for live is better handled via equity comparison
        "pnl_today":     round(float(daily_pnl), 2),
        "open_positions": [{k: _safe(v) for k, v in dict(p).items()} for p in open_pos],
        "pid":           os.getpid(),
        "uptime":        uptime_fmt
    }
    return JSONResponse(content=json.loads(json.dumps(payload, default=str)))


# ── Manual Triggers ───────────────────────────────────────

@app.post("/run/scan")
async def trigger_manual_scan(user: str = Depends(verify)):
    """Manually trigger the analyst pipeline for all configured symbols."""
    import os
    import asyncio
    from agents.orchestrator import run_cycle
    from loguru import logger
    
    symbols_str = os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT")
    symbols = [s.strip() for s in symbols_str.split(",")]
    
    for symbol in symbols:
        asyncio.create_task(run_cycle(symbol))
        logger.info(f"[API] Manual scan triggered for {symbol}")
        
    return {"status": "success", "message": f"Manual scan started for {symbols}"}


# ── Decision History ──────────────────────────────────────

@app.get("/decisions")
async def get_decisions(limit: int = 20, symbol: str | None = None, user: str = Depends(verify)):
    from data.db import get_db_session
    async with get_db_session() as conn:
            if symbol:
                rows = await conn.fetch(
                    "SELECT id,ts,symbol,direction,confidence,approved,executed FROM decisions "
                    "WHERE symbol=$1 ORDER BY ts DESC LIMIT $2", symbol, limit
                )
            else:
                rows = await conn.fetch(
                    "SELECT id,ts,symbol,direction,confidence,approved,executed FROM decisions "
                    "ORDER BY ts DESC LIMIT $1", limit
                )
    return [dict(r) for r in rows]


@app.get("/decisions/{decision_id}")
async def get_decision_detail(decision_id: int, user: str = Depends(verify)):
    from data.db import get_db_session
    async with get_db_session() as conn:
            row = await conn.fetchrow("SELECT * FROM decisions WHERE id=$1", decision_id)
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    return dict(row)


# ── Manual Trigger ────────────────────────────────────────

class RunRequest(BaseModel):
    symbol: str = "BTC/USDT"

@app.post("/run")
async def manual_run(req: RunRequest, user: str = Depends(verify)):
    if req.symbol.strip() not in [s.strip() for s in SYMBOLS]:
        raise HTTPException(400, f"Symbol {req.symbol} not in configured symbols: {SYMBOLS}")
    logger.info(f"[API] Manual run triggered: {req.symbol}")
    asyncio.create_task(run_cycle(req.symbol))
    return {"status": "started", "symbol": req.symbol, "ts": datetime.now(timezone.utc).isoformat()}


# ── Trade Journal ─────────────────────────────────────────

@app.get("/journal")
async def get_journal(limit: int = 50, user: str = Depends(verify)):
    """Fetch recent AI trade journals."""
    from data.db import get_db_session
    async with get_db_session() as conn:
            rows = await conn.fetch(
                """
                SELECT j.*, p.symbol, p.side, p.pnl_usdt 
                FROM trade_journal j
                JOIN positions p ON j.position_id = p.id
                ORDER BY j.ts DESC LIMIT $1
                """,
                limit
            )
    return [dict(r) for r in rows]

@app.get("/journal/{position_id}")
async def get_journal_detail(position_id: int, user: str = Depends(verify)):
    """Fetch detailed AI journal for a specific position."""
    from data.db import get_db_session
    async with get_db_session() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM trade_journal WHERE position_id=$1",
                position_id
            )
    if not row:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return dict(row)


# ── Meta-Agent ─────────────────────────────────────────────

@app.post("/meta-review")
async def trigger_meta_review(req: RunRequest, user: str = Depends(verify)):
    """Trigger an autonomous weekly review + improvement cycle."""
    logger.info(f"[API] Meta-review triggered: {req.symbol}")
    from agents.meta_agent import MetaAgent
    asyncio.create_task(MetaAgent().review_and_improve(req.symbol))
    return {"status": "started", "symbol": req.symbol, "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/accuracy")
async def get_agent_accuracy(user: str = Depends(verify)):
    """Get historical accuracy (hit rate) per analyst agent."""
    from data.db import get_db_session
    try:
        async with get_db_session() as conn:
            rows = await conn.fetch("SELECT * FROM agent_accuracy")
    except Exception:
        return {"error": "Run scripts/add_meta_reviews.sql first to create the agent_accuracy view"}
    return [dict(r) for r in rows]

from pydantic import BaseModel
class FeedbackPayload(BaseModel):
    decision_id: int | None
    feedback_text: str

@app.post("/api/feedback")
async def submit_feedback(payload: FeedbackPayload):
    from data.db import get_db_conn
    import asyncio
    from data.db import get_db_session
    async with get_db_session() as conn:
            await conn.execute(
                "INSERT INTO human_feedback (decision_id, feedback_text) VALUES ($1, $2)",
                payload.decision_id, payload.feedback_text
            )
        
            # Trigger the meta optimizer gently in the background
            try:
                from agents.meta_agent import MetaAgent
                asyncio.create_task(MetaAgent().process_human_feedback())
            except Exception as e:
                logger.error(f"Failed to trigger meta optimizer: {e}")
            
            return {"status": "success"}


if __name__ == "__main__":
    uvicorn.run(
        "api.server:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=False,
        log_level="info",
    )
