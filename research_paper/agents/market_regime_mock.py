"""Rule-based mock Market Regime Agent with JSON caching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


class MarketRegimeMockAgent:
    """Offline market-regime classifier used to wire the five-agent pipeline."""

    agent_name = "market_regime_agent_mock"
    prompt_version = "paper_v1_mock_market_regime_001"

    def __init__(self, project_root: Path, config: dict[str, Any], data_mode: str) -> None:
        self.config = config
        self.data_mode = data_mode
        self.experiment_name = str(config["experiment"]["name"])
        cache_dir = Path(str(config.get("agents", {}).get("cache_dir", "research_paper/results/llm_cache")))
        if not cache_dir.is_absolute():
            cache_dir = project_root / cache_dir
        self.cache_dir = cache_dir / self.agent_name / self.experiment_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, as_of_date: pd.Timestamp, benchmark: pd.Series) -> dict[str, Any]:
        cache_path = self._cache_path(as_of_date)
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("prompt_version") == self.prompt_version:
                return cached

        output = self._generate_uncached(as_of_date, benchmark)
        cache_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        return output

    def _cache_path(self, as_of_date: pd.Timestamp) -> Path:
        return self.cache_dir / f"{as_of_date.strftime('%Y%m%d')}.json"

    def _generate_uncached(self, as_of_date: pd.Timestamp, benchmark: pd.Series) -> dict[str, Any]:
        history = benchmark.loc[:as_of_date].tail(126)
        if len(history) < 21:
            raise ValueError("At least 21 benchmark observations are required for market regime classification.")

        return_21d = float((1.0 + history.tail(21)).prod() - 1.0)
        return_63d = float((1.0 + history.tail(63)).prod() - 1.0)
        realized_vol_63d = float(history.tail(63).std() * (252.0**0.5))
        equity = (1.0 + history).cumprod()
        drawdown_126d = float(equity.iloc[-1] / equity.cummax().iloc[-1] - 1.0)

        market_state = self._classify_state(return_21d, return_63d, realized_vol_63d, drawdown_126d)
        risk_environment = self._classify_risk(realized_vol_63d, drawdown_126d)
        confidence = self._confidence(return_63d, realized_vol_63d, drawdown_126d)

        return {
            "agent": self.agent_name,
            "prompt_version": self.prompt_version,
            "model": "rule_based_mock",
            "data_mode": self.data_mode,
            "as_of_date": as_of_date.strftime("%Y-%m-%d"),
            "market_state": market_state,
            "risk_environment": risk_environment,
            "features": {
                "return_21d": round(return_21d, 6),
                "return_63d": round(return_63d, 6),
                "realized_vol_63d": round(realized_vol_63d, 6),
                "drawdown_126d": round(drawdown_126d, 6),
            },
            "evidence": [
                f"63-day benchmark return is {return_63d:.3f}.",
                f"63-day annualized volatility is {realized_vol_63d:.3f}.",
                f"126-day drawdown is {drawdown_126d:.3f}.",
            ],
            "confidence": confidence,
        }

    @staticmethod
    def _classify_state(return_21d: float, return_63d: float, realized_vol_63d: float, drawdown_126d: float) -> str:
        if drawdown_126d < -0.15 and return_63d < -0.05:
            return "bear"
        if realized_vol_63d > 0.28:
            return "high_volatility"
        if return_63d > 0.08 and return_21d > 0:
            return "bull"
        if abs(return_63d) < 0.04:
            return "sideways"
        if realized_vol_63d > 0.22:
            return "volatile_sideways"
        return "sideways"

    @staticmethod
    def _classify_risk(realized_vol_63d: float, drawdown_126d: float) -> str:
        if realized_vol_63d > 0.28 or drawdown_126d < -0.15:
            return "high"
        if realized_vol_63d > 0.20 or drawdown_126d < -0.08:
            return "medium"
        return "low"

    @staticmethod
    def _confidence(return_63d: float, realized_vol_63d: float, drawdown_126d: float) -> float:
        signal_strength = min(1.0, abs(return_63d) / 0.12 + realized_vol_63d / 0.60 + abs(drawdown_126d) / 0.25)
        return round(0.50 + 0.45 * signal_strength, 6)
