"""Paper-only experiment runner for FinQuanta research baselines.

The runner intentionally stays inside ``research_paper/`` and uses synthetic
research data by default. It validates the isolation flags before doing any
work, then writes reproducible baseline outputs under the configured results
directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_paper.baselines.non_llm import NON_LLM_METHODS, run_backtest  # noqa: E402
from research_paper.common.config import load_config, validate_isolation  # noqa: E402
from research_paper.data_adapters import CsvSnapshotDataAdapter, MarketDataset, SyntheticResearchDataAdapter  # noqa: E402
from research_paper.evaluation.metrics import BacktestResult, benchmark_monthly_returns, calculate_metrics  # noqa: E402
from research_paper.agents import MarketRegimeMockAgent, StrategySelectionMockAgent  # noqa: E402

DEFAULT_CONFIG = PROJECT_ROOT / "research_paper" / "configs" / "mvp_hs300_monthly.yaml"


def write_outputs(
    output_dir: Path,
    config: dict[str, Any],
    dataset: MarketDataset,
    results: list[BacktestResult],
    metrics: list[dict[str, float | str]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(metrics).to_csv(output_dir / "metrics.csv", index=False)
    pd.concat([result.equity_curve for result in results], axis=1).to_csv(output_dir / "equity_curves.csv")
    pd.concat([result.period_returns for result in results], axis=1).to_csv(output_dir / "period_returns.csv")
    pd.concat([result.turnover for result in results], axis=1).to_csv(output_dir / "turnover.csv")
    pd.concat([result.costs for result in results], axis=1).to_csv(output_dir / "transaction_costs.csv")

    manifest = {
        "experiment": config["experiment"]["name"],
        "data_mode": dataset.data_mode,
        "methods": [result.method for result in results],
        "note": "This is an isolated dry-run baseline, not production trading output.",
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def load_dataset(config: dict[str, Any]) -> MarketDataset:
    source = str(config.get("data", {}).get("source", "synthetic")).lower()
    if source == "synthetic":
        return SyntheticResearchDataAdapter().load(config)
    if source == "csv_snapshot":
        return CsvSnapshotDataAdapter(PROJECT_ROOT).load(config)
    raise ValueError(f"Unsupported research data source: {source}. Use 'synthetic' or 'csv_snapshot'.")


def run(config_path: Path) -> Path:
    config = load_config(config_path)
    validate_isolation(config)

    output_dir = PROJECT_ROOT / config["experiment"]["output_dir"]
    dataset = load_dataset(config)
    methods = [method for method in config["optimization"]["methods"] if method in NON_LLM_METHODS]
    if not methods:
        raise RuntimeError("No supported non-LLM baseline methods are enabled in the config.")

    market_regime_agent = MarketRegimeMockAgent(PROJECT_ROOT, config, dataset.data_mode)
    strategy_agent = StrategySelectionMockAgent(PROJECT_ROOT, config, dataset.data_mode)
    results = [
        run_backtest(
            method,
            returns=dataset.returns,
            benchmark=dataset.benchmark,
            metadata=dataset.metadata,
            config=config,
            strategy_agent=strategy_agent if method == "llm_strategy_agent_mock" else None,
            market_regime_agent=market_regime_agent if method == "llm_strategy_agent_mock" else None,
        )
        for method in methods
    ]
    benchmark_returns = benchmark_monthly_returns(dataset.benchmark, results[0].period_returns.index)
    metrics = [calculate_metrics(result, benchmark_returns) for result in results]
    write_outputs(output_dir, config, dataset, results, metrics)
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paper-only FinQuanta baseline experiments.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to a research_paper YAML config.")
    args = parser.parse_args()

    output_dir = run(args.config.resolve())
    print(f"Research baseline dry-run complete. Outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
