# Contributing Guide

Conventions and patterns for keeping the codebase organized as it grows.

---

## Naming Conventions

| Layer | Convention | Examples |
|-------|-----------|----------|
| **Python modules** | `snake_case` | `portfolio_tracker.py`, `data_fetcher.py` |
| **Python functions / variables** | `snake_case` | `load_portfolios()`, `normalize_symbol()` |
| **Python classes** | `PascalCase` | `ValidationError`, `DatabaseCorruptError` |
| **React components** | `PascalCase` files and exports | `PortfolioTrackerTab.jsx`, `SwingTradeModal.jsx` |
| **JS utilities / hooks** | `camelCase` files and exports | `useTickerLookup.js`, `swingCalculations.js` |
| **Database tables / columns** | `snake_case` | `buy_lot`, `portfolio_name`, `invested_amount` |
| **SQL schema files** | `schema_v{N}.sql` (DDL), inline Python (small ALTERs) | `schema_v1.sql`, `schema_v5.sql` |
| **API routes** | Kebab-case path segments | `/api/portfolio-tracker/holding`, `/api/swing-tracker/sources` |
| **Config keys** | `snake_case` | `ema_periods`, `run_times` |

---

## Project Structure

```
stockmon/                  # Python backend package
├── db/                    # Database layer
│   ├── migrations.py      # Append-only migration engine
│   ├── schema_v*.sql      # DDL for large schema changes
│   ├── backup.py          # Online backup + restore
│   └── repositories/      # ALL SQL queries live here
├── web/                   # Flask web layer
│   ├── __init__.py        # App factory (create_app)
│   └── routes/            # Route handlers split by domain
├── paths.py               # Centralized path resolution
├── service.py             # Orchestration (refresh, snapshot)
└── ...                    # Domain modules (portfolio, ema, screener, etc.)

frontend/src/              # React SPA
├── components/            # One file per component (PascalCase)
├── constants/             # Static data (columns, filters, charges)
├── hooks/                 # Custom React hooks
├── utils/                 # Pure helper functions
├── styles/                # CSS
├── api.js                 # API client (all backend calls)
└── App.jsx                # Root component with tab navigation
```

---

## Adding a New Feature / Tab

1. **Database schema** — Add a migration to `MIGRATIONS` in `stockmon/db/migrations.py`. Use a `.sql` file for new tables, inline Python for small ALTERs. **Never edit a shipped migration.**
2. **Repository** — Create `stockmon/db/repositories/{feature}.py` for all SQL queries.
3. **Domain logic** — Create `stockmon/{feature}.py` for business logic.
4. **Route handlers** — Create `stockmon/web/routes/{feature}.py` with its own Blueprint.
5. **React component** — Create `frontend/src/components/{Feature}Tab.jsx`.
6. **API client** — Add fetch functions to `frontend/src/api.js`.
7. **Documentation** — Create `docs/{FEATURE}.md`.
8. **README** — Update the project structure tree, tab documentation table, and API reference.

---

## Database Rules

- **All SQL goes in `stockmon/db/repositories/`** — business logic never writes raw SQL.
- **Migrations are append-only** — never edit or renumber a shipped migration.
- **Always use `get_connection()`** — never open raw `sqlite3.connect()` calls.
- **Two databases**: `stockmon.db` (durable, backed up) and `screener_cache.db` (disposable, rebuildable).
- **WAL mode** is enforced on every connection for concurrent read/write safety.

---

## Code Organization Rules

- **No circular imports** — use lazy imports (`from ... import ...` inside functions) when needed.
- **Route files** should only handle HTTP concerns (request parsing, response formatting). Business logic belongs in domain modules.
- **One component per file** in React — match the filename to the component name.
- **Constants** go in `frontend/src/constants/`, not inline in components.

---

## Testing

```powershell
# Run the full test suite
.\.venv\Scripts\python.exe -m pytest tests/ -v

# Run a specific test file
.\.venv\Scripts\python.exe -m pytest tests/test_portfolio_tracker.py -v
```

- Tests live in `tests/` with `test_` prefix naming.
- Use `conftest.py` fixtures for database setup/teardown.
- Test against in-memory SQLite databases, not production data.

---

## Git Conventions

- **Never commit** `data/`, `config/settings.json`, `config/portfolios.json`, `backups/`, or `logs/`.
- **Build the frontend locally** — `frontend/dist/` is gitignored; run `npm run build` after changes.
- **Keep `.db` files out of git** — all database files are gitignored.
