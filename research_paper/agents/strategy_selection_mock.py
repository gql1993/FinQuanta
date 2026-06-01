"""Rule-based mock Strategy Selection Agent with JSON caching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


STRATEGY_COLUMNS = ["sepa_stock_magician", "vcp", "momentum", "value_quality", "low_volatility"]


class StrategySelectionMockAgent:
    """Offline mock agent that mimics LLM JSON outputs without calling an LLM."""

    agent_name = "strategy_selection_agent_mock"
    prompt_version = "paper_v1_mock_strategy_selection_003"

    def __init__(self, project_root: Path, config: dict[str, Any], data_mode: str) -> None:
        self.project_root = project_root
        self.config = config
        self.data_mode = data_mode
        self.experiment_name = str(config["experiment"]["name"])
        cache_dir = Path(str(config.get("agents", {}).get("cache_dir", "research_paper/results/llm_cache")))
        if not cache_dir.is_absolute():
            cache_dir = project_root / cache_dir
        self.cache_dir = cache_dir / self.agent_name / self.experiment_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        as_of_date: pd.Timestamp,
        scores: pd.DataFrame,
        market_regime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cache_path = self._cache_path(as_of_date)
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("prompt_version") == self.prompt_version:
                return cached

        output = self._generate_uncached(as_of_date, scores, market_regime)
        cache_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        return output

    def weighted_scores(
        self,
        as_of_date: pd.Timestamp,
        scores: pd.DataFrame,
        market_regime: dict[str, Any] | None = None,
    ) -> pd.Series:
        output = self.generate(as_of_date, scores, market_regime)
        weights = {
            item["strategy"]: float(item["weight"])
            for item in output.get("preferred_strategies", [])
            if item.get("strategy") in scores.columns
        }
        if not weights:
            return scores[STRATEGY_COLUMNS].mean(axis=1)

        weighted = pd.Series(0.0, index=scores.index)
        for strategy, weight in weights.items():
            weighted = weighted + scores[strategy] * weight
        return weighted

    def _cache_path(self, as_of_date: pd.Timestamp) -> Path:
        return self.cache_dir / f"{as_of_date.strftime('%Y%m%d')}.json"

    def _generate_uncached(
        self,
        as_of_date: pd.Timestamp,
        scores: pd.DataFrame,
        market_regime: dict[str, Any] | None,
    ) -> dict[str, Any]:
        strategy_stats = self._strategy_stats(scores)
        raw_weights = self._raw_strategy_weights(strategy_stats, market_regime)
        strategy_weights = self._normalize(raw_weights)
        weighted_scores = sum(scores[strategy] * weight for strategy, weight in strategy_weights.items())
        top_symbols = weighted_scores.nlargest(int(self.config["strategy_scores"].get("candidate_pool_size", 100))).index

        preferred = [
            {
                "strategy": strategy,
                "weight": round(weight, 6),
                "reason": self._strategy_reason(strategy, strategy_stats[strategy]),
            }
            for strategy, weight in sorted(strategy_weights.items(), key=lambda item: item[1], reverse=True)
        ]
        stock_tags = [
            {
                "symbol": str(symbol),
                "tags": self._stock_tags(scores.loc[symbol]),
                "strategy_confidence": round(float(weighted_scores.loc[symbol]), 6),
                "selection_priority": round(float(weighted_scores.rank(pct=True).loc[symbol]), 6),
            }
            for symbol in top_symbols[:50]
        ]

        return {
            "agent": self.agent_name,
            "prompt_version": self.prompt_version,
            "model": "rule_based_mock",
            "data_mode": self.data_mode,
            "as_of_date": as_of_date.strftime("%Y-%m-%d"),
            "market_regime": self._compact_market_regime(market_regime),
            "preferred_strategies": preferred,
            "strategy_weight_sum": round(sum(item["weight"] for item in preferred), 6),
            "stock_strategy_tags": stock_tags,
            "selection_notes": [
                "Rule-based mock output for offline pipeline validation.",
                "Uses only structured market-regime and strategy-score inputs supplied by the backtest.",
            ],
            "confidence": round(float(max(strategy_weights.values())), 6),
        }

    @staticmethod
    def _strategy_stats(scores: pd.DataFrame) -> dict[str, dict[str, float]]:
        stats: dict[str, dict[str, float]] = {}
        reference = scores["multifactor"]
        for strategy in STRATEGY_COLUMNS:
            series = scores[strategy]
            top_symbols = series.nlargest(max(1, len(series) // 10)).index
            alignment = series.corr(reference)
            stats[strategy] = {
                "mean": float(series.mean()),
                "top_decile_mean": float(series.nlargest(max(1, len(series) // 10)).mean()),
                "top_decile_multifactor": float(reference.loc[top_symbols].mean()),
                "dispersion": float(series.quantile(0.9) - series.quantile(0.1)),
                "alignment_with_multifactor": float(alignment) if pd.notna(alignment) else 0.0,
            }
        return stats

    @staticmethod
    def _raw_strategy_weights(
        strategy_stats: dict[str, dict[str, float]],
        market_regime: dict[str, Any] | None,
    ) -> dict[str, float]:
        raw: dict[str, float] = {}
        for strategy, stats in strategy_stats.items():
            raw[strategy] = max(
                0.01,
                0.45 * stats["top_decile_multifactor"]
                + 0.30 * max(0.0, stats["alignment_with_multifactor"])
                + 0.15 * stats["top_decile_mean"]
                + 0.10 * stats["dispersion"],
            )

        # Defensive tilt: if low-volatility has unusually strong separation, let it matter.
        if strategy_stats["low_volatility"]["dispersion"] > strategy_stats["momentum"]["dispersion"]:
            raw["low_volatility"] *= 1.15
        StrategySelectionMockAgent._apply_market_regime_tilts(raw, market_regime)
        return raw

    @staticmethod
    def _apply_market_regime_tilts(raw: dict[str, float], market_regime: dict[str, Any] | None) -> None:
        if not market_regime:
            return
        market_state = str(market_regime.get("market_state", "sideways"))
        risk_environment = str(market_regime.get("risk_environment", "medium"))

        if market_state == "bull":
            raw["sepa_stock_magician"] *= 1.20
            raw["momentum"] *= 1.15
            raw["vcp"] *= 1.10
        elif market_state in {"bear", "high_volatility"}:
            raw["low_volatility"] *= 1.30
            raw["value_quality"] *= 1.20
            raw["momentum"] *= 0.85
            raw["sepa_stock_magician"] *= 0.90
        elif market_state in {"sideways", "volatile_sideways"}:
            raw["vcp"] *= 1.15
            raw["low_volatility"] *= 1.10
            raw["value_quality"] *= 1.05

        if risk_environment == "high":
            raw["low_volatility"] *= 1.20
            raw["value_quality"] *= 1.10
        elif risk_environment == "low":
            raw["sepa_stock_magician"] *= 1.05
            raw["momentum"] *= 1.05

    @staticmethod
    def _normalize(raw_weights: dict[str, float]) -> dict[str, float]:
        total = sum(raw_weights.values())
        if total <= 0:
            return {strategy: 1.0 / len(raw_weights) for strategy in raw_weights}
        return {strategy: weight / total for strategy, weight in raw_weights.items()}

    @staticmethod
    def _stock_tags(row: pd.Series) -> list[str]:
        ranked = row[STRATEGY_COLUMNS].sort_values(ascending=False)
        return [str(strategy) for strategy, value in ranked.head(2).items() if float(value) >= 0.5]

    @staticmethod
    def _compact_market_regime(market_regime: dict[str, Any] | None) -> dict[str, Any]:
        if not market_regime:
            return {}
        return {
            "market_state": market_regime.get("market_state"),
            "risk_environment": market_regime.get("risk_environment"),
            "confidence": market_regime.get("confidence"),
            "features": market_regime.get("features", {}),
        }

    @staticmethod
    def _strategy_reason(strategy: str, stats: dict[str, float]) -> str:
        return (
            f"{strategy} has top-decile strength {stats['top_decile_mean']:.3f}, "
            f"top-decile multifactor quality {stats['top_decile_multifactor']:.3f}, "
            f"and multifactor alignment {stats['alignment_with_multifactor']:.3f}."
        )
