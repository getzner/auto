-- scripts/add_non_trade_tracking.sql
CREATE TABLE IF NOT EXISTS non_trade_outcomes (
    id              SERIAL PRIMARY KEY,
    decision_id     INTEGER REFERENCES decisions(id),
    ts              TIMESTAMPTZ DEFAULT NOW(),
    symbol          TEXT NOT NULL,
    direction       TEXT,           -- BULLISH/BEARISH/NEUTRAL die werd afgewezen
    reject_reason   TEXT,           -- waarom afgewezen (risk, confidence, conflict)
    price_at_reject FLOAT,
    price_1h_later  FLOAT,          -- automatisch ingevuld door background job
    price_4h_later  FLOAT,          -- automatisch ingevuld
    price_24h_later FLOAT,          -- automatisch ingevuld
    outcome         TEXT DEFAULT 'pending', -- 'correct_reject' / 'missed_opportunity' / 'pending' / 'neutral'
    human_verdict   INTEGER,        -- +1 goed afgewezen, -1 had moeten traden
    human_note      TEXT,
    analyst_signals JSONB           -- snapshot van alle analyst outputs op dat moment
);

CREATE INDEX IF NOT EXISTS idx_non_trade_symbol ON non_trade_outcomes(symbol);
CREATE INDEX IF NOT EXISTS idx_non_trade_outcome ON non_trade_outcomes(outcome);
CREATE INDEX IF NOT EXISTS idx_non_trade_ts ON non_trade_outcomes(ts);
