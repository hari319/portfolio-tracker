-- Schema v5 for stockmon.db — Swing Tracker tab
-- Table name aligns directly with the "Swing Tracker" tab

CREATE TABLE IF NOT EXISTS swing_tracker (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol                      TEXT NOT NULL,
    date                        TEXT NOT NULL,
    current_price               REAL,
    current_price_updated_at    TEXT,
    buy_zone                    TEXT,
    stop_loss                   TEXT,
    target1                     TEXT,
    target2                     TEXT,
    pattern_break               TEXT,
    thesis                      TEXT,
    trade_source                TEXT,
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_swing_tracker_symbol ON swing_tracker(symbol);
CREATE INDEX IF NOT EXISTS idx_swing_tracker_date ON swing_tracker(date DESC);

CREATE TABLE IF NOT EXISTS swing_tracker_source (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

-- Seed default trade sources if empty
INSERT OR IGNORE INTO swing_tracker_source(name, created_at) VALUES ('Self Analysis', datetime('now'));

