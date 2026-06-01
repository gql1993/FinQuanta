# Experiments

This directory will contain paper-only experiment runners.

Planned entry point:

```bash
python research_paper/experiments/run_experiment.py --config research_paper/configs/mvp_hs300_monthly.yaml
```

Implementation principles:

- Read configuration first.
- Validate isolation flags before running.
- Load market data through a research adapter. The current MVP supports only
  `data.source: synthetic` and `data.source: csv_snapshot`.
- Cache LLM outputs before portfolio optimization.
- Write all outputs under `research_paper/results/`.
- Never trigger live trading, production notifications, or production database
  writes.

Initial experiment stages:

1. Non-LLM baselines.
2. Strategy-family scoring.
3. Strategy Selection Agent.
4. Full five-agent constraint generation.
5. Optimizer comparison.
6. Ablation and statistical tests.

Current non-LLM dry-run baselines:

- `equal_weight`
- `multifactor_topk`
- `sepa_stock_magician_topk`
- `vcp_topk`
- `fixed_multistrategy_fusion`
- `llm_strategy_agent_mock`

`llm_strategy_agent_mock` is a rule-based offline mock. It writes JSON files to
the configured agent cache directory and does not call a real LLM. It currently
uses `MarketRegimeMockAgent` output as structured context before generating
strategy weights.
