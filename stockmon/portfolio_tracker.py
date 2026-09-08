"""Business logic and financial calculations for the Portfolio Tracker feature.

All mathematical formulas, derived columns, charge calculations, totals,
and summary panel derivations are strictly centralized here.
See docs/DATA_STORAGE_MIGRATION.md §5.4 and docs/SHEET_FORMAT.md.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from .sheet_format import parse_sheet_date

# Standard charge rates identified from Invest.xlsx
# Buy: (NSE 0.00345% + SEBI 0.0001% + Stamp Duty 0.015% + STT 0.1%) * Invested + GST 18% on NSE
BUY_CHARGE_BASE_RATE = 0.0000345 + 0.000001 + 0.00015 + 0.001  # 0.0011855
BUY_CHARGE_GST_RATE = 0.18 * 0.0000345                           # 0.00000621
BUY_CHARGE_TOTAL_RATE = BUY_CHARGE_BASE_RATE + BUY_CHARGE_GST_RATE  # ~0.00119171

# Sell: (STT 0.1% + NSE 0.00345% + SEBI 0.0001%) = 0.0010355 * Current_Total + GST 18% on NSE
SELL_CHARGE_BASE_RATE = 0.0010355
SELL_CHARGE_GST_RATE = 0.18 * 0.0000345
SELL_CHARGE_TOTAL_RATE = SELL_CHARGE_BASE_RATE + SELL_CHARGE_GST_RATE  # ~0.00104171


def compute_buy_charge(invested_amount: float) -> float:
    """Calculate standard statutory buy charges."""
    if invested_amount <= 0:
        return 0.0
    return round(invested_amount * BUY_CHARGE_TOTAL_RATE, 4)


def compute_sell_charge(current_total: float) -> float:
    """Calculate standard statutory sell charges."""
    if current_total <= 0:
        return 0.0
    return round(current_total * SELL_CHARGE_TOTAL_RATE, 4)


def calculate_period(start_date_str: str, end_date_str: str) -> tuple[int, int]:
    """Calculate (years, months) elapsed between start_date and end_date.

    Matches Excel's DATEDIF(start, end, 'M') and QUOTIENT(M, 12).
    """
    if not start_date_str or not end_date_str:
        return 0, 0

    norm_start = parse_sheet_date(start_date_str)
    norm_end = parse_sheet_date(end_date_str)

    try:
        d1 = datetime.strptime(norm_start, "%Y-%m-%d").date()
        d2 = datetime.strptime(norm_end, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0, 0

    if d2 < d1:
        return 0, 0

    # Number of full calendar months
    months = (d2.year - d1.year) * 12 + (d2.month - d1.month)
    if d2.day < d1.day:
        months -= 1
    months = max(0, months)
    years = months // 12
    return years, months


def calculate_returns(
    invested: float,
    current_total: float,
    months: int,
) -> tuple[float, float]:
    """Calculate (annual_return_pct, total_return_pct).

    Total return = ((Current Total / Invested) - 1) * 100
    Annual return = CAGR if months >= 12, else simple annualized if months > 0.
    """
    if invested <= 0:
        return 0.0, 0.0

    total_return = ((current_total / invested) - 1.0) * 100.0

    annual_return = 0.0
    years_float = months / 12.0
    if years_float >= 1.0 and current_total > 0:
        try:
            cagr = ((current_total / invested) ** (1.0 / years_float) - 1.0) * 100.0
            annual_return = round(cagr, 2)
        except (ValueError, OverflowError):
            annual_return = 0.0
    elif months > 0:
        annual_return = round(total_return * (12.0 / months), 2)

    return annual_return, round(total_return, 2)


def enrich_holding_row(
    holding: dict[str, Any],
    live_price: float | None = None,
    current_date: str | None = None,
    lots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Enrich an open holding with derived financial figures.

    Stores only inputs in the DB; all other columns are calculated at read time.
    """
    today_iso = current_date or date.today().isoformat()
    first_invest = holding.get("first_invest_date") or today_iso
    years, months = calculate_period(first_invest, today_iso)

    qty = float(holding.get("total_qty") or 0.0)
    avg_price = float(holding.get("weighted_avg_price") or 0.0)
    raw_inv = holding.get("total_invested")
    invested = float(raw_inv) if raw_inv is not None else (qty * avg_price)

    # Live market price (LTP) or fallback to avg price
    ltp = float(live_price) if live_price is not None and live_price > 0 else avg_price

    # Buy charge: use stored sum of buy charges if available, else compute
    stored_buy_charge = holding.get("total_buy_charge")
    buy_charge = float(stored_buy_charge) if stored_buy_charge is not None else compute_buy_charge(invested)

    current_total = qty * ltp
    sell_charge = compute_sell_charge(current_total)

    # Net P&L (Earned vs Loss)
    pnl = current_total - invested
    if pnl > 0:
        earned = current_total - buy_charge - sell_charge - invested
        loss = 0.0
    else:
        earned = 0.0
        # In the spreadsheet, Loss is negative
        loss = -(invested + buy_charge + sell_charge - current_total)

    annual_ret, total_ret = calculate_returns(invested, current_total, months)

    # Enrich child lots if provided
    enriched_lots = []
    if lots:
        for lot in lots:
            l_qty = float(lot.get("quantity") or 0.0)
            l_avg = float(lot.get("avg_price") or 0.0)
            l_raw_inv = lot.get("invested_amount")
            l_inv = float(l_raw_inv) if l_raw_inv is not None else (l_qty * l_avg)
            l_date = lot.get("invest_date") or today_iso
            l_y, l_m = calculate_period(l_date, today_iso)
            l_stored_bc = lot.get("buy_charge")
            l_bc = float(l_stored_bc) if l_stored_bc is not None else compute_buy_charge(l_inv)
            l_tot = l_qty * ltp
            l_sc = compute_sell_charge(l_tot)
            l_pnl = l_tot - l_inv
            l_earned = (l_tot - l_bc - l_sc - l_inv) if l_pnl > 0 else 0.0
            l_loss = -(l_inv + l_bc + l_sc - l_tot) if l_pnl <= 0 else 0.0
            l_ann, l_tot_ret = calculate_returns(l_inv, l_tot, l_m)
            enriched_lots.append(
                {
                    **lot,
                    "invested_amount": round(l_inv, 2),
                    "buy_charge": round(l_bc, 2),
                    "sell_charge": round(l_sc, 2),
                    "current_total": round(l_tot, 2),
                    "earned": round(l_earned, 2),
                    "loss": round(l_loss, 2),
                    "years": l_y,
                    "months": l_m,
                    "annual_return": l_ann,
                    "total_return": l_tot_ret,
                }
            )

    return {
        **holding,
        "stock_name": holding.get("stock_name") or holding.get("scheme_name") or "",
        "current_date": today_iso,
        "years": years,
        "months": months,
        "quantity": qty,
        "avg_price": round(avg_price, 2),
        "ltp": round(ltp, 2),
        "invested_amount": round(invested, 2),
        "buy_charge": round(buy_charge, 2),
        "sell_charge": round(sell_charge, 2),
        "current_total": round(current_total, 2),
        "earned": round(earned, 2),
        "loss": round(loss, 2),
        "annual_return": annual_ret,
        "total_return": total_ret,
        "lots": enriched_lots,
    }


