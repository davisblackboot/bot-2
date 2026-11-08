"""Paper-only long-only intraday ETF momentum experiment.
No profitability guarantee. Re-evaluates each run; broker holds persistent state.
"""
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, ClosePositionRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
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
    key = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET_KEY"]
    broker = TradingClient(key, secret, paper=True)
    data = StockHistoricalDataClient(key, secret)
    clock = broker.get_clock()
    now = datetime.now(NY)
    if not clock.is_open:
        print("Market closed; no action.")
        return
    acct = broker.get_account()
    equity = float(acct.equity)
    last_equity = float(acct.last_equity)
    if last_equity > 0 and equity <= last_equity * (1 - MAX_DAILY_DRAWDOWN):
        print("Daily equity loss limit reached; no new entries.")
        return
    positions = {p.symbol: p for p in broker.get_all_positions()}
    position = positions.get(SYMBOL)
    if position:
        entry = float(position.avg_entry_price)
        price = float(position.current_price)
        if price <= entry * (1 - STOP_PCT) or price >= entry * (1 + TAKE_PCT) or (now.hour == 15 and now.minute >= 45):
            broker.close_position(SYMBOL)
            print("Position close submitted.")
        else:
            print("Holding position.")
        return
    if not (now.hour >= 10 and (now.hour < 15 or (now.hour == 15 and now.minute < 30))):
        print("Outside entry window.")
        return
    # Do not enter again if today's order history already includes a buy.
    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    orders = broker.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.ALL, after=start_day, limit=500))
    if any(o.symbol == SYMBOL and o.side == OrderSide.BUY for o in orders):
        print("Already attempted entry today.")
        return
    end = datetime.now(timezone.utc) - timedelta(minutes=2)
    start = end - timedelta(days=8)
bars = data.get_stock_bars(
    StockBarsRequest(
        symbol_or_symbols=SYMBOL,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=DataFeed.IEX
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
    # EMA cross + trend filter; cross uses completed minute bars only.
    fast = close.ewm(span=9, adjust=False).mean()
    slow = close.ewm(span=21, adjust=False).mean()
    trend = close.ewm(span=200, adjust=False).mean()
    signal = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1] and close.iloc[-1] > trend.iloc[-1]
    if not signal:
        print("No qualifying EMA entry signal.")
        return
    amount = round(min(equity * MAX_ALLOCATION, float(acct.cash)), 2)
    if amount < MIN_ORDER:
        print("Insufficient buying power.")
        return
    order = MarketOrderRequest(symbol=SYMBOL, notional=amount, side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
    result = broker.submit_order(order_data=order)
    print(f"Paper buy submitted: {result.id}, notional ${amount:.2f}")

if __name__ == "__main__":
    main()
