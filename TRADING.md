# Trading team

Two automated teams share one idea: **risk control first, stock picking second.** No strategy wins every trade. The goal is small losses, bigger wins, and no single trade that can hurt the account.

| | Day-trading bot (Alpaca) | Swing team (Webull) |
|---|---|---|
| Runs | Every 5 min in market hours (GitHub Actions) | 10:20 and 15:20 ET on weekdays (Claude Routine) |
| Places orders | Fully automatically | Proposes; **you tap confirm** in the Webull app |
| Style | Opening-range breakout, flat by 15:45 ET | Trend and momentum, held for days to weeks |
| Budget | $1,000 (`BUDGET`) | $1,000 of the Individual Margin account |
| Stop-loss | Real stop order at the broker on every trade | Checked twice a day, sold at the bid if hit |

## Day-trading bot: how it decides

- **Analyst** (`trading_team/analyst.py`) watches a list of about 36 liquid large caps and ETFs. It never trades penny stocks. A stock qualifies only when all of these hold:
  - SPY is above its VWAP (a healthy market).
  - The stock breaks above its first-15-minute high.
  - It trades above its own VWAP and is green on the day.
  - Its volume is at least 1.5× normal.
  - It hasn't already run more than 1.5% past the breakout, so the bot never chases.
- **Risk manager** (`trading_team/risk.py`) can veto any trade:
  - Risks 1% of the budget per trade (**$10**).
  - Caps any one position at 40% of the budget, holds at most 2 positions, and makes at most 3 trades per day.
  - Stops trading for the day after losing **3% ($30)**.
  - Takes new entries only from 9:45 to 11:30 ET, and never re-enters a stock it already traded that day.
- **Trader** (`trading_team/broker.py`) buys with a *bracket order*: every entry carries a stop-loss (below the opening range) and a take-profit (2× the risk) at the broker. The protection keeps working even if GitHub runs late. After 15:45 ET it sells everything.

Each run's decisions show up in the **Actions** tab, in each run's summary.

## Set it up (about 10 minutes)

1. Create a free account at [alpaca.markets](https://alpaca.markets). Open the **Paper** dashboard, generate API keys, and save them as repository secrets (*Settings → Secrets and variables → Actions*): `ALPACA_PAPER_KEY_ID` and `ALPACA_PAPER_SECRET_KEY`.
2. Merge this branch into `main`. GitHub only runs scheduled workflows from the default branch.
3. Let it paper trade for **at least 2 weeks**, and check the daily report in the Actions tab.
4. To go live: fund an Alpaca live account and add `ALPACA_LIVE_KEY_ID` and `ALPACA_LIVE_SECRET_KEY`. Then set the repository **variable** `ALPACA_LIVE` = `true`. Use an account dedicated to the bot, because the bot's "sell everything at 15:45" rule applies to the whole account.

**Controls** (repository variables):
- `TRADING_ENABLED=false` means analyse and log only.
- `BUDGET` sets the dollar amount the bot may use.
- **Panic button:** Actions → *Trading team* → *Run workflow* → `flatten`.

Pattern-day-trader rule: accounts under $25k are blocked after 3 day trades in 5 days. The bot respects that limit (`RESPECT_PDT`).

## Swing team (Webull)

`webull/PLAYBOOK.md` holds the exact rules the scheduled Claude session follows. It tracks its own positions on a Webull watchlist called **Trading Team** and never touches your other holdings. On Mondays it only writes hold/trim/sell recommendations for them. Webull's connector can't send orders without your confirmation, so confirm or ignore each instruction in the app.

## Tests

```
pip install -r requirements.txt && python -m pytest -q
```
