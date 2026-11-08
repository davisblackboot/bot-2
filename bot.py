"""
Alpaca Automated Intraday Trading Bot
-------------------------------------
Paper trading ONLY.

Strategy:
- SPY ETF
- 9 EMA / 21 EMA bullish crossover
- 200 EMA trend confirmation
- Maximum 25% account allocation
- 0.7% stop-loss threshold
- 1.2% take-profit threshold
- 2% daily equity drawdown limit
- One entry attempt per day
- Automatic position monitoring

IMPORTANT:
This bot is experimental.
Profits are not guaranteed.
GitHub Actions does not guarantee exact execution times.
"""

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import (
    OrderSide,
    TimeInForce,
    QueryOrderStatus,
)

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed


# ==========================================
# SETTINGS
# ==========================================

SYMBOL = "SPY"

NY = ZoneInfo("America/New_York")

PAPER_ONLY = True

MAX_ALLOCATION = 0.25

MAX_DAILY_DRAWDOWN = 0.02

STOP_PCT = 0.007

TAKE_PCT = 0.012

MIN_ORDER = 1.00


# ==========================================
# MAIN BOT
# ==========================================

def main():

    print("Starting Alpaca paper trading bot...")

    # --------------------------------------
    # API CREDENTIALS
    # --------------------------------------

    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")

    if not key or not secret:
        raise RuntimeError(
            "Missing Alpaca API credentials. "
            "Check GitHub Actions secrets."
        )

    # Force paper trading
    broker = TradingClient(
        api_key=key,
        secret_key=secret,
        paper=True
    )

    data = StockHistoricalDataClient(
        api_key=key,
        secret_key=secret
    )

    # --------------------------------------
    # MARKET CLOCK
    # --------------------------------------

    clock = broker.get_clock()

    now = datetime.now(NY)

    print(f"Current New York time: {now}")

    if not clock.is_open:
        print("Market closed. No action.")
        return

    # --------------------------------------
    # ACCOUNT INFORMATION
    # --------------------------------------

    acct = broker.get_account()

    equity = float(acct.equity)

    last_equity = float(acct.last_equity)

    cash = float(acct.cash)

    print(f"Account equity: ${equity:.2f}")
    print(f"Available cash: ${cash:.2f}")

    # --------------------------------------
    # DAILY LOSS PROTECTION
    # --------------------------------------

    daily_loss_limit_reached = (
        last_equity > 0
        and equity <= last_equity * (1 - MAX_DAILY_DRAWDOWN)
    )

    # --------------------------------------
    # EXISTING POSITIONS
    # --------------------------------------

    positions = {
        position.symbol: position
        for position in broker.get_all_positions()
    }

    position = positions.get(SYMBOL)

    # --------------------------------------
    # MANAGE EXISTING POSITION
    # --------------------------------------

    if position:

        entry_price = float(position.avg_entry_price)

        current_price = float(position.current_price)

        stop_price = entry_price * (1 - STOP_PCT)

        take_price = entry_price * (1 + TAKE_PCT)

        print(f"Entry price: ${entry_price:.2f}")
        print(f"Current price: ${current_price:.2f}")

        print(f"Stop threshold: ${stop_price:.2f}")
        print(f"Take-profit threshold: ${take_price:.2f}")

        stop_hit = current_price <= stop_price

        take_hit = current_price >= take_price

        end_of_day = (
            now.hour > 15
            or (now.hour == 15 and now.minute >= 45)
        )

        if stop_hit or take_hit or end_of_day:

            # Avoid submitting duplicate closing orders
            open_orders = broker.get_orders(
                filter=GetOrdersRequest(
                    status=QueryOrderStatus.OPEN,
                    limit=500
                )
            )

            closing_order_exists = any(
                order.symbol == SYMBOL
                and order.side == OrderSide.SELL
                for order in open_orders
            )

            if closing_order_exists:
                print("Closing order already pending.")
                return

            broker.close_position(SYMBOL)

            print("Position close submitted.")

        else:

            print("Holding existing position.")

        return

    # --------------------------------------
    # DAILY LOSS LIMIT
    # --------------------------------------

    if daily_loss_limit_reached:

        print("Daily loss limit reached.")
        print("No new entries allowed.")

        return

    # --------------------------------------
    # ENTRY TIME WINDOW
    # --------------------------------------

    entry_allowed = (
        now.hour >= 10
        and (
            now.hour < 15
            or (now.hour == 15 and now.minute < 30)
        )
    )

    if not entry_allowed:

        print("Outside trading entry window.")

        return

    # --------------------------------------
    # PREVENT MULTIPLE ENTRIES
    # --------------------------------------

    start_day = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    orders = broker.get_orders(
        filter=GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            after=start_day,
            limit=500
        )
    )

    already_traded = any(
        order.symbol == SYMBOL
        and order.side == OrderSide.BUY
        for order in orders
    )

    if already_traded:

        print("Already attempted a trade today.")

        return

    # --------------------------------------
    # GET HISTORICAL MARKET DATA
    # --------------------------------------

    end = datetime.now(timezone.utc) - timedelta(minutes=2)

    start = end - timedelta(days=8)

    request = StockBarsRequest(
        symbol_or_symbols=SYMBOL,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=DataFeed.IEX
    )

    bars = data.get_stock_bars(request).df

    if bars.empty:

        print("No market data available.")

        return

    # Handle Alpaca multi-index format
    if isinstance(bars.index, pd.MultiIndex):

        bars = bars.xs(
            SYMBOL,
            level="symbol"
        )

    bars = bars.sort_index()

    close = bars["close"].astype(float)

    if len(close) < 210:

        print("Insufficient market data.")

        return

    # --------------------------------------
    # CALCULATE INDICATORS
    # --------------------------------------

    fast_ema = close.ewm(
        span=9,
        adjust=False
    ).mean()

    slow_ema = close.ewm(
        span=21,
        adjust=False
    ).mean()

    trend_ema = close.ewm(
        span=200,
        adjust=False
    ).mean()

    # --------------------------------------
    # BUY SIGNAL
    # --------------------------------------

    bullish_crossover = (
        fast_ema.iloc[-2] <= slow_ema.iloc[-2]
        and fast_ema.iloc[-1] > slow_ema.iloc[-1]
    )

    above_trend = (
        close.iloc[-1] > trend_ema.iloc[-1]
    )

    buy_signal = bullish_crossover and above_trend

    print(f"Bullish crossover: {bullish_crossover}")
    print(f"Above 200 EMA: {above_trend}")

    if not buy_signal:

        print("No qualifying EMA entry signal.")

        return

    # --------------------------------------
    # POSITION SIZE
    # --------------------------------------

    amount = round(
        min(
            equity * MAX_ALLOCATION,
            cash
        ),
        2
    )

    if amount < MIN_ORDER:

        print("Insufficient funds for minimum order.")

        return

    # --------------------------------------
    # SUBMIT PAPER BUY ORDER
    # --------------------------------------

    order = MarketOrderRequest(
        symbol=SYMBOL,
        notional=amount,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY
    )

    result = broker.submit_order(
        order_data=order
    )

    print("Paper buy order submitted.")

    print(f"Order ID: {result.id}")

    print(f"Investment amount: ${amount:.2f}")


# ==========================================
# START PROGRAM
# ==========================================

if __name__ == "__main__":

    main()
