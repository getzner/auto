-- ============================================================
-- Cost Tracking Table Migration
-- Run on VPS: psql -U trader -d trade_db -f scripts/add_cost_tracking.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS llm_costs (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    agent_name    VARCHAR(50)     NOT NULL,
    model         VARCHAR(60)     NOT NULL,
    symbol        VARCHAR(20),
    input_tokens  INTEGER         NOT NULL DEFAULT 0,
    output_tokens INTEGER         NOT NULL DEFAULT 0,
    cost_usd      NUMERIC(12, 8)  NOT NULL DEFAULT 0,
    decision_id   BIGINT REFERENCES decisions(id) ON DELETE SET NULL
);

CREATE INDEX idx_llm_costs_ts         ON llm_costs (ts DESC);
CREATE INDEX idx_llm_costs_agent      ON llm_costs (agent_name);
CREATE INDEX idx_llm_costs_decision   ON llm_costs (decision_id);
