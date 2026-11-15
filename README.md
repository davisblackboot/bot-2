# Alpaca paper-only SPY bot

This is a **paper-only** experiment, not a guaranteed profitable system. It uses SPY, a 9/21 EMA bullish crossover above EMA200, a 25% maximum allocation, and an entry window of 10:00–15:30 New York time. Existing positions are checked on each scheduled run and targeted for exit on stop/take thresholds or after 15:45 New York time.

**Important:** Stop-loss, take-profit, and end-of-day exits are **software checks**, not protective broker orders. GitHub Actions schedules can be delayed or skipped, leaving a position open. The 2% daily equity limit is a new-entry gate and an exit trigger when a run occurs, **not a guaranteed maximum loss**. Do not use with real money without further testing and safeguards.

## Upload to GitHub

1. Extract this ZIP on your computer.
2. Open your GitHub repository `davisblackboot/bot-2`.
3. Replace the existing root-level `bot.py`, `report.py`, `requirements.txt`, and `README.md` with the files from this ZIP. Add `.gitignore` if absent.
4. Preserve the **hidden** `.github/workflows/blank.yml` folder path. Replace the existing workflow file with the one in this ZIP. Do not upload the outer folder as an extra nested directory.
5. Commit the changes to `main`.
6. Under **Settings → Secrets and variables → Actions**, create repository secrets `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` using **paper** API credentials. Never commit credentials to source files.
7. Open **Actions → Paper intraday bot → Run workflow** and inspect the logs. Manual runs outside market hours will say market closed; that is normal.
8. Under the completed run, download the `paper-report-...` artifact for `report.csv`.

## Repository structure

```
bot.py
report.py
requirements.txt
README.md
.gitignore
.github/workflows/blank.yml
```

## How it works

- Uses Alpaca paper API (`paper=True`) and requires `PAPER_ONLY=true`.
- Uses free IEX minute bars; IEX data differs from consolidated market data.
- Checks for existing SPY orders and positions before opening new trades.
- Allows at most one SPY buy attempt per New York calendar day based on recent broker orders.
- Uses available cash and a maximum of 25% of equity; it does not request margin buying power.
- Runs roughly every five minutes on weekdays during a UTC window spanning US market hours; actual start times are not guaranteed.
- Reports FIFO estimates for recent filled orders only; the report does not include a complete ledger, accurate taxes, or guaranteed cost basis. It may show 0 rows until there are matched buys and sells.

## Troubleshooting

- `IndentationError` at line 1: replace the **entire** root `bot.py`; it must begin with a triple-quoted description.
- `can't open file report.py`: ensure `report.py` is in the repository root alongside `bot.py`.
- `Market closed`: run during regular US stock-market hours.
- `No qualifying EMA entry signal`: bot is functioning but no entry condition occurred; it may trade infrequently.
- Credentials errors: check that both repository secrets are set to Alpaca **paper** API credentials.
- The syntax-check step validates parsing, but **does not** test Alpaca API connectivity, trading results, or order execution.

## Costs and reports

The CSV uses illustrative trading-cost and tax-reserve assumptions; it is not an official tax report. GitHub Actions usage may be subject to account limits and billing. Paper results do not establish live profitability.
