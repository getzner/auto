# Smart Agents — Autonome Zelfverbeterende Agents

> **Visie:** Agents die zichzelf verbeteren zonder dat wij de pipeline bepalen.
> Ze krijgen een doel, niet een script.

---

## Het Fundamentele Verschil

```
Statisch systeem (tool-using):
  Wij bouwen pipeline → Wij bepalen tools → Agent voert uit
  Probleem: wij worden de bottleneck voor verbetering

Autonoom systeem (goal-driven):
  Agent krijgt een doel → Agent kiest eigen tools
  Agent test → evalueert → past zichzelf aan → herhaalt
  Wij: stellen doelen en bewaken grenzen
```

---

## De Architectuur: Meta-Agent + Specialist Agents

```
┌─────────────────────────────────────────────────────┐
│                    META-AGENT                        │
│  Doel: "Maximaliseer risk-adjusted returns"          │
│                                                      │
│  Taken:                                              │
│   - Beoordeelt prestaties van alle specialist agents │
│   - Beslist welke agent verbeterd moet worden        │
│   - Geeft opdracht tot zelf-verbetering              │
│   - Valideert verbeteringen voor deployment          │
└──────────────────────────┬──────────────────────────┘
                           │ stuurt aan
          ┌────────────────┼────────────────┐
          ↓                ↓                ↓
   VolumeAgent      OnchainAgent      StrategyAgent
   verbetert CVD    test Fear&Greed   ontdekt nieuwe
   strategie        thresholds        patterns
```

---

## De Cruciale Tools voor Autonomie

### 1. Python Code Executor
Agent schrijft code, voert uit, leest resultaat:
```python
tool_execute_python(code="""
import pandas as pd
df = pd.read_sql("SELECT * FROM candles WHERE symbol='BTC/USDT'", conn)
rsi = calculate_rsi(df['close'], 14)
print(rsi.tail(5).to_dict())
""")
→ {"2026-02-28": 28.4, ...}
```

### 2. Autonome Backtester
Agent kiest zelf parameters en strategie:
```python
tool_run_backtest(
    strategy="buy when RSI < 30 AND fear_greed < 20 AND funding < -0.01",
    lookback_days=90,
    symbols=["BTC/USDT", "ETH/USDT"]
)
→ {"winrate": 0.67, "sharpe": 1.8, "max_drawdown": 0.12}
```

### 3. Prompt Self-Editor
Agent herschrijft zijn eigen system prompt op basis van resultaten:
```python
tool_update_own_prompt(
    agent="OnchainAnalyst",
    new_rules=["Geef 9+ confidence bij Extreme Fear + negatieve funding",
               "Verhoog stop loss buffer bij hoge OI"],
    reason="Backtestresultaten tonen 78% winrate bij deze combinatie"
)
```

### 4. Strategy Registry
Agent registreert ontdekte strategieën:
```python
tool_register_strategy(
    name="ExtremeFear_Reversal_v2",
    conditions={"fear_greed": "<20", "funding": "<-0.01", "oi_trend": "stable"},
    backtest_stats={"winrate": 0.78, "avg_rr": 2.8, "n_trades": 23},
    deployed=True
)
```

### 5. Agent Performance Monitor
Agent leest zijn eigen historische prestaties:
```python
tool_get_performance(agent="VolumeAnalyst", last_n_trades=50)
→ {"accuracy": 0.42, "best_signal": "bearish", "worst_signal": "bullish during fear"}
```

---

## De Autonome Verbetering Loop

```
Elke zondag (of na 20 trades):

1. META-AGENT evalueert alle agents
   → "VolumeAnalyst heeft 42% accuraatheid — onderzoek nodig"

2. META-AGENT geeft opdracht aan VolumeAnalyst:
   "Analyseer je eigen fouten van de laatste 20 trades.
    Backtest 5 varianten van je CVD strategie.
    Stel een verbeterde versie voor."

3. VolumeAnalyst (autonoom):
   → haalt eigen historiek op
   → analyseert patronen in de fouten
   → schrijft 5 backtest scripts
   → voert ze uit
   → kiest de beste variant
   → schrijft nieuwe prompt versie

4. META-AGENT valideert:
   → test nieuwe prompt op out-of-sample data
   → vergelijkt met huidige versie
   → deployt als verbetering > 5%

5. Resultaat naar Discord:
   "VolumeAnalyst v2 deployed — winrate: 42% → 61%"
```

---

## Zelfontdekking van Nieuwe Patronen

Agent kan actief nieuwe patronen ontdekken:

