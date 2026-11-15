"""
Alpaca PAPER account: estimated realized P&L report from recent filled orders.

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


# ==========================================
# REPORT SETTINGS
# ==========================================

OUTPUT = "report.csv"

LOOKBACK_DAYS = 30

MAX_ORDERS = 500

# User-adjustable rough estimates.
# These are NOT actual broker charges or tax liabilities.

ESTIMATED_COST_RATE = Decimal(
    os.getenv("ESTIMATED_COST_RATE", "0.001")
)

ESTIMATED_TAX_RATE = Decimal(
    os.getenv("ESTIMATED_TAX_RATE", "0.20")
)


# ==========================================
# CSV REPORT COLUMNS
# ==========================================

COLUMNS = [
    "symbol",
    "sell_time_utc",
    "quantity",
    "sell_proceeds_usd",
    "fifo_cost_basis_usd",
    "gross_realized_pnl_usd",
    "estimated_trading_cost_usd",
    "estimated_net_pnl_usd",
    "illustrative_tax_reserve_usd",
    "notes",
]


# ==========================================
# MONEY FORMATTING
# ==========================================

def money(value):

    return f"{value.quantize(Decimal('0.01')):.2f}"


# ==========================================
# MAIN REPORT FUNCTION
# ==========================================

def main():

    print("Starting Alpaca paper trading report...")

    # --------------------------------------
    # PAPER TRADING SAFETY CHECK
    # --------------------------------------

    if os.getenv("PAPER_ONLY", "true").lower() != "true":

        raise RuntimeError(
            "Safety lock: report supports paper trading only."
        )

    # --------------------------------------
    # API CREDENTIALS
    # --------------------------------------

    key = os.getenv("ALPACA_API_KEY")

    secret = os.getenv("ALPACA_SECRET_KEY")

    if not key or not secret:

        raise RuntimeError(
            "Missing ALPACA_API_KEY or ALPACA_SECRET_KEY GitHub secret."
        )

    # --------------------------------------
    # VALIDATE ESTIMATED RATES
    # --------------------------------------

    if ESTIMATED_COST_RATE < 0 or ESTIMATED_TAX_RATE < 0:

        raise ValueError(
            "Estimated rates cannot be negative."
        )

    # --------------------------------------
    # CONNECT TO ALPACA PAPER ACCOUNT
    # --------------------------------------

    trading = TradingClient(
        key,
        secret,
        paper=True
    )

    # --------------------------------------
    # GET RECENT ORDERS
    # --------------------------------------

    since = datetime.now(timezone.utc) - timedelta(
        days=LOOKBACK_DAYS
    )

    orders = trading.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            after=since,
            limit=MAX_ORDERS
        )
    )

    fills = []

    for order in orders:

        qty = getattr(
            order,
            "filled_qty",
            None
        )

        price = getattr(
            order,
            "filled_avg_price",
            None
        )

        filled_at = getattr(
            order,
            "filled_at",
            None
        )

        if not qty or not price or not filled_at:
            continue

        qty = Decimal(str(qty))

        price = Decimal(str(price))

        if qty <= 0 or price <= 0:
            continue

        fills.append(
            (
                filled_at,
                str(order.symbol),
                order.side,
                qty,
                price
            )
        )

    # Sort completed orders by time
    fills.sort(
        key=lambda row: row[0]
    )

    # --------------------------------------
    # TRACK BUY AND SELL TRANSACTIONS
    # --------------------------------------

    lots = defaultdict(deque)

    rows = []

    unmatched_sells = 0

    for when, symbol, side, qty, price in fills:

        # ----------------------------------
        # BUY ORDERS
        # ----------------------------------

        if side == OrderSide.BUY:

            lots[symbol].append(
                [qty, price]
            )

            continue

        # ----------------------------------
        # SELL ORDERS
        # ----------------------------------

        if side != OrderSide.SELL:
            continue

        remaining = qty

        matched = Decimal("0")

        basis = Decimal("0")

        # Match sells against previous buys
        # using FIFO accounting.

        while remaining > 0 and lots[symbol]:

            lot_qty, buy_price = lots[symbol][0]

            used = min(
                remaining,
                lot_qty
            )

            basis += used * buy_price

            matched += used

            remaining -= used

            lots[symbol][0][0] -= used

            if lots[symbol][0][0] == 0:

                lots[symbol].popleft()

        # ----------------------------------
        # MISSING COST BASIS
        # ----------------------------------

        if remaining > 0:

            unmatched_sells += 1

            print(
                f"WARNING: {symbol} sell has "
                f"{remaining} shares with unknown cost basis. "
                "Excluded that portion from estimated P&L."
            )

        if matched <= 0:
            continue

        # ----------------------------------
        # CALCULATE PROFIT AND LOSS
        # ----------------------------------

        proceeds = matched * price

        gross = proceeds - basis

        # Estimated spread/slippage/fees.
        # These are approximations, not actual
        # broker charges. Some costs may already
        # be reflected in executed prices.

        estimated_cost = (
            basis + proceeds
        ) * ESTIMATED_COST_RATE

        net = gross - estimated_cost

        # Illustrative tax reserve only.

        tax_reserve = max(
            net,
            Decimal("0")
        ) * ESTIMATED_TAX_RATE

        # ----------------------------------
        # ADD COMPLETED TRADE TO REPORT
        # ----------------------------------

        rows.append(
            {
                "symbol": symbol,

                "sell_time_utc": (
                    when.astimezone(
                        timezone.utc
                    ).isoformat()
                ),

                "quantity": str(matched),

                "sell_proceeds_usd": money(proceeds),

                "fifo_cost_basis_usd": money(basis),

                "gross_realized_pnl_usd": money(gross),

                "estimated_trading_cost_usd": money(
                    estimated_cost
                ),

                "estimated_net_pnl_usd": money(net),

                "illustrative_tax_reserve_usd": money(
                    tax_reserve
                ),

                "notes": (
                    "Estimate only; FIFO within retrieved orders; "
                    "no wash-sale adjustments"
                ),
            }
        )

    # ======================================
    # GENERATE CSV REPORT
    # ======================================

    with open(
        OUTPUT,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=COLUMNS
        )

        writer.writeheader()

        writer.writerows(rows)

    # ======================================
    # REPORT SUMMARY
    # ======================================

    print(
        f"Wrote {len(rows)} estimated realized "
        f"P&L rows to {OUTPUT}."
    )

    if len(orders) >= MAX_ORDERS:

        print(
            "WARNING: Order query reached limit; "
            "older fills may be missing."
        )

    if unmatched_sells:

        print(
            f"WARNING: {unmatched_sells} sell orders "
            "lacked complete purchase history."
        )

    print(
        "Report is illustrative only: not an official "
        "tax document or reliable full-history P&L "
        "calculation. Verify with broker statements "
        "and tax records."
    )


# ==========================================
# START REPORT
# ==========================================

if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        print(
            f"REPORT ERROR: {exc}",
            file=sys.stderr
        )

        raise
