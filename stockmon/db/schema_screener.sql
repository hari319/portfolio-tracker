-- Schema for screener_cache.db — the disposable screener database.
-- See docs/DATA_STORAGE_MIGRATION.md §5.3 for design rationale.
--
-- This database is NEVER backed up.  It can be rebuilt from the upstream
-- bigbreakingwire API via sync_historical_dates().
--
-- Design: hybrid — one row per (date, symbol), 15 hot columns promoted
-- for indexed queries, remaining 112 fields kept in a `payload` JSON column.

CREATE TABLE IF NOT EXISTS screener_day (
    trade_date   TEXT PRIMARY KEY,             -- 'YYYY-MM-DD'
    fetched_at   TEXT NOT NULL,
    total_items  INTEGER NOT NULL,
    timeframe    TEXT,
    source       TEXT,
    envelope     TEXT                          -- non-item top-level keys as JSON
);

CREATE TABLE IF NOT EXISTS screener_row (
    trade_date          TEXT NOT NULL REFERENCES screener_day(trade_date) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,

    -- Promoted "hot" columns: the 13 fields multi_day_analyzer.py needs,
    -- plus the handful the UI sorts and filters on.
    close               REAL,
    open                REAL,
    high                REAL,
    low                 REAL,
    prev_close          REAL,
    pct_change          REAL,
    volume              REAL,
    delivery_qty        REAL,
    delivery_percent    REAL,
    supertrend_dir      TEXT,
    sma_20              REAL,
    close_near_high_pct REAL,
    volume_ratio_20     REAL,
    range_pct_5         REAL,
    series              TEXT,

    -- Everything else, verbatim, compact JSON (no indent).
    payload             TEXT NOT NULL,

    PRIMARY KEY (trade_date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_screener_symbol_date
    ON screener_row(symbol, trade_date DESC);
