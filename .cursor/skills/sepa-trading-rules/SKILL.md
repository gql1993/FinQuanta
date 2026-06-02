---
name: sepa-trading-rules
description: Applies Mark Minervini SEPA-style trading rules to stock selection, entry timing, position management, and exits. Use when reviewing or changing arena_sepa, SEPA, VCP, trend template, distribution-day filters, pivot breakouts, stop losses, or Minervini/股票魔法师 rules.
---

# SEPA Trading Rules

## Copyright Boundary

Do not copy or quote book text. Use this skill as a principle-based checklist distilled from the SEPA method: trend, fundamentals, leadership, institutional demand, precise entry, strict risk, and sell discipline.

## Review Workflow

When reviewing or implementing SEPA:

1. Check market environment before individual stock rules.
2. Check Stage 2 trend template and leadership.
3. Check base quality and VCP contraction.
4. Check the exact pivot breakout and volume confirmation.
5. Check risk before entry: stop, position size, and invalidation.
6. Check post-entry management: progress, failed breakout, partial profit, fast-gainer exception.
7. Check exits by priority: hard stop, failed breakout, Stage 3/4, climax top, time stop, trailing stop.

## Market Preconditions

SEPA buys should be blocked when:

- The benchmark is in correction by distribution-day rules.
- The benchmark is not in a constructive Stage 2 uptrend.
- Broad leadership is absent or deteriorating.

Allow missing market data only as an explicit degraded-data fallback; surface the fallback in diagnostics.

## Stock Selection

Minimum technical filters:

- Price above 150-day and 200-day moving averages.
- 150-day moving average above 200-day moving average.
- 200-day moving average rising.
- 50-day moving average above both 150-day and 200-day moving averages.
- Price above 50-day moving average.
- Price meaningfully above 52-week low.
- Price near 52-week high.
- Relative strength high enough to show leadership.
- Average liquidity high enough to enter and exit without excessive slippage.

Prefer candidates with:

- Strong RS versus the market and peers.
- Clean base after a prior advance.
- Tight closes and volatility contraction.
- Volume drying up during contraction.
- Demand returning on breakout.
- Fundamental or catalyst support when available; if data is absent, mark this as an explicit data gap rather than pretending it passed.

## Entry Rules

A valid SEPA buy requires:

- Market environment OK.
- Stage 2 trend template passed.
- VCP or similarly constructive base detected.
- Buy as close as practical to the pivot; avoid extended entries.
- Entry should be near the pivot, commonly within a small configurable band such as 0-5%.
- Breakout confirmed by volume expansion.
- Initial stop known before buying, usually near 7-8% maximum risk or a tighter logical stop when available.
- Position size should be derived from entry-to-stop risk when the execution layer supports sizing.

Reject entries when:

- Breakout is extended far above pivot.
- Volume is weak on breakout.
- Volume did not contract during the base.
- RS is mediocre.
- Base is too loose, obvious, late-stage, or failed recently.
- Risk/reward to stop is unattractive.
- Average volume/liquidity is too low.

## Holding Rules

After entry:

- If breakout fails quickly, exit without negotiation.
- If gain is fast and substantial early, allow the fast-gainer/8-week style exception to avoid selling a potential leader too soon.
- If profit develops normally, progressively reduce risk.
- After partial profit, trail using moving averages or logical support.
- Keep winners while Stage 2 behavior remains intact.

## Exit Priority

Evaluate exits in this order:

1. Hard stop or failed breakout.
2. Climax top or exhaustion behavior after an extended advance.
3. Stage 3/4 transition or major moving-average structure break.
4. Excessive drawdown from peak.
5. Partial profit where appropriate.
6. Trailing stop after partial profit.
7. Time stop when the stock does not make progress.

## Implementation Expectations

For this repository:

- `desktop/arena/sepa_rules.py` is the arena SEPA entry/exit adapter.
- `desktop/arena/market_regime.py` owns distribution-day and index Stage checks.
- `risk_manager.py` owns post-entry SEPA exit discipline.
- `trend_template.py` owns Stage 2 trend template.
- `vcp_detector.py` owns VCP and pivot breakout detection.
- `strategy_profiles.py` owns user-tunable defaults such as RS floor, breakout volume, pivot extension, and liquidity thresholds.
- Tests should cover both pass and block cases: market blocked, weak volume, weak RS, low liquidity, no trend template, no VCP volume contraction, extended pivot entry, failed breakout, hard stop, and fast-gainer behavior.