```
StrategyAgent opdracht: "Zoek onbekende winstgevende patronen in onze data"

Agent acties (autonoom):
  1. "Ik ga correlaties analyseren tussen alle variabelen"
     → runt Python analyse op volledige DB
  2. "Interessant: als funding < -0.005 EN vol_spike = true → 73% LONG win"
     → backtest dit patroon
  3. "Bevestigd op 3 maanden data. N=31, Sharpe=2.1"
     → registreert als nieuwe strategie
  4. "Aanbeveling: voeg dit toe aan OrderflowAnalyst"
     → rapporteert aan META-AGENT
```

---

## Grenzen en Veiligheid

Autonomie heeft grenzen nodig:

| Actie | Mag autonoom? | Vereist goedkeuring |
|---|---|---|
| Prompt aanpassen | ✅ Na validatie | Nee |
| Nieuwe strategie backtesten | ✅ Altijd | Nee |
| Eigen performance analyseren | ✅ Altijd | Nee |
| Live trade parameters aanpassen | ❌ Nooit autonoom | Jij |
| Nieuw LLM model kiezen | ❌ | Jij |
| Agent verwijderen | ❌ | Jij |

**Regel:** Agents verbeteren hun *analyse*, nooit hun *risico grenzen*.

---

## Implementatie: Van Nu naar Autonoom

### Fase A — Code Execution Engine (Week 1)
```python
# data/code_executor.py
# Veilige Python sandbox: alleen DB reads + calculations, geen writes
class CodeExecutor:
    ALLOWED_IMPORTS = ["pandas", "numpy", "scipy", "ta"]
    MAX_RUNTIME_SEC = 30

    async def run(self, code: str) -> str:
        # Sandboxed execution, stdout captured
```

### Fase B — Backtest Tool (Week 1-2)
```python
# backtest/auto_backtest.py
# Agent geeft strategie als string → krijgt statistieken terug
async def run_strategy_backtest(
    strategy_code: str,
    lookback_days: int = 90
) -> BacktestResult:
```

### Fase C — Meta-Agent (Week 2-3)
```python
# agents/meta_agent.py
class MetaAgent:
    """Beoordeelt agents, geeft verbeteropdrachten, deployt updates."""
    async def weekly_review(self):
        # Evalueer alle agents
        # Identificeer zwakste performer
        # Start autonome verbetercyclus
```

### Fase D — Prompt Evolution (Week 3-4)
```python
# agents/base_agent.py uitbreiding
async def self_improve(self, performance_data: dict):
    """Agent herschrijft zijn eigen prompt na analyse."""
    new_prompt = await self.llm.ainvoke(
        f"Jouw huidige prompt:\n{self.system_prompt}\n"
        f"Jouw fouten:\n{performance_data}\n"
        f"Schrijf een verbeterde versie van je prompt:"
    )
    await self._save_prompt_version(new_prompt)
```

---

## Framework: LangGraph + ReAct

We gebruiken al LangGraph. De upgrade naar autonomie:

```python
# Nu: vaste graph
collect_data → analysts → researchers → trader → execute

# Autonoom: dynamische graph
meta_agent →
  decides: "welke agent heeft verbetering nodig?"
  creates: subgraph voor die agent
  runs: analyse + backtest + verbetering
  validates: nieuwe versie tegen historiek
  deploys: of verwerpte
```

---

## Kosten van Autonomie

| Component | Frequentie | Kosten |
|---|---|---|
| Weekly Meta-Agent review | 1x/week | ~$0.05 |
| Backtest runs (5 varianten) | Per review | ~$0.10 |
| Prompt evolution | Per verbetering | ~$0.02 |
| **Totaal per week** | | **~$0.17** |

**ROI:** Als één verbetering de winrate van één agent met 10% verhoogt
→ significant meer winstgevende trades → betaalt zichzelf terug op dag 1.

---

## Het Grote Plaatje

```
Maand 1:  Agents analyseren markt, slaan memories op
Maand 2:  Meta-agent start eerste autonome verbetercyclus
Maand 3:  Agents hebben 3-5x betere prompts dan bij start
Maand 6:  StrategyAgent heeft patronen ontdekt die wij nooit zouden bedenken
Jaar 1:   Systeem dat zichzelf continu verbetert, 24/7, zonder onze input
```

**Dit is niet science fiction — alle technologie bestaat vandaag.**
LangGraph, ChromaDB, code execution, LLM prompt generatie — we hebben het al.
Wat overblijft: de juiste architectuur om het samen te brengen.
