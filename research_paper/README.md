# FinQuanta Research Paper Sandbox

This directory contains an isolated research sandbox for the paper-oriented
experiments. It must stay separate from the production quant stock-selection
workflow.

## Research Direction

Working title:

**A Risk-Constrained Portfolio Construction Framework with Multi-Agent LLMs and
Quantum-Inspired Optimization**

Core idea:

- Traditional quant strategies generate candidate stocks and structured alpha
  scores.
- A five-agent LLM layer identifies market regime, strategy suitability, sector
  rotation, risk preference, and final portfolio constraints.
- Classical and quantum-inspired optimizers construct final portfolios under
  explicit constraints.
- Experiments compare the proposed framework with equal-weight, index,
  multifactor, Markowitz, risk-parity, and non-LLM baselines.

## Isolation Rules

1. Production code must not import modules from `research_paper/`.
2. Research experiments may read shared project utilities through adapters, but
   must not modify production strategy, scheduler, database, notification, or
   trading code.
3. All experiment outputs must be written under `research_paper/results/`.
4. LLM responses used in experiments must be cached and versioned for
   reproducibility.
5. No experiment should trigger real orders, production approvals, or live
   notifications.

## Proposed Layout

```text
research_paper/
  README.md
  agents/
    five_agent_framework.md
  configs/
    mvp_hs300_monthly.yaml
  data_manifest/
    README.md
  experiments/
    README.md
  prompts/
    five_agent_prompts.md
  reports/
    README.md
  results/
    README.md
```

## MVP Experiment

Initial experiment name: `paper_v1_mvp_hs300_monthly`

Scope:

- Universe: CSI 300 constituents, or a fixed HS300-like research universe if
  constituent history is unavailable.
- Period: 2018-01-01 to 2025-12-31.
- Rebalance: monthly.
- Costs: configurable transaction cost and slippage.
- Candidate generation: multifactor score plus strategy-specific scores.
- Strategy families: SEPA/Stock Magician, VCP, momentum, value-quality,
  low-volatility, and optional event-driven signals.
- Optimizers: equal weight, Markowitz, risk parity, QUBO/simulated annealing.
- LLM layer: five-agent constraint generation.

Primary outputs:

- Performance metrics table.
- Turnover and cost analysis.
- Constraint violation report.
- Market-regime subperiod analysis.
- Ablation results.

## First Implementation Milestones

1. Freeze dataset and data-cleaning rules in `data_manifest/`.
2. Implement non-LLM baselines.
3. Add strategy-family scoring and fixed-weight multi-strategy fusion.
4. Add Strategy Selection Agent with cached JSON outputs.
5. Add full five-agent constraint generation.
6. Add optimizer comparison and ablation experiments.
7. Add bootstrap and statistical significance tests.
