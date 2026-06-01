# Five-Agent Research Framework

This document defines the paper-only five-agent architecture. It is a research
design artifact and must not be wired into production trading flows directly.

## Architecture Summary

The proposed framework uses LLM agents as a structured context and constraint
generation layer. Agents do not place trades and do not directly set final
portfolio weights.

Pipeline:

```text
Market data and factors
  -> strategy-family scores
  -> candidate stock pool
  -> five-agent LLM context layer
  -> portfolio constraints
  -> classical or quantum-inspired optimizer
  -> backtest and evaluation
```

## Agent 1: Market Regime Agent

Purpose:

Identify the current market state using structured market indicators.

Inputs:

- Index trend and moving-average structure.
- Market breadth.
- Volatility level.
- Liquidity and turnover change.
- Drawdown and rebound state.
- Benchmark-relative momentum.

Outputs:

- `market_state`: bull, bear, sideways, volatile_sideways, high_volatility, or
  liquidity_contraction.
- `risk_environment`: low, medium, high.
- `confidence`: 0 to 1.
- `evidence`: short structured rationale.

Current MVP implementation:

- `MarketRegimeMockAgent` is a rule-based offline placeholder.
- It generates valid JSON and caches one file per rebalance date.
- It classifies market state from benchmark trend, volatility, and drawdown.
- Its output is passed into the Strategy Selection mock agent.

## Agent 2: Strategy Selection Agent

Purpose:

Select suitable strategy families and assign dynamic strategy weights.

Candidate strategy families:

- SEPA / Stock Magician.
- VCP.
- CANSLIM-style growth leadership.
- Momentum.
- Value-quality.
- Low-volatility.
- Event-driven, if point-in-time event data is available.
- Mean reversion, if the experiment explicitly enables short-horizon signals.

Inputs:

- Market regime output.
- Strategy-family score distributions.
- Candidate stock summaries.
- Recent factor performance.
- Breadth and volatility context.

Outputs:

- `preferred_strategies`: list of strategy names and weights.
- `strategy_weight_sum`: must equal 1.0 after normalization.
- `stock_strategy_tags`: strategy tags and confidence per candidate.
- `selection_notes`: concise structured explanation.

Important constraint:

This agent must not invent unsupported stock facts. It can only use supplied
structured indicators and summaries.

Current MVP implementation:

- `StrategySelectionMockAgent` is a rule-based offline placeholder.
- It generates valid JSON and caches one file per rebalance date.
- It receives market-regime JSON and applies simple regime-aware strategy tilts.
- It does not call a real LLM.
- Its output contract is intended to stay compatible with the later real LLM
  implementation.

## Agent 3: Sector Rotation Agent

Purpose:

Assess industry exposure, crowding, and rotation risk.

Inputs:

- Candidate stocks with sector labels.
- Sector momentum.
- Sector breadth.
- Sector volatility.
- Concentration and crowding measures.

Outputs:

- `preferred_sectors`.
- `restricted_sectors`.
- `max_industry_weight`.
- `sector_penalty_overrides`.
- `confidence`.

## Agent 4: Risk Control Agent

Purpose:

Translate market and strategy context into risk preferences.

Inputs:

- Market regime output.
- Strategy selection output.
- Portfolio drawdown state.
- Volatility and correlation estimates.
- Transaction cost assumptions.

Outputs:

- `risk_level`.
- `max_position_per_stock`.
- `target_stock_count`.
- `turnover_limit`.
- `cash_buffer`.
- `volatility_penalty`.
- `drawdown_control`.

## Agent 5: Portfolio Constraint Agent

Purpose:

Merge previous agent outputs into a final optimizer-ready constraint object.

Inputs:

- Outputs from Agents 1-4.
- Candidate stock table.
- Baseline optimizer defaults.

Outputs:

- Final JSON constraints for the optimizer.
- Constraint conflict report.
- Fallback behavior if agent outputs are inconsistent.

Example output:

```json
{
  "market_state": "volatile_sideways",
  "strategy_weights": {
    "sepa_stock_magician": 0.25,
    "vcp": 0.25,
    "momentum": 0.15,
    "value_quality": 0.20,
    "low_volatility": 0.15
  },
  "max_position_per_stock": 0.06,
  "max_industry_weight": 0.22,
  "target_stock_count": 20,
  "turnover_limit": 0.30,
  "cash_buffer": 0.10,
  "volatility_penalty": 1.20,
  "constraint_conflicts": [],
  "confidence": 0.76
}
```

## Research Requirements

- All agent outputs must be valid JSON.
- All prompts and model settings must be versioned.
- All LLM outputs must be cached by date, universe, prompt version, and model.
- Experiments must include no-LLM and single-agent ablation baselines.
- Agent outputs must be evaluated for parse failure, constraint conflict, and
  stability across market regimes.
