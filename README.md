# 🤖 Agentic Crypto Trading Server

Multi-agent LLM-powered crypto trading framework. Paper trading first, live later.

## Signal Stack
- **Volume / CVD** — Cumulative Volume Delta, buy/sell pressure, spikes
- **Orderflow** — Footprint candles, bid/ask delta, imbalance zones
- **Volume Profile** — POC, VAH/VAL, HVN/LVN across 1h/4h/1d sessions
- **On-chain** — Exchange flows, whale transactions, stablecoin dynamics

## Agent Pipeline
```
collect_data → analyst_team (×4, parallel) → researcher_debate (Bull vs Bear)
→ trader → risk_check → portfolio_decision → execute
```
Orchestrator: **Ollama** (local) | Analysts: **Gemini Flash / GPT-4o-mini / Claude Haiku / Claude Sonnet / GPT-4o**

## Quick Start (VPS)

```bash
# 1. Provision server
bash setup_server.sh

# 2. Configure
cp .env.example .env
nano .env   # fill in exchange + LLM API keys

# 3. Start infrastructure
docker compose up -d

# 4. Install deps
source /opt/trade_env/bin/activate
pip install -r requirements.txt

# 5. Run (paper mode by default)
python main.py

# 6. API
curl http://localhost:8000/health
curl http://localhost:8000/status
curl -X POST http://localhost:8000/run -H "Content-Type: application/json" -d '{"symbol":"BTC/USDT"}'
```

## Project Structure

```
trade_server/
├── main.py                     ← Entry point (data feed + agent scheduler)
├── agents/
│   ├── orchestrator.py         ← LangGraph workflow
│   ├── analysts/               ← Volume, Orderflow, VP, On-chain agents
│   ├── researchers/            ← Bull & Bear debate
│   └── traders/                ← Trader, Risk Manager, Portfolio Manager
├── data/                       ← CCXT feed, CVD, VP, orderflow, on-chain
├── execution/                  ← Paper trader (live trader: future)
├── api/                        ← FastAPI server
├── config/config.yaml          ← All settings
├── scripts/init_db.sql         ← DB schema
├── docker-compose.yml          ← Postgres + Redis + ChromaDB
├── setup_server.sh             ← VPS provisioning script
└── .env.example                ← API keys template
```

## Mode Toggle
Set `TRADE_MODE=paper` (default) or `TRADE_MODE=live` in `.env`.
Live mode requires exchange API keys with trading permissions.
