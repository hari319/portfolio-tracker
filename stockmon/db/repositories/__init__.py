"""Repository package — all SQL lives here.

No module outside this package should write raw SQL.
Business logic calls e.g. ``portfolios.list_all()``, never ``conn.execute(...)``.

See docs/DATA_STORAGE_MIGRATION.md §4.3 — this isolation keeps a future
Postgres migration to rewriting one package.
"""
