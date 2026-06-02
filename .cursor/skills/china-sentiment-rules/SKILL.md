---
name: china-sentiment-rules
description: Applies China A-share sentiment and hot-money style rules for Yangjia, Zhao Laoge, Asking, and emotion trading. Use when reviewing or changing market sentiment, profit effect, leader relay, divergence-to-consensus, board strength, overheating filters, or arena A-share short-term rules.
---

# China Sentiment Rules

## Copyright Boundary

Do not copy private course material or trader quotes. Use public, principle-level A-share short-term concepts: emotion cycle, leader stocks, board effect, profit effect, divergence-to-consensus, and fast loss cutting.

## Review Workflow

1. Identify the current sentiment phase: ice point, start, fermentation, climax, ebb.
2. Confirm board or market-wide profit effect when data exists.
3. Prefer leaders: near highs, high RS, strong board, and visible volume.
4. Buy only during constructive phases; avoid late climax unless explicitly allowed.
5. Avoid overheated moves after excessive short-term gains.
6. Exit quickly on ebb, leader failure, MA break, or loss of profit effect.

## Strategy-Specific Checks

### Yangjia

- Buy divergence-to-consensus, not random breakouts.
- Require volume agreement, profit effect, and non-climax phase.
- Exit when consensus turns into divergence or sentiment ebbs.

### Zhao Laoge

- Focus on leading stocks in the main rising leg.
- Require near-high leadership, strong inertia, and phase support.
- Exit when leader inertia fails.

### Asking

- Prefer main uptrend acceleration.
- Cut losses quickly and let strong winners continue while trend remains intact.
- Exit on short MA break or sentiment ebb.

### Generic Emotion

- Use market/board sentiment if available.
- If only single-stock proxy is available, label it as a proxy and keep thresholds conservative.

## Repository Expectations

- `strategy_profiles.py` should combine phase, profit effect, RS, volume, and overheating filters.
- Future work should replace single-stock proxies with market-wide涨跌家数,连板高度,炸板率 when data is available.
- Tests should cover constructive phase, overheat block, ebb exit, and volume/RS gates.
