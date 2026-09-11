"""HTTP routes for Portfolio Tracker."""

import io
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file

from ...errors import ValidationError
from ...data_fetcher import fetch_ticker_quote
from ...portfolio import normalize_symbol

logger = logging.getLogger(__name__)
portfolio_tracker_bp = Blueprint("portfolio_tracker", __name__)

@portfolio_tracker_bp.get("/api/portfolio-tracker/<portfolio>")
def api_portfolio_tracker_data(portfolio: str):
    """Fetch complete holdings, sold, dividends, totals, and summary for a portfolio."""
    port_name = portfolio.strip().upper()
    if port_name not in ("MADI", "BAPA", "LOAN"):
        return jsonify({"ok": False, "error": f"Invalid portfolio: {portfolio}"}), 400

    from ...db.repositories import dividends as div_repo
    from ...db.repositories import holdings as hold_repo
    from ...db.repositories import quotes as quote_repo
    from ...db.repositories import summary as sum_repo
    from ...portfolio_tracker import (
        compute_summary_panel,
        compute_totals,
        enrich_holding_row,
        enrich_sold_row,
    )

    quotes_cache = quote_repo.load_quotes_cache()

    # Open holdings with child buy lots
    open_raw = hold_repo.list_holdings(port_name, status="open")
    enriched_open = []
    for h in open_raw:
        lots = hold_repo.get_lots(h["id"])
        sym = h["symbol"]
        bare = sym.split(".")[0]
        quote = next(
            (
                quotes_cache[key]
                for key in (sym, bare, f"{bare}.NS", f"{bare}.BO")
                if key in quotes_cache
            ),
            None,
        )
        live_price = quote["price"] if quote and quote.get("price") else None
        enriched_open.append(enrich_holding_row(h, live_price=live_price, lots=lots))

    open_totals = compute_totals(enriched_open)

    # Sold holdings
    sold_raw = hold_repo.list_holdings(port_name, status="sold")
    enriched_sold = [enrich_sold_row(s) for s in sold_raw]
    sold_totals = compute_totals(enriched_sold)

    # Dividends
    dividends = div_repo.list_dividends(port_name)
    total_div = div_repo.total_dividends(port_name)

    # Summary panel
    summary_data = None
    if port_name == "LOAN":
        sum_vals = sum_repo.get_all()
        # Stock Profit in Block B reflects realized gains from sold positions: Earned total - Loss total
        loan_earned = sold_totals["earned"]
        loan_loss = sold_totals["loss"]
        loan_stock_invest = open_totals["invested_amount"]
        summary_data = compute_summary_panel(
            sum_vals,
            loan_earned=loan_earned,
            loan_loss=loan_loss,
            loan_dividends=total_div,
            loan_stock_invest=loan_stock_invest,
        )

    return jsonify({
        "ok": True,
        "portfolio": port_name,
        "open_holdings": enriched_open,
        "sold_holdings": enriched_sold,
        "open_totals": open_totals,
        "sold_totals": sold_totals,
        "dividends": dividends,
        "total_dividends": round(total_div, 2),
        "summary": summary_data,
    })


# Not every holding is an NSE stock, so a bare ticker is tried against both exchanges.
_TICKER_SUFFIXES = (".NS", ".BO")


def _resolve_ticker(raw_symbol: str) -> dict:
    """Resolve a ticker to the exchange-suffixed symbol that actually quotes.

    Returns ``{symbol, name, price, found}`` where ``found`` reports whether a real
    company name (not just the ticker) could be fetched — §3's confirmation trigger.
    """
    from ...db.repositories import quotes as quote_repo

    sym = (raw_symbol or "").strip().upper().replace(" ", "")
    if not sym:
        return {"symbol": "", "name": "", "price": None, "found": False}

    if "." in sym or sym.startswith("^"):
        candidates = [sym]
    else:
        candidates = [f"{sym}{suffix}" for suffix in _TICKER_SUFFIXES]

    for cand in [sym, *candidates]:
        cached = quote_repo.get_quote(cand)
        if cached and cached.get("price"):
            name = (cached.get("name") or "").strip()
            resolved_name = "" if name.upper() in ("", cand, sym) else name
            return {
                "symbol": cand,
                "name": resolved_name,
                "price": cached.get("price"),
                "found": bool(resolved_name),
            }

    from ...data_fetcher import fetch_ticker_quote

    for cand in candidates:
        try:
            res = fetch_ticker_quote(cand)
        except Exception as exc:
            logger.info("Ticker lookup failed for %s: %s", cand, exc)
            continue
        if not res.get("price"):
            continue
        name = (res.get("name") or "").strip()
        resolved_name = "" if name.upper() in ("", cand, sym) else name
        return {
            "symbol": cand,
            "name": resolved_name,
            "price": res.get("price"),
            "found": bool(resolved_name),
        }

    return {"symbol": candidates[0], "name": "", "price": None, "found": False}


