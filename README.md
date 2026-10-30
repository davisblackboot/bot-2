# $100 Alpaca + GitHub Actions paper bot

**Paper trading only.** No strategy guarantees profit or daily fills. This bot checks every five minutes on weekdays, trades SPY fractional shares long-only, and aims for at most one entry attempt per day.

## Setup
1. Create a **new GitHub repository** and upload the files from this ZIP, preserving `.github/workflows/trade.yml`.
2. In your Alpaca dashboard, copy your **paper** API key and secret (not live keys).
3. In GitHub: **Settings → Secrets and variables → Actions → New repository secret**. Add `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`.
4. Open **Actions → Alpaca $100 paper strategy → Run workflow** to test.
5. Set your Alpaca paper account equity to $100 if your dashboard allows resetting it; otherwise performance won't reflect a $100 account.
6. Review Actions logs, Alpaca orders, fills, and equity curve daily for at least 30–60 trading days before considering any live trading.

## Strategy and limitations
- 9/21 EMA bullish crossover on 1-minute SPY bars, above the 200 EMA; entry only 10:00–15:30 New York time.
- Max 25% of equity per entry; one attempted buy per day; checks for 0.7% stop or 1.2% target and exits after 15:45.
- Exits are **software-checked every five minutes, not broker-native protective stops**. Gaps, delayed runs, and slippage can cause larger losses. Position may remain open overnight if a run fails.
- 2% daily equity-loss gate prevents *new* entries only; it does not liquidate positions.
- GitHub Actions scheduled runs may be delayed or skipped, and do not guarantee exact execution times. Cron uses UTC; 14–20 UTC covers the 10:00–15:45 ET window in both US daylight and standard time, but triggers some unnecessary runs.
- Alpaca market-data entitlements and historical coverage can vary. Paper fills don't reproduce real slippage or liquidity perfectly.
- Fractional SPY market orders are notional DAY orders. Fees, spread, taxes, and realized P&L are not calculated in this sample.
- This is an experiment, not production-grade unattended trading software.
