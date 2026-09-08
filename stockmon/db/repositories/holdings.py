"""Repository for ``holding``, ``buy_lot``, and ``sale`` tables.

All SQL for portfolio holdings, individual buy lots, and completed sales
is encapsulated here.
See docs/DATA_STORAGE_MIGRATION.md §5.4 and docs/SHEET_FORMAT.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .. import get_connection

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Holdings & Lots
# ---------------------------------------------------------------------------

def split_existing_multi_lot_sold_holdings() -> None:
    """Ensure any existing sold holding with multiple buy lots is split into individual sold holdings."""
    conn = get_connection()
    multi_sold = conn.execute(
        """
        SELECT h.id, COUNT(b.id) AS lot_count
        FROM holding h
        JOIN buy_lot b ON b.holding_id = h.id
        WHERE h.status = 'sold'
        GROUP BY h.id
        HAVING COUNT(b.id) > 1
        """
    ).fetchall()

    if not multi_sold:
        return

    now = _utc_now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for row in multi_sold:
            hid = row["id"]
            holding = conn.execute("SELECT * FROM holding WHERE id = ?", (hid,)).fetchone()
            sales = conn.execute("SELECT * FROM sale WHERE holding_id = ?", (hid,)).fetchall()
            lots = conn.execute("SELECT * FROM buy_lot WHERE holding_id = ? ORDER BY invest_date ASC, id ASC", (hid,)).fetchall()
            if not holding or not lots or not sales:
                continue

            sale_record = sales[0]
            sell_date = sale_record["sell_date"]
            sell_price = float(sale_record["sell_price"])
            tot_sc = float(sale_record["sell_charge"]) if sale_record["sell_charge"] is not None else None
            tot_q = sum(float(l["quantity"]) for l in lots)

            for lot in lots:
                l_qty = float(lot["quantity"])
                l_price = float(lot["avg_price"])
                l_bc = float(lot["buy_charge"]) if lot["buy_charge"] is not None else None
                l_inv = float(lot["invested_amount"]) if lot["invested_amount"] is not None else round(l_qty * l_price, 4)
                l_sc = round(tot_sc * (l_qty / tot_q), 4) if (tot_sc is not None and tot_q > 0) else None

                holding_stock_name = holding["stock_name"] if ("stock_name" in holding.keys() and holding["stock_name"]) else holding["scheme_name"]
                cur = conn.execute(
                    """
                    INSERT INTO holding (
                        portfolio_name, symbol, scheme_name, stock_name, name_confirmed,
                        person, app, remarks, bought_reason, sold_reason,
                        mistake_learned, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'sold', ?, ?)
                    """,
                    (
                        holding["portfolio_name"],
                        holding["symbol"],
                        holding["scheme_name"],
                        holding_stock_name,
                        holding["name_confirmed"],
                        holding["person"],
                        holding["app"],
                        holding["remarks"],
                        holding["bought_reason"],
                        holding["sold_reason"],
                        holding["mistake_learned"],
                        now,
                        now,
                    ),
                )
                new_hid = cur.lastrowid

                conn.execute(
                    """
                    INSERT INTO buy_lot (
                        holding_id, invest_date, quantity, avg_price,
                        invested_amount, buy_charge, remarks, app, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_hid,
                        lot["invest_date"],
                        l_qty,
                        l_price,
                        l_inv,
                        l_bc,
                        lot["remarks"],
                        lot["app"],
                        now,
                    ),
                )

                conn.execute(
                    """
                    INSERT INTO sale (
                        holding_id, sell_date, quantity, sell_price,
                        sell_charge, remarks, app, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_hid,
                        sell_date,
                        l_qty,
                        sell_price,
                        l_sc,
                        sale_record["remarks"],
                        sale_record["app"],
                        now,
                    ),
                )

            conn.execute("DELETE FROM buy_lot WHERE holding_id = ?", (hid,))
            conn.execute("DELETE FROM sale WHERE holding_id = ?", (hid,))
            conn.execute("DELETE FROM holding WHERE id = ?", (hid,))

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def list_holdings(portfolio_name: str, status: str = "open") -> list[dict[str, Any]]:
    """Return all holdings for a portfolio with their aggregated lot information.

    For status='open':
      Joins with buy_lot to aggregate total quantity, total invested, weighted
      average price, earliest invest date, and lot count.
    For status='sold':
      Joins with sale and buy_lot to return realized exit details.
    """
    conn = get_connection()

    if status == "open":
        query = """
            SELECT
                h.id,
                h.portfolio_name,
                h.symbol,
                h.scheme_name,
                COALESCE(h.stock_name, h.scheme_name, '') AS stock_name,
                h.name_confirmed,
                h.person,
                h.app,
                h.remarks,
                h.bought_reason,
                h.sold_reason,
                h.mistake_learned,
                h.status,
                h.created_at,
                h.updated_at,
                COALESCE(SUM(b.quantity), 0.0) AS total_qty,
                COALESCE(SUM(COALESCE(b.invested_amount, b.quantity * b.avg_price)), 0.0) AS total_invested,
                CASE
                    WHEN COALESCE(SUM(b.quantity), 0) > 0
                    THEN SUM(b.quantity * b.avg_price) / SUM(b.quantity)
                    ELSE 0.0
                END AS weighted_avg_price,
                COALESCE(MIN(b.invest_date), '') AS first_invest_date,
                COALESCE(MAX(b.invest_date), '') AS last_invest_date,
                SUM(b.buy_charge) AS total_buy_charge,
                COUNT(b.id) AS lot_count
            FROM holding h
            LEFT JOIN buy_lot b ON b.holding_id = h.id
            WHERE h.portfolio_name = ? AND h.status = 'open'
            GROUP BY h.id
            ORDER BY first_invest_date ASC, h.symbol ASC, h.id ASC
        """
        rows = conn.execute(query, (portfolio_name,)).fetchall()
        return [dict(r) for r in rows]

    # status == 'sold'
    split_existing_multi_lot_sold_holdings()
    query = """

        SELECT
            h.id,
            h.portfolio_name,
            h.symbol,
            h.scheme_name,
            COALESCE(h.stock_name, h.scheme_name, '') AS stock_name,
            h.name_confirmed,
            h.person,
            h.app,
            h.remarks,
            h.bought_reason,
            h.sold_reason,
            h.mistake_learned,
            h.status,
            h.created_at,
            h.updated_at,
            s.id AS sale_id,
            s.sell_date,
            s.quantity AS sold_quantity,
            s.sell_price,
            s.sell_charge,
            s.remarks AS sale_remarks,
            COALESCE(bl.first_invest_date, '') AS invest_date,
            COALESCE(bl.weighted_avg, 0.0) AS avg_price,
            bl.total_buy_charge AS buy_charge,
            COALESCE(bl.total_invested, 0.0) AS invested_amount
        FROM holding h
        JOIN sale s ON s.holding_id = h.id
        LEFT JOIN (
            SELECT
                holding_id,
                MIN(invest_date) AS first_invest_date,
                CASE WHEN SUM(quantity) > 0
                     THEN SUM(quantity * avg_price) / SUM(quantity)
                     ELSE 0.0
                END AS weighted_avg,
                SUM(buy_charge) AS total_buy_charge,
                SUM(COALESCE(invested_amount, quantity * avg_price)) AS total_invested
            FROM buy_lot
            GROUP BY holding_id
        ) bl ON bl.holding_id = h.id
        WHERE h.portfolio_name = ? AND h.status = 'sold'
        ORDER BY s.sell_date DESC, s.id DESC
    """
    rows = conn.execute(query, (portfolio_name,)).fetchall()
    return [dict(r) for r in rows]


def get_holding(holding_id: int) -> dict[str, Any] | None:
    """Fetch a single holding by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM holding WHERE id = ?", (holding_id,)).fetchone()
    return dict(row) if row else None


def get_lots(holding_id: int) -> list[dict[str, Any]]:
    """Return all child buy lots for a parent holding, ordered by invest date."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, holding_id, invest_date, quantity, avg_price, invested_amount,
               buy_charge, remarks, app, created_at
        FROM buy_lot
        WHERE holding_id = ?
        ORDER BY invest_date ASC, id ASC
        """,
        (holding_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_holding(
    portfolio_name: str,
    symbol: str,
    scheme_name: str | None = None,
    invest_date: str = "",
    quantity: float = 0.0,
    avg_price: float = 0.0,
    person: str | None = None,
    remarks: str | None = None,
    app: str | None = None,
    buy_charge: float | None = None,
    name_confirmed: bool = False,
    bought_reason: str | None = None,
    status: str = "open",
    invested_amount: float | None = None,
    stock_name: str | None = None,
) -> tuple[int, int]:
    """Add a holding and its initial buy lot.

    If an open holding for (portfolio_name, symbol) already exists,
    appends the buy lot to it.
    Returns (holding_id, lot_id).
    """
    conn = get_connection()
    now = _utc_now_iso()
    symbol = symbol.strip().upper()
    resolved_stock_name = (stock_name or scheme_name or symbol).strip()
    resolved_scheme_name = (scheme_name or stock_name or symbol).strip()

    conn.execute("BEGIN IMMEDIATE")
    try:
        holding_id: int | None = None
        if status == "open":
            existing = conn.execute(
                "SELECT id FROM holding WHERE portfolio_name = ? AND symbol = ? AND status = 'open'",
                (portfolio_name, symbol),
            ).fetchone()
            if existing:
                holding_id = existing["id"]

        if holding_id is None:
            cur = conn.execute(
                """
                INSERT INTO holding (
                    portfolio_name, symbol, scheme_name, stock_name, name_confirmed,
                    person, app, remarks, bought_reason, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    portfolio_name,
                    symbol,
                    resolved_scheme_name,
                    resolved_stock_name,
                    1 if name_confirmed else 0,
                    person,
                    app,
                    remarks,
                    bought_reason,
                    status,
                    now,
                    now,
                ),
            )
            holding_id = cur.lastrowid

        # Insert child buy lot
        lot_cur = conn.execute(
            """
            INSERT INTO buy_lot (
                holding_id, invest_date, quantity, avg_price, invested_amount,
                buy_charge, remarks, app, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                holding_id,
                invest_date,
                quantity,
                avg_price,
                invested_amount,
                buy_charge,
                remarks,
                app,
                now,
            ),
        )
        lot_id = lot_cur.lastrowid
        conn.execute("COMMIT")
        return holding_id, lot_id
    except Exception:
        conn.execute("ROLLBACK")
        raise


def add_buy_lot(
    holding_id: int,
    invest_date: str,
    quantity: float,
    avg_price: float,
    buy_charge: float | None = None,
    remarks: str | None = None,
    app: str | None = None,
    invested_amount: float | None = None,
) -> int:
    """Append a new buy lot to an existing holding."""
    conn = get_connection()
    now = _utc_now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            """
            INSERT INTO buy_lot (
                holding_id, invest_date, quantity, avg_price, invested_amount,
                buy_charge, remarks, app, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (holding_id, invest_date, quantity, avg_price, invested_amount, buy_charge, remarks, app, now),
        )
        conn.execute(
            "UPDATE holding SET updated_at = ? WHERE id = ?",
            (now, holding_id),
        )
        conn.execute("COMMIT")
        return cur.lastrowid
    except Exception:
        conn.execute("ROLLBACK")
        raise


def delete_holding(holding_id: int) -> bool:
    """Delete a holding and cascade to its buy lots and sales."""
    conn = get_connection()
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute("DELETE FROM holding WHERE id = ?", (holding_id,))
        deleted = cur.rowcount > 0
        conn.execute("COMMIT")
        return deleted
    except Exception:
        conn.execute("ROLLBACK")
        raise


def delete_lot(lot_id: int) -> bool:
    """Delete a single buy lot. Leaves parent holding intact."""
    conn = get_connection()
    conn.execute("BEGIN IMMEDIATE")
    try:
        lot = conn.execute("SELECT holding_id FROM buy_lot WHERE id = ?", (lot_id,)).fetchone()
        if not lot:
            conn.execute("ROLLBACK")
            return False
        holding_id = lot["holding_id"]
        conn.execute("DELETE FROM buy_lot WHERE id = ?", (lot_id,))
        # Check if holding still has lots
        remaining = conn.execute(
            "SELECT COUNT(*) AS c FROM buy_lot WHERE holding_id = ?",
            (holding_id,),
        ).fetchone()["c"]
        if remaining == 0:
            # No lots left, remove holding
            conn.execute("DELETE FROM holding WHERE id = ?", (holding_id,))
        else:
            conn.execute(
                "UPDATE holding SET updated_at = ? WHERE id = ?",
                (_utc_now_iso(), holding_id),
            )
        conn.execute("COMMIT")
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise


def get_lot(lot_id: int) -> dict[str, Any] | None:
    """Fetch a single buy lot by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM buy_lot WHERE id = ?", (lot_id,)).fetchone()
    return dict(row) if row else None


def update_lot(
    lot_id: int,
    invest_date: str,
    quantity: float,
    avg_price: float,
    invested_amount: float | None = None,
    buy_charge: float | None = None,
    remarks: str | None = None,
    app: str | None = None,
) -> bool:
    """Update values for an individual buy lot."""
    conn = get_connection()
    now = _utc_now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        lot = conn.execute("SELECT holding_id FROM buy_lot WHERE id = ?", (lot_id,)).fetchone()
        if not lot:
            conn.execute("ROLLBACK")
            return False
        holding_id = lot["holding_id"]
        conn.execute(
            """
            UPDATE buy_lot
            SET invest_date = ?, quantity = ?, avg_price = ?,
                invested_amount = ?, buy_charge = ?, remarks = ?,
                app = COALESCE(?, app)
            WHERE id = ?
            """,
            (invest_date, quantity, avg_price, invested_amount, buy_charge, remarks, app, lot_id),
        )
        conn.execute(
            "UPDATE holding SET updated_at = ? WHERE id = ?",
            (now, holding_id),
        )
        conn.execute("COMMIT")
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise


def update_holding(
    holding_id: int,
    symbol: str | None = None,
    scheme_name: str | None = None,
    person: str | None = None,
    remarks: str | None = None,
    stock_name: str | None = None,
    name_confirmed: bool | None = None,
) -> bool:
    """Update high-level metadata for an open holding."""
    conn = get_connection()
    now = _utc_now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        holding = conn.execute("SELECT * FROM holding WHERE id = ?", (holding_id,)).fetchone()
        if not holding:
            conn.execute("ROLLBACK")
            return False
        curr_stock_name = holding["stock_name"] if ("stock_name" in holding.keys() and holding["stock_name"]) else holding["scheme_name"]
        new_symbol = symbol.strip().upper() if symbol is not None and symbol.strip() else holding["symbol"]
        new_stock = stock_name.strip() if stock_name is not None and stock_name.strip() else (scheme_name.strip() if scheme_name is not None and scheme_name.strip() else curr_stock_name)
        new_scheme = scheme_name.strip() if scheme_name is not None and scheme_name.strip() else new_stock
        new_person = person.strip().upper() if person is not None else holding["person"]
        new_remarks = remarks.strip() if remarks is not None else holding["remarks"]
        new_confirmed = int(name_confirmed) if name_confirmed is not None else holding["name_confirmed"]
        conn.execute(
            """
            UPDATE holding
            SET symbol = ?, scheme_name = ?, stock_name = ?, person = ?, remarks = ?, name_confirmed = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_symbol, new_scheme, new_stock, new_person, new_remarks, new_confirmed, now, holding_id),
        )
        conn.execute("COMMIT")
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise


def update_sold_position(
    holding_id: int,
    invest_date: str,
    sell_date: str,
    quantity: float,
    avg_price: float,
    sell_price: float,
    invested_amount: float | None = None,
    buy_charge: float | None = None,
    sell_charge: float | None = None,
    remarks: str | None = None,
    person: str | None = None,
    symbol: str | None = None,
    scheme_name: str | None = None,
    stock_name: str | None = None,
    name_confirmed: bool | None = None,
) -> bool:
    """Update values for a sold position (holding, buy_lot, and sale records)."""
    conn = get_connection()
    now = _utc_now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        holding = conn.execute("SELECT * FROM holding WHERE id = ? AND status = 'sold'", (holding_id,)).fetchone()
        if not holding:
            conn.execute("ROLLBACK")
            return False

        curr_stock_name = holding["stock_name"] if ("stock_name" in holding.keys() and holding["stock_name"]) else holding["scheme_name"]
        new_symbol = symbol.strip().upper() if symbol is not None and symbol.strip() else holding["symbol"]
        new_stock = stock_name.strip() if stock_name is not None and stock_name.strip() else (scheme_name.strip() if scheme_name is not None and scheme_name.strip() else curr_stock_name)
        new_scheme = scheme_name.strip() if scheme_name is not None and scheme_name.strip() else new_stock
        new_person = person.strip().upper() if person is not None else holding["person"]
        new_confirmed = int(name_confirmed) if name_confirmed is not None else holding["name_confirmed"]

        conn.execute(
            """
            UPDATE holding
            SET symbol = ?, scheme_name = ?, stock_name = ?, person = ?, remarks = ?, name_confirmed = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_symbol, new_scheme, new_stock, new_person, remarks, new_confirmed, now, holding_id),
        )

        conn.execute(
            """
            UPDATE buy_lot
            SET invest_date = ?, quantity = ?, avg_price = ?,
                invested_amount = ?, buy_charge = ?, remarks = ?
            WHERE holding_id = ?
            """,
            (invest_date, quantity, avg_price, invested_amount, buy_charge, remarks, holding_id),
        )

        conn.execute(
            """
            UPDATE sale
            SET sell_date = ?, quantity = ?, sell_price = ?,
                sell_charge = ?, remarks = ?
            WHERE holding_id = ?
            """,
            (sell_date, quantity, sell_price, sell_charge, remarks, holding_id),
        )

        conn.execute("COMMIT")
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise


def sell_holding(
    holding_id: int,
    sell_date: str,
    sell_price: float,
    quantity: float | None = None,
    remarks: str | None = None,
    sell_charge: float | None = None,
    sold_reason: str | None = None,
    mistake_learned: str | None = None,
) -> int:
    """Mark a holding (or part of it) as sold and record the sale transaction(s).

    For each buy lot consumed in FIFO order, creates an individual sold holding,
    buy lot, and sale record. This ensures that a stock with multiple buy lots
    displays all its individual sold transactions in the Sold Positions history.
    """
    conn = get_connection()
    now = _utc_now_iso()

    conn.execute("BEGIN IMMEDIATE")
    try:
        holding = conn.execute("SELECT * FROM holding WHERE id = ?", (holding_id,)).fetchone()
        if not holding:
            raise ValueError(f"Holding {holding_id} not found")

        # Fetch all lots for this holding ordered by invest date (FIFO)
        lot_rows = conn.execute(
            "SELECT * FROM buy_lot WHERE holding_id = ? ORDER BY invest_date ASC, id ASC",
            (holding_id,),
        ).fetchall()
        total_q = sum(float(r["quantity"]) for r in lot_rows)

        sell_total = total_q if (quantity is None or quantity >= total_q) else float(quantity)
        rem = sell_total
        last_sale_id = None

        for lot in lot_rows:
            if rem <= 0:
                break
            lot_id = lot["id"]
            l_qty = float(lot["quantity"])
            l_price = float(lot["avg_price"])
            l_bc = float(lot["buy_charge"]) if lot["buy_charge"] is not None else None
            l_inv = float(lot["invested_amount"]) if lot["invested_amount"] is not None else None
            take_qty = min(l_qty, rem)

            take_bc = round(l_bc * (take_qty / l_qty), 4) if l_bc is not None else None
            left_bc = round(l_bc - take_bc, 4) if (l_bc is not None and take_bc is not None) else None

            take_inv = round(l_inv * (take_qty / l_qty), 4) if l_inv is not None else round(take_qty * l_price, 4)
            left_inv = round(l_inv - take_inv, 4) if (l_inv is not None and take_inv is not None) else round((l_qty - take_qty) * l_price, 4)

            take_sc = round(float(sell_charge) * (take_qty / sell_total), 4) if sell_charge is not None else None

            # Create individual sold holding for this tranche
            holding_stock_name = holding["stock_name"] if ("stock_name" in holding.keys() and holding["stock_name"]) else holding["scheme_name"]
            sold_cur = conn.execute(
                """
                INSERT INTO holding (
                    portfolio_name, symbol, scheme_name, stock_name, name_confirmed,
                    person, app, remarks, bought_reason, sold_reason,
                    mistake_learned, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'sold', ?, ?)
                """,
                (
                    holding["portfolio_name"],
                    holding["symbol"],
                    holding["scheme_name"],
                    holding_stock_name,
                    holding["name_confirmed"],
                    holding["person"],
                    holding["app"],
                    remarks or holding["remarks"],
                    holding["bought_reason"],
                    sold_reason or holding["sold_reason"],
                    mistake_learned or holding["mistake_learned"],
                    now,
                    now,
                ),
            )
            sold_holding_id = sold_cur.lastrowid

            # Insert buy lot for this tranche
            conn.execute(
                """
                INSERT INTO buy_lot (
                    holding_id, invest_date, quantity, avg_price,
                    invested_amount, buy_charge, remarks, app, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sold_holding_id,
                    lot["invest_date"],
                    take_qty,
                    l_price,
                    take_inv,
                    take_bc,
                    lot["remarks"],
                    lot["app"],
                    now,
                ),
            )

            # Insert sale record for this tranche
            cur_sale = conn.execute(
                """
                INSERT INTO sale (
                    holding_id, sell_date, quantity, sell_price,
                    sell_charge, remarks, app, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sold_holding_id,
                    sell_date,
                    take_qty,
                    sell_price,
                    take_sc,
                    remarks or holding["remarks"],
                    holding["app"],
                    now,
                ),
            )
            last_sale_id = cur_sale.lastrowid

            # Update or remove lot from open holding
            if take_qty >= l_qty:
                conn.execute("DELETE FROM buy_lot WHERE id = ?", (lot_id,))
            else:
                conn.execute(
                    "UPDATE buy_lot SET quantity = ?, invested_amount = ?, buy_charge = ? WHERE id = ?",
                    (round(l_qty - take_qty, 4), left_inv, left_bc, lot_id),
                )
            rem -= take_qty

        # Clean up or update original open holding
        remaining_count = conn.execute(
            "SELECT COUNT(*) FROM buy_lot WHERE holding_id = ?", (holding_id,)
        ).fetchone()[0]
        if remaining_count == 0:
            conn.execute("DELETE FROM holding WHERE id = ?", (holding_id,))
        else:
            conn.execute(
                "UPDATE holding SET updated_at = ? WHERE id = ?",
                (now, holding_id),
            )

        conn.execute("COMMIT")
        return last_sale_id or 0
    except Exception:
        conn.execute("ROLLBACK")
        raise



def update_notes(
    holding_id: int,
    bought_reason: str | None = None,
    sold_reason: str | None = None,
    mistake_learned: str | None = None,
) -> bool:
    """Update §6 note fields for a holding."""
    conn = get_connection()
    now = _utc_now_iso()
    cur = conn.execute(
        """
        UPDATE holding
        SET bought_reason = COALESCE(?, bought_reason),
            sold_reason = COALESCE(?, sold_reason),
            mistake_learned = COALESCE(?, mistake_learned),
            updated_at = ?
        WHERE id = ?
        """,
        (bought_reason, sold_reason, mistake_learned, now, holding_id),
    )
    return cur.rowcount > 0


def list_all_mistakes() -> list[dict[str, Any]]:
    """Return all holdings that have non-empty mistake_learned notes (§6 follow-up)."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, portfolio_name, symbol, scheme_name, status,
               bought_reason, sold_reason, mistake_learned, updated_at
        FROM holding
        WHERE mistake_learned IS NOT NULL AND TRIM(mistake_learned) != ''
        ORDER BY updated_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]
