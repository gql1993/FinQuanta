---
name: event-fund-tracking-rules
description: Applies event-driven and fund-holding tracking rules. Use when reviewing or changing event matching, board mapping, announcement/news catalysts, fund holding changes,增持/新进 filters, disclosure timing, or arena event/fund_tracking strategy rules.
---

# Event And Fund Tracking Rules

## Copyright Boundary

Do not copy paid research or proprietary datasets. Use principle-level rules: catalyst must map to beneficiaries, price/volume confirms the event, and fund tracking must use real holding context when available.

## Event-Driven Workflow

1. Require an event context: stored event, news item, or matched board.
2. Map the event to beneficiary boards/stocks.
3. Confirm price/volume reaction; avoid buying unexplained one-day spikes.
4. Limit holding period; event trades should not become accidental long-term positions.
5. Exit on failed reaction, MA break, event decay, or max holding days.

## Fund Tracking Workflow

1. Require fund holding data when the strategy claims fund tracking.
2. Prefer new entrants or increased holdings over stale heavy holdings.
3. Require enough funds to reduce single-manager noise.
4. Confirm stock trend/RS after disclosure.
5. Exit when trend fails, fund context weakens, or disclosure effect decays.

## Repository Expectations

- `desktop/event_strategy.py` contains event-to-board matching and recommendation helpers.
- `desktop/fund_strategy.py` contains fund holdings and period comparison logic.
- `desktop/arena/strategy_signals.py` should load context from `events`, `board_stocks`, and `fund_holdings`.
- `strategy_profiles.py` should block event/fund buys when required context is absent.
- Tests should cover missing-context blocks, matched-context passes, max hold exits, and reduced/退出 fund blocks.
