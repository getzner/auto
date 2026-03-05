-- add_optimization_tables.sql
-- DB migration for Self-Optimization Step 7

-- 1. Dynamic Agent Prompts
CREATE TABLE IF NOT EXISTS agent_prompts (
    id           SERIAL PRIMARY KEY,
    agent_name   VARCHAR(50) NOT NULL UNIQUE,
    prompt_text  TEXT NOT NULL,
    version      INTEGER DEFAULT 1,
    ts_updated   TIMESTAMPTZ DEFAULT NOW()
);

-- 2. System Hyperparameters (Scanner, Risk, etc.)
CREATE TABLE IF NOT EXISTS system_config (
    key          VARCHAR(50) PRIMARY KEY,
    value        JSONB NOT NULL,
    description  TEXT,
    ts_updated   TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Challenger Results (Shadow Signals)
CREATE TABLE IF NOT EXISTS challenger_results (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decision_id     BIGINT REFERENCES decisions(id),
    agent_name      VARCHAR(50) NOT NULL,
    version         INTEGER NOT NULL, -- The version of the prompt/config that generated this
    signal          VARCHAR(10),      -- BULLISH | BEARISH | NEUTRAL
    confidence      INTEGER,
    reasoning       JSONB,
    outcome_met     BOOLEAN DEFAULT NULL -- Whether this "hypothetical" trade would have won
);

-- Seed defaults for core analysts if not present
INSERT INTO system_config (key, value, description)
VALUES 
('scanner_thresholds', '{"volatility_spike": 0.02, "volume_spike": 2.5}', 'Thresholds for triggering agent cycles'),
('risk_limits', '{"max_drawdown": -0.05, "max_positions": 3}', 'Hard risk limits for the portfolio manager')
ON CONFLICT (key) DO NOTHING;
