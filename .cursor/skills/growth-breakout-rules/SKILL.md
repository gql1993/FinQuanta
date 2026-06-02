---
name: growth-breakout-rules
description: Applies growth breakout trading rules for CAN SLIM, Livermore, Larry Williams, and related momentum breakout strategies. Use when reviewing or changing growth breakout stock selection, volume breakouts, RS leadership, pivot entries, stop losses, or arena strategy rules.
---

# Growth Breakout Rules

## Copyright Boundary

Do not copy or quote book text. Use principle-based checklists distilled from public descriptions of growth breakout, CAN SLIM, Livermore key-point, and short-term momentum systems.

## Review Workflow

When reviewing or implementing a growth breakout strategy:

1. Confirm the market and stock trend are constructive.
2. Confirm leadership: high RS, near highs, and clear relative strength.
3. Confirm the setup: base, key point, short consolidation, or volatility contraction.
4. Confirm breakout quality: price clears the trigger with volume expansion.
5. Confirm risk before entry: stop, maximum loss, and position size.
6. Confirm post-entry behavior: quick progress, failed breakout, and tight loss control.
7. Confirm exits: hard stop, key point failure, moving average break, climax, or time stop.

## Strategy-Specific Checks

### CAN SLIM

- C/A: use real fundamentals when available; otherwise use explicit momentum proxy.
- N/S/L: prefer new-high proximity, supply/demand volume, and RS leadership.
- M: require market/stage trend or explicit degraded-data fallback.
- Reject weak-volume breakouts, mediocre RS, late/extended entries, or bases that are too deep.
- Use a tight max loss, commonly around 7-8%.

### Livermore

- Focus on key-point or pivot breakout, not random strength.
- Require trend direction and volume confirmation.
- Exit quickly if the key point fails or the stock violates the chosen trend line.
- Avoid buying far above the trigger.

### Larry Williams Short-Term Breakout

- Prefer short-term volatility contraction followed by a decisive breakout.
- Require volume expansion and short-term strength.
- Hold briefly; exit on failed breakout, short moving-average break, or time stop.

## Repository Expectations

- `strategy_profiles.py` owns the vector buy/exit rules and default parameters.
- `desktop/arena/strategy_signals.py` owns position-aware overlays such as max hold days and stop loss.
- Tests should cover pass/block cases for RS, volume, extension, failed breakout, and time stop.
