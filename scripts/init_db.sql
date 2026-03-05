-- ============================================================
-- Trade Server — Database Initialization
-- Auto-run by Docker on first Postgres start
-- ============================================================

-- ── OHLCV Candles ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS candles (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(20)     NOT NULL,
    timeframe   VARCHAR(5)      NOT NULL,
    ts          TIMESTAMPTZ     NOT NULL,
    open        NUMERIC(20, 8)  NOT NULL,
    high        NUMERIC(20, 8)  NOT NULL,
    low         NUMERIC(20, 8)  NOT NULL,
    close       NUMERIC(20, 8)  NOT NULL,
    volume      NUMERIC(24, 8)  NOT NULL,
    UNIQUE (symbol, timeframe, ts)
);
CREATE INDEX idx_candles_sym_ts ON candles (symbol, timeframe, ts DESC);

-- ── Raw Trades (for orderflow reconstruction) ─────────────
CREATE TABLE IF NOT EXISTS trades_raw (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(20)     NOT NULL,
    exchange_id VARCHAR(40),
    ts          TIMESTAMPTZ     NOT NULL,
    price       NUMERIC(20, 8)  NOT NULL,
    amount      NUMERIC(24, 8)  NOT NULL,
    side        VARCHAR(4)      NOT NULL,  -- buy | sell
    taker_side  VARCHAR(4)      NOT NULL   -- buy | sell (aggressor)
);
CREATE INDEX idx_trades_sym_ts ON trades_raw (symbol, ts DESC);

-- ── CVD / Volume Delta per candle ─────────────────────────
CREATE TABLE IF NOT EXISTS volume_delta (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(20)     NOT NULL,
    timeframe   VARCHAR(5)      NOT NULL,
    ts          TIMESTAMPTZ     NOT NULL,
    buy_volume  NUMERIC(24, 8)  NOT NULL,
    sell_volume NUMERIC(24, 8)  NOT NULL,
    net_delta   NUMERIC(24, 8)  NOT NULL,  -- buy - sell
    cvd         NUMERIC(24, 8),            -- cumulative delta
    volume_spike BOOLEAN DEFAULT FALSE,
    UNIQUE (symbol, timeframe, ts)
);

-- ── Volume Profile ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS volume_profile (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(20)     NOT NULL,
    session     VARCHAR(10)     NOT NULL,  -- 1h | 4h | 1d | 1w
    ts_start    TIMESTAMPTZ     NOT NULL,
    ts_end      TIMESTAMPTZ     NOT NULL,
    poc         NUMERIC(20, 8)  NOT NULL,  -- Point of Control
    vah         NUMERIC(20, 8)  NOT NULL,  -- Value Area High
    val         NUMERIC(20, 8)  NOT NULL,  -- Value Area Low
    total_volume NUMERIC(24, 8),
    profile_json JSONB,                    -- price→volume buckets
    UNIQUE (symbol, session, ts_start)
);

-- ── Orderflow / Footprint per candle ──────────────────────
CREATE TABLE IF NOT EXISTS orderflow (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(20)     NOT NULL,
    timeframe   VARCHAR(5)      NOT NULL,
    ts          TIMESTAMPTZ     NOT NULL,
    delta       NUMERIC(24, 8)  NOT NULL,  -- candle delta
    cumulative_delta NUMERIC(24, 8),
    imbalances  JSONB,                     -- price levels with strong imbalance
    footprint   JSONB,                     -- {price: {buy: vol, sell: vol}}
    UNIQUE (symbol, timeframe, ts)
);

-- ── On-chain Snapshots ────────────────────────────────────
CREATE TABLE IF NOT EXISTS onchain (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20)     NOT NULL,
    ts              TIMESTAMPTZ     NOT NULL,
    exchange_inflow NUMERIC(24, 8),
    exchange_outflow NUMERIC(24, 8),
    netflow         NUMERIC(24, 8),
    whale_tx_count  INTEGER DEFAULT 0,
    whale_tx_volume NUMERIC(24, 8) DEFAULT 0,
    stablecoin_mint NUMERIC(24, 8),
    source          VARCHAR(30),            -- cryptoquant | whalealert
    UNIQUE (symbol, ts, source)
);

-- ── Agent Decisions ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS decisions (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    symbol          VARCHAR(20)     NOT NULL,
    direction       VARCHAR(10),            -- LONG | SHORT | HOLD
    confidence      NUMERIC(5, 2),          -- 0.0–1.0
    entry_price     NUMERIC(20, 8),
    stop_loss       NUMERIC(20, 8),
    take_profit     NUMERIC(20, 8),
    position_size   NUMERIC(10, 4),         -- in % of portfolio
    reasoning       JSONB,                  -- full agent reports
    approved        BOOLEAN DEFAULT FALSE,
    executed        BOOLEAN DEFAULT FALSE
);

-- ── Paper / Live Positions ────────────────────────────────
CREATE TABLE IF NOT EXISTS positions (
    id              BIGSERIAL PRIMARY KEY,
    decision_id     BIGINT REFERENCES decisions(id),
    symbol          VARCHAR(20)     NOT NULL,
    side            VARCHAR(10)     NOT NULL,  -- long | short
    entry_price     NUMERIC(20, 8)  NOT NULL,
    size_usdt       NUMERIC(20, 8)  NOT NULL,
    stop_loss       NUMERIC(20, 8),
    take_profit     NUMERIC(20, 8),
    opened_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    close_price     NUMERIC(20, 8),
    pnl_usdt        NUMERIC(20, 8),
    status          VARCHAR(10)     DEFAULT 'open'  -- open | closed | stopped
);