def enrich_sold_row(sold_item: dict[str, Any]) -> dict[str, Any]:
    """Enrich a sold holding record with realized returns."""
    invest_date = sold_item.get("invest_date") or ""
    sell_date = sold_item.get("sell_date") or ""
    years, months = calculate_period(invest_date, sell_date)

    qty = float(sold_item.get("sold_quantity") or 0.0)
    avg_price = float(sold_item.get("avg_price") or 0.0)
    sell_price = float(sold_item.get("sell_price") or 0.0)

    raw_inv = sold_item.get("invested_amount")
    invested = float(raw_inv) if raw_inv is not None else (qty * avg_price)
    current_total = qty * sell_price

    stored_bc = sold_item.get("buy_charge")
    buy_charge = float(stored_bc) if stored_bc is not None else compute_buy_charge(invested)

    stored_sc = sold_item.get("sell_charge")
    sell_charge = float(stored_sc) if stored_sc is not None else compute_sell_charge(current_total)

    pnl = current_total - invested
    if pnl > 0:
        earned = current_total - buy_charge - sell_charge - invested
        loss = 0.0
    else:
        earned = 0.0
        loss = -(invested + buy_charge + sell_charge - current_total)

    annual_ret, total_ret = calculate_returns(invested, current_total, months)

    return {
        **sold_item,
        "stock_name": sold_item.get("stock_name") or sold_item.get("scheme_name") or "",
        "current_date": sell_date,
        "years": years,
        "months": months,
        "quantity": qty,
        "avg_price": round(avg_price, 2),
        "ltp": round(sell_price, 2),
        "invested_amount": round(invested, 2),
        "buy_charge": round(buy_charge, 2),
        "sell_charge": round(sell_charge, 2),
        "current_total": round(current_total, 2),
        "earned": round(earned, 2),
        "loss": round(loss, 2),
        "annual_return": annual_ret,
        "total_return": total_ret,
    }


