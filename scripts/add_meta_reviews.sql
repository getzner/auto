-- add_meta_reviews.sql
-- DB migration for Meta-Agent weekly review storage

CREATE TABLE IF NOT EXISTS meta_reviews (
    id                   SERIAL PRIMARY KEY,
    ts                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    plan                 JSONB,
    performance_snapshot JSONB
);

CREATE INDEX IF NOT EXISTS idx_meta_reviews_ts ON meta_reviews(ts DESC);

-- Agent performance view — hit rate per analyst across all decisions
CREATE OR REPLACE VIEW agent_accuracy AS
WITH analyst_signals AS (
    SELECT
        d.id AS decision_id,
        d.direction AS final_direction,
        d.approved,
        p.pnl_usdt,
        jsonb_array_elements(
            (d.reasoning::jsonb)->'analyst_reports'
        ) AS report
    FROM decisions d
    LEFT JOIN positions p ON p.decision_id = d.id
    WHERE d.reasoning IS NOT NULL
      AND d.reasoning != '{}'
)
SELECT
    report->>'analyst' AS agent_name,
    COUNT(*)           AS total_signals,
    SUM(CASE
        WHEN report->>'signal' = 'BULLISH' AND final_direction = 'LONG'  AND pnl_usdt > 0 THEN 1
        WHEN report->>'signal' = 'BEARISH' AND final_direction = 'SHORT' AND pnl_usdt > 0 THEN 1
        ELSE 0
    END)               AS correct_signals,
    ROUND(
        SUM(CASE
            WHEN report->>'signal' = 'BULLISH' AND final_direction = 'LONG'  AND pnl_usdt > 0 THEN 1
            WHEN report->>'signal' = 'BEARISH' AND final_direction = 'SHORT' AND pnl_usdt > 0 THEN 1
            ELSE 0
        END)::numeric / NULLIF(COUNT(*), 0), 3
    )                  AS accuracy
FROM analyst_signals
WHERE report->>'analyst' IS NOT NULL
GROUP BY report->>'analyst'
ORDER BY accuracy DESC NULLS LAST;
