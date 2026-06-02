---
name: value-quality-rules
description: Applies value, quality, and GARP rules for Graham, Buffett, Lynch, Danbin, Linyuan, Qiuguolu, and related strategies. Use when reviewing or changing valuation filters, margin of safety, quality trend, growth-at-reasonable-price, defensive trend guards, or arena value strategy rules.
---

# Value Quality Rules

## Copyright Boundary

Do not copy book text or investor letters. Use principle-based summaries: valuation discipline, business quality, growth at a reasonable price, margin of safety, and long holding discipline.

## Review Workflow

1. Identify whether the strategy is deep value, GARP, or quality compounder.
2. Check required fundamentals; if missing, use explicit degraded-data fallback or block.
3. Check valuation against strategy-specific caps and safety margin.
4. Check quality/growth proxy only when real fundamentals are unavailable.
5. Check trend guard only as risk control, not as the sole thesis.
6. Define sell triggers: thesis deterioration, overvaluation, safety margin loss, or major trend break.

## Strategy-Specific Checks

### Graham

- Require a clear margin of safety.
- Prefer cheap valuation and balance-sheet conservatism when data exists.
- Sell when safety margin disappears or risk protection fails.

### Buffett / Quality Compounder

- Prefer durable quality proxies, steady trend, and reasonable valuation.
- Avoid selling solely on normal volatility; sell on quality trend break or extreme overvaluation.

### Lynch / GARP

- Require growth proxy plus valuation that is not excessive.
- Sell when growth fades, valuation becomes excessive, or long-term risk guard fails.

### Domestic Private/Institutional Value

- Danbin: long-term quality/sector momentum and crowding control.
- Linyuan: defensive consumption/healthcare-style proxy and resilient trend.
- Qiuguolu: safety margin plus low crowding and improving fundamentals proxy.

## Repository Expectations

- `strategy_profiles.py` should keep valuation, heat, crowding, and trend proxy rules explicit.
- `desktop/arena/strategy_signals.py` should load available financial context.
- Tests should cover margin pass/fail, overvaluation exit, growth fade, and missing data behavior.
