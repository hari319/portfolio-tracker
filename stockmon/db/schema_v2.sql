-- Schema v2 for stockmon.db — Portfolio Tracker feature.
-- See docs/DATA_STORAGE_MIGRATION.md §5.4 and docs/SHEET_FORMAT.md.

-- 1. Ensure LOAN portfolio exists
INSERT OR IGNORE INTO portfolio(name, kind, created_at)
VALUES ('LOAN', 'loan', datetime('now'));

-- 2. Holdings table: one row per open stock per portfolio.
-- Multiple buys are stored in buy_lot table.
CREATE TABLE IF NOT EXISTS holding (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_name  TEXT NOT NULL REFERENCES portfolio(name) ON DELETE CASCADE,
    symbol          TEXT NOT NULL,
    scheme_name     TEXT NOT NULL,
    stock_name      TEXT,
    name_confirmed  INTEGER NOT NULL DEFAULT 0,
    person          TEXT,                                  -- 'MADI' | 'BAPA' (LOAN only)
    app             TEXT,                                  -- e.g. 'Kite', 'Kite Madi', 'Kite Bapa'
    remarks         TEXT,
    bought_reason   TEXT,                                  -- §6 notes
    sold_reason     TEXT,                                  -- §6 notes
    mistake_learned TEXT,                                  -- §6 notes
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'sold')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_holding_portfolio ON holding(portfolio_name, status);
CREATE INDEX IF NOT EXISTS idx_holding_person ON holding(person) WHERE person IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_holding_unique_open ON holding(portfolio_name, symbol) WHERE status = 'open';

-- 3. Buy lots: individual buy transactions for a holding (§2.2)
CREATE TABLE IF NOT EXISTS buy_lot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    holding_id  INTEGER NOT NULL REFERENCES holding(id) ON DELETE CASCADE,
    invest_date TEXT NOT NULL,
    quantity    REAL NOT NULL CHECK (quantity > 0),
    avg_price   REAL NOT NULL CHECK (avg_price >= 0),
    invested_amount REAL,                                  -- manual cost basis override (e.g. demerger = 0)
    buy_charge  REAL,                                      -- manual override or calculated
    remarks     TEXT,
    app         TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_buy_lot_holding ON buy_lot(holding_id);

-- 4. Sales table: records of sold positions (§4)
CREATE TABLE IF NOT EXISTS sale (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    holding_id  INTEGER NOT NULL REFERENCES holding(id) ON DELETE CASCADE,
    sell_date   TEXT NOT NULL,
    quantity    REAL NOT NULL CHECK (quantity > 0),
    sell_price  REAL NOT NULL,
    sell_charge REAL,
    remarks     TEXT,
    app         TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sale_holding ON sale(holding_id);

-- 5. Dividends table: per-portfolio dividends (§7)
CREATE TABLE IF NOT EXISTS dividend (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_name TEXT NOT NULL REFERENCES portfolio(name) ON DELETE CASCADE,
    symbol         TEXT NOT NULL,
    value          REAL NOT NULL,
    received_date  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dividend_portfolio ON dividend(portfolio_name, received_date DESC);

-- 6. Summary values table: fixed, user-entered values for Loan Summary panel (§8)
CREATE TABLE IF NOT EXISTS summary_value (
    key        TEXT PRIMARY KEY,
    value      REAL NOT NULL,
    label      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