def _get_tracker_port(portfolio: str, person: str | None = None) -> str | None:
    port = (portfolio or "").strip().upper()
    p = (person or "").strip().upper()
    if port == "MADI" or (port == "LOAN" and p == "MADI"):
        return "MADI"
    if port == "BAPA" or (port == "LOAN" and p == "BAPA"):
        return "BAPA"
    return None


def _sync_tracker_tab_symbol(tracker_port: str | None, symbol: str) -> None:
    """Sync a single symbol in Tracker tab snapshot after changes in Portfolio Tracker."""
    if not tracker_port or not symbol:
        return
    try:
        from ...portfolio import load_tracker_portfolios_meta, normalize_symbol
        from ...service import build_row, drop_row, load_snapshot, save_snapshot, upsert_row
        try:
            norm_sym = normalize_symbol(symbol)
        except Exception:
            norm_sym = symbol.strip().upper()

        meta_dict = load_tracker_portfolios_meta((tracker_port,)).get(tracker_port, {})
        if norm_sym not in meta_dict:
            drop_row(tracker_port, norm_sym, source="holding-removed")
        else:
            meta = meta_dict[norm_sym]
            snap = load_snapshot()
            rows = snap.get("portfolios", {}).get(tracker_port, {}).get("rows", [])
            found = False
            for r in rows:
                if r.get("symbol") == norm_sym:
                    r["avg_price"] = meta.get("avg_price")
                    r["is_sourced"] = meta.get("is_sourced", False)
                    r["is_manual"] = meta.get("is_manual", False)
                    if meta.get("stock_name"):
                        r["name"] = meta["stock_name"]
                    found = True
                    break
            if found:
                save_snapshot(snap)
            else:
                row = build_row(norm_sym)
                row["avg_price"] = meta.get("avg_price")
                row["is_sourced"] = meta.get("is_sourced", False)
                row["is_manual"] = meta.get("is_manual", False)
                if meta.get("stock_name"):
                    row["name"] = meta["stock_name"]
                upsert_row(tracker_port, row, source="holding-synced")
    except Exception as exc:
        logger.warning("Failed to sync Tracker tab for %s in %s: %s", symbol, tracker_port, exc)


@portfolio_tracker_bp.get("/api/portfolio-tracker/lookup-ticker")
def api_portfolio_tracker_lookup_ticker():
    """Look up stock name and quote for a ticker symbol."""
    sym = (request.args.get("symbol") or "").strip().upper()
    if not sym:
        return jsonify({"ok": False, "error": "Symbol is required."}), 400

    res = _resolve_ticker(sym)
    return jsonify({
        "ok": True,
        "symbol": sym,
        "resolved_symbol": res["symbol"],
        "name": res["name"],
        "price": res["price"],
        "found": res["found"],
    })


