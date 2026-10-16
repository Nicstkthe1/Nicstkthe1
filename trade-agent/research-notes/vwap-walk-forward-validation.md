# VWAP Mean-Reversion — Walk-Forward Validation (Train/Test Split)

**Date run:** 2026-10-16
**Data:** same 47-day real SPY 5-min dataset (`SPY_M5_full.csv`), split chronologically — no shuffling, so no leakage: train = first 30 days (Jul 25 – Sep 5), test = last 17 days (Sep 8 – Sep 30).

## Method
1. Grid-searched `entry_z` ∈ {1.0, 1.5, 2.0, 2.5} × `exit_z` ∈ {0.0, 0.2, 0.5} — 12 combos — **on the TRAIN window only**.
2. Picked the best-Sharpe combo from train, then ran that exact, untouched parameter set on the TEST window to see if it held up out-of-sample.

## Result: it doesn't hold up, but more importantly — nothing in the grid worked

Every one of the 12 train-window combos had **negative Sharpe** (range: -2.32 to -4.54). The "best" one (entry_z=1.5, exit_z=0.0) was just the least-bad, at -2.32 Sharpe / -1.16% return on train. Run out-of-sample on test: Sharpe dropped further to -4.44 (-1.05% return). The untuned default (1.5/0.2) was similarly negative on both sides (-3.15 train, -5.22 test).

**This is the right outcome to see, even though it's a "no."** There's no cherry-picking here — the full grid lost money in-sample, so there was nothing promising to even validate out-of-sample. A strategy search that returns "everything was bad" is doing its job; the risk would have been finding one lucky combo in 12 and mistaking it for an edge.

## What this means for the plan going forward
- **VWAP mean-reversion, as specified (z-score vs. intraday VWAP, this entry/exit/vol-filter logic), has no demonstrated edge on SPY 5-min bars in this 3-month window.** Not "needs more tuning" — the tuning step is what revealed this.
- Don't keep turning knobs on this same signal shape; that path leads to overfitting on 47 days of data, not to a real edge.
- Options are off the table for now per your steer — and this result reinforces why: there was nothing here to amplify.

## Honest next steps (pick a different lever, not more tuning)
1. **Different signal family entirely** — e.g., cross-sectional (relative strength between correlated tickers), a slower multi-day regime filter, or earnings/event-driven setups — rather than another intraday mean-reversion variant.
2. **More/different underlyings** — test the same VWAP logic on a higher-beta or less efficient name (a single stock rather than SPY) where retail order flow creates more exploitable short-term dislocations.
3. **Longer history** — 47 days covers one summer regime; pulling 6-12 months (more paginated batches) would show whether this is regime-specific or just doesn't work, period.

## Files
- `/home/claude/trade-agent/run_walk_forward.py` — the train/test grid search script
