"""Alpaca PAPER account: estimated realized P&L report from recent filled orders.

This is an informational estimate, NOT a tax return or authoritative broker ledger.
It assumes FIFO, ignores wash-sale adjustments, and cannot reconstruct opening
cost basis for positions purchased before the retrieved history window.
"""

import csv
import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

OUTPUT = "report.csv"
LOOKBACK_DAYS = 30
MAX_ORDERS = 500
# User-adjustable rough estimates, not actual broker charges or tax liability.
ESTIMATED_COST_RATE = Decimal(os.getenv("ESTIMATED_COST_RATE", "0.001"))
ESTIMATED_TAX_RATE = Decimal(os.getenv("ESTIMATED_TAX_RATE", "0.20"))
COLUMNS = [
    "symbol", "sell_time_utc", "quantity", "sell_proceeds_usd",
    "fifo_cost_basis_usd", "gross_realized_pnl_usd",
    "estimated_trading_cost_usd", "estimated_net_pnl_usd",
    "illustrative_tax_reserve_usd", "notes",
]


def money(value):
    return f"{value.quantize(Decimal('0.01')):.2f}"


def main():
    if os.getenv("PAPER_ONLY", "true").lower() != "true":
        raise RuntimeError("Safety lock: report supports paper trading only.")
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Missing ALPACA_API_KEY or ALPACA_SECRET_KEY GitHub secret.")
    if ESTIMATED_COST_RATE < 0 or ESTIMATED_TAX_RATE < 0:
        raise ValueError("Estimated rates cannot be negative.")

    trading = TradingClient(key, secret, paper=True)
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    orders = trading.get_orders(
        filter=GetOrdersRequest(status=QueryOrderStatus.ALL, after=since, limit=MAX_ORDERS)
    )
    fills = []
    for order in orders:
        qty = getattr(order, "filled_qty", None)
        price = getattr(order, "filled_avg_price", None)
        filled_at = getattr(order, "filled_at", None)
        if not qty or not price or not filled_at:
            continue
        qty, price = Decimal(str(qty)), Decimal(str(price))
        if qty <= 0 or price <= 0:
            continue
        fills.append((filled_at, str(order.symbol), order.side, qty, price))
    fills.sort(key=lambda row: row[0])

    lots = defaultdict(deque)
    rows = []
    unmatched_sells = 0
    for when, symbol, side, qty, price in fills:
        if side == OrderSide.BUY:
            lots[symbol].append([qty, price])
            continue
        if side != OrderSide.SELL:
            continue
        remaining = qty
        matched = Decimal("0")
        basis = Decimal("0")
        while remaining > 0 and lots[symbol]:
            lot_qty, buy_price = lots[symbol][0]
            used = min(remaining, lot_qty)
            basis += used * buy_price
            matched += used
            remaining -= used
            lots[symbol][0][0] -= used
            if lots[symbol][0][0] == 0:
                lots[symbol].popleft()
        if remaining > 0:
            unmatched_sells += 1
            print(f"WARNING: {symbol} sell has {remaining} shares with unknown cost basis; "
                  "excluded that portion from estimated P&L.")
        if matched <= 0:
            continue
        proceeds = matched * price
        gross = proceeds - basis
        # Proxy for spread/slippage/fees, not actual fees and may double-count
        # costs already embedded in executed prices.
        estimated_cost = (basis + proceeds) * ESTIMATED_COST_RATE
        net = gross - estimated_cost
        tax_reserve = max(net, Decimal("0")) * ESTIMATED_TAX_RATE
        rows.append({
            "symbol": symbol,
            "sell_time_utc": when.astimezone(timezone.utc).isoformat(),
            "quantity": str(matched),
            "sell_proceeds_usd": money(proceeds),
            "fifo_cost_basis_usd": money(basis),
            "gross_realized_pnl_usd": money(gross),
            "estimated_trading_cost_usd": money(estimated_cost),
            "estimated_net_pnl_usd": money(net),
            "illustrative_tax_reserve_usd": money(tax_reserve),
            "notes": "Estimate only; FIFO within retrieved orders; no wash-sale adjustments",
        })

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} estimated realized P&L rows to {OUTPUT}.")
    if len(orders) >= MAX_ORDERS:
        print("WARNING: Order query reached limit; older fills may be missing.")
    if unmatched_sells:
        print(f"WARNING: {unmatched_sells} sell orders lacked complete purchase history.")
    print("Report is illustrative only: not an official tax document or reliable "
          "full-history P&L calculation. Verify with broker statements and tax records.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"REPORT ERROR: {exc}", file=sys.stderr)
        raise