@portfolio_tracker_bp.post("/api/portfolio-tracker/holding")
def api_portfolio_tracker_add_holding():
    """Add a new open holding / buy lot."""
    payload = request.get_json(silent=True) or request.form
    portfolio = (payload.get("portfolio") or "").strip().upper()
    symbol = (payload.get("symbol") or "").strip().upper()
    invest_date = (payload.get("invest_date") or "").strip()
    quantity = float(payload.get("quantity") or 0.0)
    avg_price = float(payload.get("avg_price") or 0.0)

    if not portfolio or not symbol or quantity <= 0 or avg_price <= 0:
        return jsonify({"ok": False, "error": "portfolio, symbol, quantity (>0), and avg_price (>0) are required."}), 400

    from ...db.backup import create_backup
    from ...db.repositories import holdings as hold_repo

    resolved = _resolve_ticker(symbol)
    stored_symbol = resolved["symbol"] or symbol

    stock_name = (payload.get("stock_name") or payload.get("scheme_name") or "").strip()
    name_confirmed = bool(payload.get("name_confirmed"))

    if stock_name:
        name_confirmed = True
    elif resolved.get("found") and resolved.get("name"):
        stock_name = resolved["name"]
        name_confirmed = True
    else:
        # Sensible fallback: empty string fallback if ticker lookup fails, rather than crashing
        stock_name = ""
        name_confirmed = False

    scheme_name = stock_name or stored_symbol

    person = (payload.get("person") or "").strip().upper() if portfolio == "LOAN" else None
    remarks = (payload.get("remarks") or "").strip() or None
    bought_reason = (payload.get("bought_reason") or "").strip() or None

    holding_id, lot_id = hold_repo.add_holding(
        portfolio_name=portfolio,
        symbol=stored_symbol,
        scheme_name=scheme_name,
        stock_name=stock_name,
        invest_date=invest_date or datetime.now().strftime("%Y-%m-%d"),
        quantity=quantity,
        avg_price=avg_price,
        person=person,
        remarks=remarks,
        name_confirmed=name_confirmed,
        bought_reason=bought_reason,
    )

    try:
        create_backup()
    except Exception as exc:
        logger.warning("Auto backup after adding holding failed: %s", exc)

    # Sync into Tracker tab
    t_port = _get_tracker_port(portfolio, person)
    if t_port:
        _sync_tracker_tab_symbol(t_port, stored_symbol)

    return jsonify({
        "ok": True,
        "holding_id": holding_id,
        "lot_id": lot_id,
        "symbol": stored_symbol,
        "stock_name": stock_name,
        "message": f"Successfully added holding for {stored_symbol} in {portfolio}.",
    })


@portfolio_tracker_bp.post("/api/portfolio-tracker/lot")
def api_portfolio_tracker_add_lot():
    """Add a child buy lot to an existing holding."""
    payload = request.get_json(silent=True) or request.form
    holding_id = int(payload.get("holding_id") or 0)
    invest_date = (payload.get("invest_date") or "").strip()
    quantity = float(payload.get("quantity") or 0.0)
    avg_price = float(payload.get("avg_price") or 0.0)
    remarks = (payload.get("remarks") or "").strip() or None

    if holding_id <= 0 or quantity <= 0 or avg_price <= 0:
        return jsonify({"ok": False, "error": "Valid holding_id, quantity, and avg_price required."}), 400

    from ...db.backup import create_backup
    from ...db.repositories import holdings as hold_repo

    holding = hold_repo.get_holding(holding_id)

    lot_id = hold_repo.add_buy_lot(
        holding_id=holding_id,
        invest_date=invest_date or datetime.now().strftime("%Y-%m-%d"),
        quantity=quantity,
        avg_price=avg_price,
        remarks=remarks,
    )

    try:
        create_backup()
    except Exception:
        pass

    if holding:
        t_port = _get_tracker_port(holding.get("portfolio_name"), holding.get("person"))
        _sync_tracker_tab_symbol(t_port, holding.get("symbol"))

    return jsonify({"ok": True, "lot_id": lot_id, "message": "Buy lot added successfully."})


@portfolio_tracker_bp.delete("/api/portfolio-tracker/holding/<int:holding_id>")
def api_portfolio_tracker_delete_holding(holding_id: int):
    """Delete a holding and its associated buy lots."""
    from ...db.backup import create_backup
    from ...db.repositories import holdings as hold_repo

    holding = hold_repo.get_holding(holding_id)
    t_port = _get_tracker_port(holding["portfolio_name"], holding.get("person")) if holding else None
    h_sym = holding["symbol"] if holding else None

    deleted = hold_repo.delete_holding(holding_id)
    if not deleted:
        return jsonify({"ok": False, "error": f"Holding {holding_id} not found."}), 404

    try:
        create_backup()
    except Exception:
        pass

    if t_port and h_sym:
        _sync_tracker_tab_symbol(t_port, h_sym)

    return jsonify({"ok": True, "message": f"Holding {holding_id} deleted."})