def compute_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Calculate the Totals row for Holdings or Sold tables (§5)."""
    total_invested = sum(r.get("invested_amount", 0.0) for r in rows)
    total_current = sum(r.get("current_total", 0.0) for r in rows)
    total_earned = sum(r.get("earned", 0.0) for r in rows)
    total_loss = sum(r.get("loss", 0.0) for r in rows)
    # Net Profit / Realized Profit = Earned total - Loss total.
    # Note: loss is stored as a negative float (e.g. -1500.0),
    # so total_earned + total_loss equals total_earned - abs(total_loss).
    net_profit = total_earned + total_loss if total_loss <= 0 else total_earned - total_loss

    return {
        "invested_amount": round(total_invested, 2),
        "current_total": round(total_current, 2),
        "earned": round(total_earned, 2),
        "loss": round(total_loss, 2),
        "net_profit": round(net_profit, 2),
    }


def compute_summary_panel(
    summary_values: dict[str, float],
    loan_earned: float,
    loan_loss: float,
    loan_dividends: float,
    loan_stock_invest: float | None = None,
) -> dict[str, Any]:
    """Compute all Summary Panel values (Block A and Block B) per §8."""
    # Block A: Current Stock & ETF Invest is taken from Loan Total Invested if provided
    if loan_stock_invest is not None:
        stock_invest = float(loan_stock_invest)
    else:
        stock_invest = summary_values.get("current_stock_etf_invest", 0.0)
    mf_invest = summary_values.get("current_mf_invest", 0.0)
    mf_redeem = summary_values.get("current_mf_redeem", 0.0)
    total_block_a = stock_invest + mf_invest + mf_redeem

    # Block B
    loan_amount = summary_values.get("loan_amount", 0.0)
    # Loan money not yet deployed; negative once deployment exceeds the loan.
    remaining_invest_loan = loan_amount - total_block_a
    # Stock Profit = Earned + Loss of sold positions (since loss is negative)
    stock_profit = loan_earned + loan_loss if loan_loss <= 0 else loan_earned - loan_loss
    dividend_total = loan_dividends
    mf_redeem_profit = summary_values.get("current_mf_redeem_profit", 0.0)

    current_remaining = (
        remaining_invest_loan
        + stock_profit
        + dividend_total
        + mf_redeem_profit
    )

    return {
        "block_a": {
            "current_stock_etf_invest": round(stock_invest, 2),
            "current_mf_invest": round(mf_invest, 2),
            "current_mf_redeem": round(mf_redeem, 2),
            "total": round(total_block_a, 2),
        },
        "block_b": {
            "loan_amount": round(loan_amount, 2),
            "remaining_invest_loan": round(remaining_invest_loan, 2),
            "stock_profit": round(stock_profit, 2),
            "sold_earned": round(loan_earned, 2),
            "sold_loss": round(loan_loss, 2),
            "dividend": round(dividend_total, 2),
            "current_mf_redeem_profit": round(mf_redeem_profit, 2),
            "current_remaining": round(current_remaining, 2),
        },
    }
