-- Schema v1 for stockmon.db — the durable, backed-up database.
-- See docs/DATA_STORAGE_MIGRATION.md §5.2 for design rationale.
--
-- Contains: portfolios, pending additions, sync state, tracker snapshots,
--           quote cache, stock status.  Everything here is irreplaceable
--           user data or app state.

-- config/portfolios.json → portfolio + portfolio_ticker
CREATE TABLE IF NOT EXISTS portfolio (
    name        TEXT PRIMARY KEY,             -- 'BAPA' | 'MADI' | 'LOAN'
    kind        TEXT NOT NULL DEFAULT 'personal',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_ticker (
    portfolio_name TEXT NOT NULL REFERENCES portfolio(name) ON DELETE CASCADE,
    symbol         TEXT NOT NULL,             -- normalized, e.g. 'RELIANCE.NS'
    added_at       TEXT NOT NULL,
    PRIMARY KEY (portfolio_name, symbol)
);

-- data/pending_additions.json → pending_addition
CREATE TABLE IF NOT EXISTS pending_addition (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_name TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    added_at       TEXT NOT NULL,
    consumed_at    TEXT                        -- NULL = still pending
);
CREATE INDEX IF NOT EXISTS idx_pending_unconsumed
    ON pending_addition(consumed_at) WHERE consumed_at IS NULL;

-- data/status.json → sync_state (single-row table)
CREATE TABLE IF NOT EXISTS sync_state (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    version    INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT,
    source     TEXT,
    message    TEXT,
    summary    TEXT                           -- JSON blob, rendered as-is
);
-- Seed the single row if it doesn't exist
INSERT OR IGNORE INTO sync_state(id, version, message)
    VALUES (1, 0, 'No refresh has run yet.');

-- data/snapshot.json → tracker_snapshot (opaque JSON blob, keep last N)
CREATE TABLE IF NOT EXISTS tracker_snapshot (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL,
    source       TEXT,
    payload      TEXT NOT NULL                 -- full rendered snapshot JSON
);
CREATE INDEX IF NOT EXISTS idx_snapshot_generated
    ON tracker_snapshot(generated_at DESC);

-- data/quotes_cache.json → quote_cache
CREATE TABLE IF NOT EXISTS quote_cache (
    symbol     TEXT PRIMARY KEY,
    price      REAL,
    currency   TEXT,
    name       TEXT,
    fetched_at TEXT NOT NULL
);

-- data/stock_status.json → stock_status
CREATE TABLE IF NOT EXISTS stock_status (
    id                 TEXT PRIMARY KEY,        -- existing uuid4 hex strings
    symbol             TEXT NOT NULL,
    name               TEXT,
    date_of_analysis   TEXT NOT NULL,
    price_of_analysis  REAL,
    best_entry         REAL,
    status             TEXT,                    -- Buy | Avoid | Hold | Acc on dip
    base_low           REAL,
    base_high          REAL,
    bull_low           REAL,
    bull_high          REAL,
    bear_low           REAL,
    bear_high          REAL,
    remarks            TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_status_symbol ON stock_status(symbol);