@portfolio_tracker_bp.delete("/api/portfolio-tracker/lot/<int:lot_id>")
def api_portfolio_tracker_delete_lot(lot_id: int):
    """Delete a single buy lot."""
    from ...db.backup import create_backup
    from ...db.repositories import holdings as hold_repo

    lot = hold_repo.get_lot(lot_id)
    holding = hold_repo.get_holding(lot["holding_id"]) if lot else None
    t_port = _get_tracker_port(holding["portfolio_name"], holding.get("person")) if holding else None
    h_sym = holding["symbol"] if holding else None

    deleted = hold_repo.delete_lot(lot_id)
    if not deleted:
        return jsonify({"ok": False, "error": f"Lot {lot_id} not found."}), 404

    try:
        create_backup()
    except Exception:
        pass

    if t_port and h_sym:
        _sync_tracker_tab_symbol(t_port, h_sym)

    return jsonify({"ok": True, "message": f"Lot {lot_id} deleted."})


@portfolio_tracker_bp.put("/api/portfolio-tracker/lot/<int:lot_id>")
def api_portfolio_tracker_update_lot(lot_id: int):
    """Update a buy lot's details (invest date, quantity, avg price, invested amount, buy charge, remarks)."""
    payload = request.get_json(silent=True) or request.form
    invest_date = (payload.get("invest_date") or "").strip()
    try:
        quantity = float(payload.get("quantity") or 0.0)
        avg_price = float(payload.get("avg_price") or 0.0)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid quantity or avg_price."}), 400

    if quantity <= 0 or avg_price <= 0:
        return jsonify({"ok": False, "error": "quantity and avg_price must be greater than 0."}), 400

    invested_amount = payload.get("invested_amount")
    if invested_amount is not None and str(invested_amount).strip() != "":
        try:
            invested_amount = float(invested_amount)
        except (ValueError, TypeError):
            invested_amount = None
    else:
        invested_amount = None

    buy_charge = payload.get("buy_charge")
    if buy_charge is not None and str(buy_charge).strip() != "":
        try:
            buy_charge = float(buy_charge)
        except (ValueError, TypeError):
            buy_charge = None
    else:
        buy_charge = None

    remarks = payload.get("remarks")
    if remarks is not None:
        remarks = str(remarks).strip()

    app = payload.get("app")
    if app is not None:
        app = str(app).strip()

    from ...db.backup import create_backup
    from ...db.repositories import holdings as hold_repo

    updated = hold_repo.update_lot(
        lot_id=lot_id,
        invest_date=invest_date or datetime.now().strftime("%Y-%m-%d"),
        quantity=quantity,
        avg_price=avg_price,
        invested_amount=invested_amount,
        buy_charge=buy_charge,
        remarks=remarks,
        app=app,
    )
    if not updated:
        return jsonify({"ok": False, "error": f"Lot {lot_id} not found."}), 404

    lot = hold_repo.get_lot(lot_id)
    holding = hold_repo.get_holding(lot["holding_id"]) if lot else None
    t_port = _get_tracker_port(holding["portfolio_name"], holding.get("person")) if holding else None
    h_sym = holding["symbol"] if holding else None
    if t_port and h_sym:
        _sync_tracker_tab_symbol(t_port, h_sym)

    try:
        create_backup()
    except Exception:
        pass

    return jsonify({"ok": True, "message": f"Lot {lot_id} updated successfully."})


@portfolio_tracker_bp.put("/api/portfolio-tracker/holding/<int:holding_id>")
def api_portfolio_tracker_update_holding(holding_id: int):
    """Update high-level holding details (symbol, scheme_name/stock_name, person, remarks)."""
    payload = request.get_json(silent=True) or request.form
    raw_symbol = payload.get("symbol")
    clean_symbol = raw_symbol.strip().upper() if raw_symbol and raw_symbol.strip() else None
    raw_stock_name = payload.get("stock_name") or payload.get("scheme_name")
    clean_stock_name = raw_stock_name.strip() if raw_stock_name and raw_stock_name.strip() else ""
    person = payload.get("person")
    remarks = payload.get("remarks")
    name_confirmed = payload.get("name_confirmed")

    if clean_symbol and (not clean_stock_name or clean_stock_name.upper() == clean_symbol):
        resolved = _resolve_ticker(clean_symbol)
        if resolved.get("found") and resolved.get("name"):
            clean_stock_name = resolved["name"]
            if name_confirmed is None:
                name_confirmed = True

    scheme_name = clean_stock_name or clean_symbol
    stock_name = clean_stock_name

    from ...db.backup import create_backup
    from ...db.repositories import holdings as hold_repo

    updated = hold_repo.update_holding(
        holding_id=holding_id,
        symbol=clean_symbol,
        scheme_name=scheme_name,
        stock_name=stock_name,
        person=person,
        remarks=remarks,
        name_confirmed=name_confirmed,
    )
    if not updated:
        return jsonify({"ok": False, "error": f"Holding {holding_id} not found."}), 404

    try:
        create_backup()
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "message": f"Holding {holding_id} updated successfully.",
        "symbol": clean_symbol,
        "stock_name": stock_name,
    })


