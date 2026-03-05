# Trade Server — Project Overzicht 3.0 (The Beast Mode Edition)

> Agentic crypto trading framework | VPS: 76.13.187.23 | Fase: Paper Trading / Preparation Live

Dit document is de "Source of Truth" voor de huidige status en de roadmap van het project. We hebben de afgelopen dagen het systeem getransformeerd van een lokaal script naar een robuuste, "self-healing" server-applicatie.

---

## 🏆 Wat hebben we al klaargespeeld? (The Journey So Far)

### 1. Industriële Stabiliteit & Infrastructuur (✅ Voltooid)
- **Volledige `systemd` Integratie**: Zowel de API (`trade-server`) als de achtergrond-engine (`trade-main`) draaien nu als onverwoestbare achtergrond-services.
- **Self-Healing Mechanics**: Bij database uitval (Postgres/Redis) crasht de scanner niet meer, maar wacht hij netjes af. De API en Main Engine houden elkaar in de gaten (heartbeats) en herstarten het systeem automatisch bij een freeze.
- **Veilige Reboots**: Geen "zombie processen" meer. PID-locking en permission-handling zijn geoptimaliseerd voor feilloze reboots.

### 2. Het Control Center Dashboard (✅ Voltooid)
- **Live Monitoring**: Een hypermodern dashboard met directe visuele feedback (groene/oranje bolletjes) over álle sub-systemen (Postgres, Redis, Main, Scanner, Ollama).
- **Service Control**: Eén-klik knoppen om vanaf je telefoon de hele server (API & Engine) feilloos te herstarten via beveiligde API endpoints.
- **Live Configuratie**: Risicomanagement (Min Confidence, Max Risk, Max Positions) en scanner-gevoeligheid live aanpassen zónder de server te moeten herstarten.
- **Model Switcher**: Direct wisselen van LLM per agent (DeepSeek, Claude, Llama) rechtstreeks in de UI.
- **Trade Journaling & Live Logs**: Achtergrondprocessen, LLM logica en trade-redeneringen live te volgen in een ingebouwde terminal-viewer.

### 3. De LangGraph Orchestrator (✅ Voltooid)
- **Multi-Agent Debates**: Een gecoördineerde flow waarin Volume, Orderflow, Onchain en News analisten informatie samenvoegen tot één harde trade-beslissing.
- **Challenger Systeem**: "Shadow trading" waarin agents die een alternatief model of prompt gebruiken hun beslissingen registreren voor latere prestatievergelijking.

---

## 🚀 De Roadmap (Wat gaan we nog doen?)

Hier is het gezamenlijke actieplan voor de komende iteraties.

### 🧠 Huidige Focus & Laatst Voltooide Stappen (The Custom Build)

- [x] **1. Dynamische Agent Selectie (Aan/Uit Schakelaars)**
  - Het dashboard is succesvol uitgebreid met toggles voor **Core Analisten** in het configuratiemenu.
  - De LLM Orchestrator pikt deze status live op; als je een agent deactiveert, verbruikt deze geen tokens meer en praat niet mee in het debat.

- [x] **2. Human-in-the-Loop Skill Training (Supervised Agent Evolution)**
  - Er is een "Feedback/Mentor Studio" gebouwd rechtstreeks in de **Trade Journal** tab.
  - Na elke trade beslissing (Decision) kun jij specifieke tekstuele feedback geven (bv "Volume_Analyst: je negeerde de low timeframe fake-out").
  - De **Meta Optimizer** springt autonoom aan in de background, zoekt de beslissing op, destilleert jouw les in een programmeerbare "1-sentence rule", en slaat deze permanent op in de database tabel (`agent_prompts`) voor de verantwoordelijke agent!
  
### ⚡ Door Antigravity Voorgestelde Volgende Stappen

- [ ] **3. Testnet Order Executie (De Vuursdoop)**
  - De `live_trader.py` koppelen aan de officiële **Bybit Testnet API**.
  - Wegstappen van de "Paper Trading" database-simulatie en échte (neppe) orders insturen, monitoren hoe snel Bybit ze vult, en hoe de `stop_monitor.py` omgaat met latency, slippage en gedeeltelijke fills.

- [ ] **4. Autonome Markt-Regime Detectie**
  - Een kleine vederlichte "Market Observer" agent toevoegen die continu checkt: *Zitten we in een trend, of gaan we zijwaarts (ranging)?*
  - Deze detectie gebruiken om automatisch de weging van agents aan te passen (bv. in een ranging market krijgt de RSI expert meer stemrecht, in een trending market krijgt de Volume expert meer stemrecht).

---

## 🛠️ Operational Guide (Quick Commands)

### 🏥 Dashboard & Monitoring
- **Dashboard**: [http://76.13.187.23:8000/dashboard](http://76.13.187.23:8000/dashboard)
  - *Gebruik de "System Control Center" knoppen voor veilige reboots!*
- **Health Check API**: [http://76.13.187.23:8000/health](http://76.13.187.23:8000/health)

### 🔄 Synchronisatie (Mac naar VPS)
```bash
rsync -avz --exclude 'venv' --exclude 'data/*.pid' --exclude '__pycache__' /Users/wernervrijens/Documents/klanten/trade_server/ root@76.13.187.23:/opt/trade_server/
```

### ⚡ Nood-Terminal Management (Als dashboard down is)
```bash
# Alles herstarten (API + Orchestrator)
/opt/trade_server/bin/restart_all.sh

# Alleen de API service
systemctl restart trade-server

# Alleen de Main Engine
systemctl restart trade-main

# Bekijk de logs van de Engine
journalctl -u trade-main -f
```
