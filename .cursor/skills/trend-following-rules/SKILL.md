---
name: trend-following-rules
description: Applies trend-following rules for Turtle, Covell, Dow Theory, and other systematic trend strategies. Use when reviewing or changing Donchian breakouts, long-term moving-average trend filters, ATR risk units, trailing exits, or arena trend-following strategy rules.
---

# Trend Following Rules

## Copyright Boundary

Do not quote proprietary book text. Use public, principle-level trend-following rules: trade breakouts, size by risk, cut losers, and ride major trends.

## Review Workflow

1. Define the trend universe and long-only or long/short stance.
2. Define entry trigger: Donchian breakout, long-term high, or confirmed primary trend.
3. Define trend filter: long moving average, rising average, or Dow structure.
4. Define risk unit: ATR or entry-to-stop distance.
5. Define exit trigger before entry: trailing low, moving-average break, or structure failure.
6. Keep exits systematic; do not add discretionary rescue logic.

## Strategy-Specific Checks

### Turtle

- Use separate breakout systems rather than requiring all breakouts at once.
- Use ATR/N for position sizing and stop distance when execution supports it.
- Exit on shorter Donchian low or system-specific trailing stop.

### Covell Trend Following

- Prefer long-term breakout plus price above a rising long moving average.
- Avoid entries when volatility is excessive relative to price.
- Exit on trend failure, not valuation or opinions.

### Dow Theory

- Require primary trend confirmation: moving-average structure plus higher highs and higher lows.
- Exit when structure breaks, lower lows appear, or intermediate trend fails.

## Repository Expectations

- `strategy_profiles.py` should store deterministic vector rules.
- `desktop/arena/strategy_signals.py` should add only position-aware overlays.
- Tests should cover breakout pass, trend-filter block, ATR/volatility block, and trailing exit.