@portfolio_tracker_bp.post("/api/portfolio-tracker/swap")
def api_portfolio_tracker_swap():
    """Swap one or more open holdings to a different portfolio (LOAN, MADI, BAPA)."""
    payload = request.get_json(silent=True) or request.form
    if not payload:
        return jsonify({"ok": False, "error": "Invalid request payload."}), 400

    raw_ids = payload.get("holding_ids")
    if raw_ids is None and payload.get("holding_id") is not None:
        raw_ids = [payload.get("holding_id")]

    if not raw_ids or not isinstance(raw_ids, list):
        return jsonify({"ok": False, "error": "holding_ids must be a non-empty list of integers."}), 400

    try:
        holding_ids = [int(i) for i in raw_ids]
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid holding ID in holding_ids."}), 400

    target_portfolio = (payload.get("target_portfolio") or "").strip().upper()
    target_person = payload.get("target_person")

    from ...db.backup import create_backup
    from ...db.repositories import holdings as hold_repo

    try:
        res = hold_repo.swap_holdings(
            holding_ids=holding_ids,
            target_portfolio=target_portfolio,
            target_person=target_person,
        )
    except ValidationError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to swap holdings")
        return jsonify({"ok": False, "error": f"Failed to swap holdings: {exc}"}), 500

    try:
        create_backup()
    except Exception:
        pass

    target_desc = f"{target_portfolio} ({target_person})" if target_portfolio == "LOAN" else target_portfolio
    return jsonify({
        "ok": True,
        "message": f"Successfully moved {res['total_processed']} holding(s) to {target_desc}.",
        **res,
    })


@portfolio_tracker_bp.put("/api/portfolio-tracker/sold/<int:holding_id>")
def api_portfolio_tracker_update_sold(holding_id: int):
    """Update a sold position (invest_date, sell_date, quantity, avg_price, sell_price, invested_amount, buy_charge, sell_charge, remarks, person, stock_name)."""
    payload = request.get_json(silent=True) or request.form
    invest_date = (payload.get("invest_date") or "").strip()
    sell_date = (payload.get("sell_date") or "").strip()

    try:
        quantity = float(payload.get("quantity") or 0.0)
        avg_price = float(payload.get("avg_price") or 0.0)
        sell_price = float(payload.get("sell_price") or 0.0)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid quantity, avg_price, or sell_price."}), 400

    if quantity <= 0 or avg_price < 0 or sell_price < 0:
        return jsonify({"ok": False, "error": "quantity must be > 0 and prices must be >= 0."}), 400

    invested_amount = payload.get("invested_amount")
    if invested_amount is not None and str(invested_amount).strip() != "":
        try:
            invested_amount = float(invested_amount)
        except (ValueError, TypeError):
            invested_amount = None
    else:
        invested_amount = None

    buy_charge = payload.get("buy_charge")
    if buy_charge is not None and str(buy_charge).strip() != "":
        try:
            buy_charge = float(buy_charge)
        except (ValueError, TypeError):
            buy_charge = None
    else:
        buy_charge = None

    sell_charge = payload.get("sell_charge")
    if sell_charge is not None and str(sell_charge).strip() != "":
        try:
            sell_charge = float(sell_charge)
        except (ValueError, TypeError):
            sell_charge = None
    else:
        sell_charge = None

    remarks = payload.get("remarks")
    person = payload.get("person")
    raw_symbol = payload.get("symbol")
    clean_symbol = raw_symbol.strip().upper() if raw_symbol and raw_symbol.strip() else None
    raw_stock_name = payload.get("stock_name") or payload.get("scheme_name")
    clean_stock_name = raw_stock_name.strip() if raw_stock_name and raw_stock_name.strip() else ""
    name_confirmed = payload.get("name_confirmed")

    if clean_symbol and (not clean_stock_name or clean_stock_name.upper() == clean_symbol):
        resolved = _resolve_ticker(clean_symbol)
        if resolved.get("found") and resolved.get("name"):
            clean_stock_name = resolved["name"]
            if name_confirmed is None:
                name_confirmed = True

    scheme_name = clean_stock_name or clean_symbol
    stock_name = clean_stock_name

    from ...db.backup import create_backup
    from ...db.repositories import holdings as hold_repo

    updated = hold_repo.update_sold_position(
        holding_id=holding_id,
        invest_date=invest_date or datetime.now().strftime("%Y-%m-%d"),
        sell_date=sell_date or datetime.now().strftime("%Y-%m-%d"),
        quantity=quantity,
        avg_price=avg_price,
        sell_price=sell_price,
        invested_amount=invested_amount,
        buy_charge=buy_charge,
        sell_charge=sell_charge,
        remarks=remarks,
        person=person,
        symbol=clean_symbol,
        scheme_name=scheme_name,
        stock_name=stock_name,
        name_confirmed=name_confirmed,
    )
    if not updated:
        return jsonify({"ok": False, "error": f"Sold position {holding_id} not found."}), 404

    try:
        create_backup()
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "message": f"Sold position {holding_id} updated successfully.",
        "symbol": clean_symbol,
        "stock_name": stock_name,
    })


