"""Paper-only long-only intraday SPY momentum experiment.

Runs once per GitHub Actions invocation. No profitability guarantee.
Software exits depend on GitHub actually running and are NOT protective stop orders.
"""
import os
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

SYMBOL = "SPY"
NY = ZoneInfo("America/New_York")
MAX_ALLOCATION = 0.25
MAX_DAILY_DRAWDOWN = 0.02
STOP_PCT = 0.007
TAKE_PCT = 0.012
MIN_ORDER = 1.00


def main():
    if os.getenv("PAPER_ONLY", "true").lower() != "true":
        raise RuntimeError("Safety lock: this bot is paper-only.")

    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]
    broker = TradingClient(key, secret, paper=True)
    data = StockHistoricalDataClient(key, secret)
    now = datetime.now(NY)

    if not broker.get_clock().is_open:
        print("Market closed; no action.")
        return

    acct = broker.get_account()
    if acct.trading_blocked or acct.account_blocked:
        print("Account trading blocked; no orders.")
        return

    equity = float(acct.equity)
    last_equity = float(acct.last_equity)
    drawdown_hit = last_equity > 0 and equity <= last_equity * (1 - MAX_DAILY_DRAWDOWN)

    # Check existing orders before submitting another buy or sell.
    open_orders = broker.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500))
    if any(o.symbol == SYMBOL for o in open_orders):
        print("SPY order already pending; no duplicate order.")
        return

    positions = {p.symbol: p for p in broker.get_all_positions()}
    if any(symbol != SYMBOL for symbol in positions):
        print("Other positions detected; no new orders.")
        return

    position = positions.get(SYMBOL)
    if position:
        entry = float(position.avg_entry_price)
        price = float(position.current_price)
        if (drawdown_hit or price <= entry * (1 - STOP_PCT)
                or price >= entry * (1 + TAKE_PCT)
                or now.time() >= time(15, 45)):
            broker.close_position(SYMBOL)
            print("Paper position close submitted.")
        else:
            print("Holding paper position.")
        return

    if drawdown_hit:
        print("Daily equity loss limit reached; no new entries.")
        return

    # Do not open new positions late in the session.
    if not (time(10, 0) <= now.time() < time(15, 30)):
        print("Outside entry window.")
        return

    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    orders = broker.get_orders(filter=GetOrdersRequest(
        status=QueryOrderStatus.ALL, after=start_day, limit=500
    ))
    if any(o.symbol == SYMBOL and o.side == OrderSide.BUY for o in orders):
        print("Already attempted SPY entry today.")
        return

    end = datetime.now(timezone.utc) - timedelta(minutes=2)
    start = end - timedelta(days=8)
    bars = data.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=SYMBOL,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )
    ).df

    if bars.empty:
        print("No market data.")
        return
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(SYMBOL, level="symbol")
    bars = bars.sort_index()
    close = bars["close"].astype(float)
    if len(close) < 210:
        print("Insufficient bars.")
        return

    # 9/21 EMA crossover with a 200 EMA trend filter.
    fast = close.ewm(span=9, adjust=False).mean()
    slow = close.ewm(span=21, adjust=False).mean()
    trend = close.ewm(span=200, adjust=False).mean()
    signal = (fast.iloc[-2] <= slow.iloc[-2]
              and fast.iloc[-1] > slow.iloc[-1]
              and close.iloc[-1] > trend.iloc[-1])
    if not signal:
        print("No qualifying EMA entry signal.")
        return

    # Use available cash, not margin buying power.
    amount = round(min(equity * MAX_ALLOCATION, float(acct.cash) * 0.95), 2)
    if amount < MIN_ORDER:
        print("Insufficient available cash.")
        return

    order = MarketOrderRequest(
        symbol=SYMBOL,
        notional=amount,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )
    result = broker.submit_order(order_data=order)
    print(f"Paper buy submitted: {result.id}, notional ${amount:.2f}")


if __name__ == "__main__":
    main()
