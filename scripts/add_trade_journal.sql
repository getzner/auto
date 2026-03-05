-- Trade Journal Storage
-- Stores AI-generated post-mortems for closed trades

CREATE TABLE IF NOT EXISTS trade_journal (
    id                   BIGSERIAL PRIMARY KEY,
    position_id          BIGINT REFERENCES positions(id) ON DELETE CASCADE,
    decision_id          BIGINT REFERENCES decisions(id) ON DELETE SET NULL,
    ts                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    summary              TEXT NOT NULL,
    performance_score    INTEGER,         -- 0-100 score
    lessons_learned      JSONB,           -- List of bullet points
    agent_critique       TEXT,            -- Constructive criticism of the analysts
    market_context       JSONB,           -- Snapshot of indicators at exit
    
    UNIQUE (position_id)
);

CREATE INDEX IF NOT EXISTS idx_trade_journal_pos ON trade_journal(position_id);
CREATE INDEX IF NOT EXISTS idx_trade_journal_ts ON trade_journal(ts DESC);

-- Add is_live column to positions
ALTER TABLE positions ADD COLUMN IF NOT EXISTS is_live BOOLEAN DEFAULT FALSE;