@portfolio_tracker_bp.post("/api/portfolio-tracker/sell")
def api_portfolio_tracker_sell():
    """Sell a holding, moving it to the Sold table."""
    payload = request.get_json(silent=True) or request.form
    holding_id = int(payload.get("holding_id") or 0)
    sell_date = (payload.get("sell_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    sell_price = float(payload.get("sell_price") or 0.0)
    quantity = float(payload["quantity"]) if payload.get("quantity") else None
    remarks = (payload.get("remarks") or "").strip() or None
    sold_reason = (payload.get("sold_reason") or "").strip() or None
    mistake_learned = (payload.get("mistake_learned") or "").strip() or None

    if holding_id <= 0 or sell_price <= 0:
        return jsonify({"ok": False, "error": "holding_id and sell_price (>0) are required."}), 400

    from ...db.backup import create_backup
    from ...db.repositories import holdings as hold_repo

    holding = hold_repo.get_holding(holding_id)
    t_port = _get_tracker_port(holding["portfolio_name"], holding.get("person")) if holding else None
    h_sym = holding["symbol"] if holding else None

    try:
        sale_id = hold_repo.sell_holding(
            holding_id=holding_id,
            sell_date=sell_date,
            sell_price=sell_price,
            quantity=quantity,
            remarks=remarks,
            sold_reason=sold_reason,
            mistake_learned=mistake_learned,
        )
        try:
            create_backup()
        except Exception:
            pass

        if t_port and h_sym:
            _sync_tracker_tab_symbol(t_port, h_sym)

        return jsonify({"ok": True, "sale_id": sale_id, "message": "Holding sold successfully."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@portfolio_tracker_bp.put("/api/portfolio-tracker/notes/<int:holding_id>")
def api_portfolio_tracker_update_notes(holding_id: int):
    """Update §6 note fields: bought_reason, sold_reason, mistake_learned."""
    payload = request.get_json(silent=True) or request.form
    from ...db.repositories import holdings as hold_repo

    updated = hold_repo.update_notes(
        holding_id=holding_id,
        bought_reason=payload.get("bought_reason"),
        sold_reason=payload.get("sold_reason"),
        mistake_learned=payload.get("mistake_learned"),
    )
    if not updated:
        return jsonify({"ok": False, "error": f"Holding {holding_id} not found."}), 404

    return jsonify({"ok": True, "message": "Notes updated successfully."})


@portfolio_tracker_bp.get("/api/portfolio-tracker/mistakes")
def api_portfolio_tracker_list_mistakes():
    """List all holdings with lessons/mistakes recorded (§6 follow-up)."""
    from ...db.repositories import holdings as hold_repo
    mistakes = hold_repo.list_all_mistakes()
    return jsonify({"ok": True, "mistakes": mistakes})


@portfolio_tracker_bp.post("/api/portfolio-tracker/dividend")
def api_portfolio_tracker_add_dividend():
    """Add a dividend record."""
    payload = request.get_json(silent=True) or request.form
    portfolio = (payload.get("portfolio") or "").strip().upper()
    symbol = (payload.get("symbol") or "").strip().upper()
    value = float(payload.get("value") or 0.0)
    received_date = (payload.get("received_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")

    if not portfolio or not symbol or value <= 0:
        return jsonify({"ok": False, "error": "portfolio, symbol, and value (>0) are required."}), 400

    from ...db.repositories import dividends as div_repo
    div_id = div_repo.add_dividend(portfolio, symbol, value, received_date)
    return jsonify({"ok": True, "dividend_id": div_id, "message": f"Dividend recorded for {symbol}."})


@portfolio_tracker_bp.delete("/api/portfolio-tracker/dividend/<int:dividend_id>")
def api_portfolio_tracker_delete_dividend(dividend_id: int):
    """Delete a dividend record."""
    from ...db.repositories import dividends as div_repo
    deleted = div_repo.delete_dividend(dividend_id)
    if not deleted:
        return jsonify({"ok": False, "error": "Dividend not found."}), 404
    return jsonify({"ok": True, "message": "Dividend deleted."})


@portfolio_tracker_bp.get("/api/portfolio-tracker/summary")
def api_portfolio_tracker_get_summary():
    """Get Summary panel values."""
    from ...db.repositories import summary as sum_repo
    return jsonify({"ok": True, "values": sum_repo.get_all_rows()})


@portfolio_tracker_bp.put("/api/portfolio-tracker/summary")
def api_portfolio_tracker_update_summary():
    """Update a fixed value in the Summary panel."""
    payload = request.get_json(silent=True) or request.form
    key = (payload.get("key") or "").strip()
    val = float(payload.get("value") or 0.0)
    label = payload.get("label")

    if not key:
        return jsonify({"ok": False, "error": "Key is required."}), 400

    from ...db.repositories import summary as sum_repo
    sum_repo.upsert(key, val, label)
    return jsonify({"ok": True, "message": f"Updated summary field {key}."})


@portfolio_tracker_bp.post("/api/portfolio-tracker/import")
def api_portfolio_tracker_import():
    """Upload and import Excel workbook (Invest.xlsx) into Portfolio Tracker."""
    replace = request.args.get("replace", "false").lower() in ("true", "1", "yes")

    from ...paths import BASE_DIR
    from ...sheet_io import import_workbook

    file = request.files.get("file")
    if file:
        file_bytes = io.BytesIO(file.read())
        res = import_workbook(file_bytes, replace=replace)
    else:
        # Check if default Invest.xlsx exists in root directory
        default_file = BASE_DIR / "Invest.xlsx"
        if default_file.exists():
            res = import_workbook(default_file, replace=replace)
        else:
            return jsonify({"ok": False, "error": "No file uploaded and Invest.xlsx not found."}), 400

    return jsonify(res)


@portfolio_tracker_bp.get("/api/portfolio-tracker/export")
def api_portfolio_tracker_export():
    """Export current Portfolio Tracker database into standard Invest.xlsx or CSV format."""
    from flask import send_file
    from ...sheet_io import export_csv, export_workbook

    portfolio = request.args.get("portfolio")
    fmt = (request.args.get("format") or "xlsx").strip().lower()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    port_label = portfolio.upper() if portfolio else "ALL"

    if fmt == "csv":
        # CSV is one sheet per file, so a portfolio must be named explicitly.
        if port_label not in ("MADI", "BAPA", "LOAN"):
            return jsonify({
                "ok": False,
                "error": "CSV export requires ?portfolio=MADI|BAPA|LOAN.",
            }), 400
        buf = io.BytesIO()
        export_csv(buf, portfolio=port_label)
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name=f"Portfolio_Tracker_{port_label}_{stamp}.csv",
            mimetype="text/csv",
        )

    buf = io.BytesIO()
    export_workbook(buf, portfolio=portfolio)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"Portfolio_Tracker_{port_label}_{stamp}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
