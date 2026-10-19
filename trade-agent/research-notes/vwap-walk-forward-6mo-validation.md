# VWAP Mean-Reversion — Walk-Forward Validation, 5-Month Sample

**Date run:** 2026-10-16
**Data:** real SPY 5-min RTH bars, extended via 4 more paginated Webull pulls → **8,400 bars across 109 trading days (Apr 25 – Sep 30, 2025)**, up from the prior 47-day sample. Train = first 70 days (Apr 25 – Aug 5), test = last 39 days (Aug 6 – Sep 30), split chronologically, no leakage.

## Result: same conclusion as the 47-day run, now on firmer footing

11 of 12 grid combos are negative-to-flat Sharpe on train. One combo — `entry_z=2.0, exit_z=0.0` — showed **+0.69 Sharpe / +0.86% return** in-sample (57 trades). Applied unchanged to the out-of-sample test window: **-1.48 Sharpe / -0.74% return**. The untuned default (1.5/0.2) was negative on both sides, same as before (-0.85 train, -2.82 test).

**This is the overfitting trap working exactly as expected, not a reason to keep searching.** With 12 combos tested, finding one with a positive in-sample Sharpe by chance is unsurprising — and its failure to survive the out-of-sample test is the evidence that it was chance, not edge. Doubling the data didn't change the verdict; it just made one pre-existing false positive visible and then falsified it properly.

## Where this leaves VWAP mean-reversion
Across two independent data windows (47 days and 109 days) and 24 total parameter combinations tested, nothing has survived out-of-sample validation. This is now a reasonably solid negative result, not an artifact of a short sample — continuing to grid-search this same signal shape on SPY 5-min bars is very unlikely to find something real; it's more likely to just produce another false positive to chase.

## Recommendation
Stop iterating on this specific signal. The honest options from here:
1. **Try a structurally different strategy** (cross-sectional relative strength, overnight gap, event-driven, multi-day swing) rather than another intraday mean-reversion variant on the same instrument.
2. **Try a different instrument** — SPY is heavily arbitraged/efficient; a smaller, less liquid name may have more exploitable microstructure for the same style of signal.
3. **Accept that "no edge found yet" is itself the useful output of this round** and redirect effort to risk management / portfolio construction with known factors (indexing, systematic risk premia) rather than searching for intraday alpha that may not be there for a retail-accessible timeframe.

## Files
- `/home/claude/trade-agent/data/SPY_M5_6mo.csv` — merged 109-day dataset (8,400 bars)
- `/home/claude/trade-agent/run_walk_forward_6mo.py`
