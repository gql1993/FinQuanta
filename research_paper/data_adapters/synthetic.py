"""Synthetic research data adapter for dry-run experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MarketDataset:
    """Point-in-time market dataset used by paper experiments."""

    returns: pd.DataFrame
    benchmark: pd.Series
    metadata: pd.DataFrame
    data_mode: str


class SyntheticResearchDataAdapter:
    """Generate deterministic synthetic A-share-like data for dry runs."""

    data_mode = "synthetic_research_data"

    def load(self, config: dict[str, Any]) -> MarketDataset:
        data_config = config["data"]
        strategy_config = config["strategy_scores"]
        seed = int(config["experiment"].get("random_seed", 20260507))
        rng = np.random.default_rng(seed)

        dates = pd.bdate_range(data_config["start_date"], data_config["end_date"])
        asset_count = int(strategy_config.get("candidate_pool_size", 100))
        symbols = [f"RP{i:04d}" for i in range(1, asset_count + 1)]

        quality = rng.normal(0, 1, asset_count)
        growth = rng.normal(0, 1, asset_count)
        value = rng.normal(0, 1, asset_count)
        liquidity = rng.uniform(0.2, 1.0, asset_count)
        sectors = np.array([f"sector_{i % 10:02d}" for i in range(asset_count)])

        market = rng.normal(0.00025, 0.011, len(dates))
        style_alpha = 0.00008 * quality + 0.00006 * growth + 0.00003 * value
        noise = rng.normal(0, 0.018, (len(dates), asset_count))
        returns = pd.DataFrame(market[:, None] + style_alpha[None, :] + noise, index=dates, columns=symbols)
        returns = returns.clip(lower=-0.10, upper=0.10)

        benchmark = pd.Series(market + rng.normal(0, 0.006, len(dates)), index=dates, name="benchmark")
        metadata = pd.DataFrame(
            {
                "symbol": symbols,
                "sector": sectors,
                "quality": quality,
                "growth": growth,
                "value": value,
                "liquidity": liquidity,
            }
        ).set_index("symbol")

        return MarketDataset(
            returns=returns,
            benchmark=benchmark,
            metadata=metadata,
            data_mode=self.data_mode,
        )
