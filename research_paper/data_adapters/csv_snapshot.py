"""Read-only CSV snapshot adapter for reproducible paper experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from research_paper.data_adapters.synthetic import MarketDataset


REQUIRED_METADATA_COLUMNS = {"symbol", "sector", "quality", "growth", "value", "liquidity"}


class CsvSnapshotDataAdapter:
    """Load a frozen research dataset from CSV files.

    Expected files:

    - returns.csv: date column plus one column per symbol, values are daily returns.
    - benchmark.csv: date and benchmark_return columns.
    - metadata.csv: symbol, sector, quality, growth, value, liquidity columns.
    """

    data_mode = "csv_snapshot"

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def load(self, config: dict[str, Any]) -> MarketDataset:
        data_config = config["data"]
        snapshot_config = data_config.get("snapshot", {})
        if not isinstance(snapshot_config, dict):
            raise ValueError("data.snapshot must be a mapping for csv_snapshot source.")

        returns = self._load_returns(self._resolve_path(snapshot_config.get("returns_path")))
        benchmark = self._load_benchmark(self._resolve_path(snapshot_config.get("benchmark_path")))
        metadata = self._load_metadata(self._resolve_path(snapshot_config.get("metadata_path")))

        start_date = pd.Timestamp(data_config["start_date"])
        end_date = pd.Timestamp(data_config["end_date"])
        returns = returns.loc[(returns.index >= start_date) & (returns.index <= end_date)]
        benchmark = benchmark.loc[(benchmark.index >= start_date) & (benchmark.index <= end_date)]

        common_symbols = [symbol for symbol in returns.columns if symbol in metadata.index]
        if not common_symbols:
            raise ValueError("No overlapping symbols between returns.csv and metadata.csv.")

        returns = returns[common_symbols].sort_index()
        metadata = metadata.loc[common_symbols]
        benchmark = benchmark.sort_index()

        if len(returns) < 126:
            raise ValueError("CSV snapshot must contain at least 126 trading days for current baselines.")
        if benchmark.empty:
            raise ValueError("benchmark.csv has no rows after date filtering.")

        return MarketDataset(
            returns=returns,
            benchmark=benchmark,
            metadata=metadata,
            data_mode=self.data_mode,
        )

    def _resolve_path(self, raw_path: Any) -> Path:
        if not raw_path:
            raise ValueError("CSV snapshot path is missing.")
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = self.project_root / path
        if not path.exists():
            raise FileNotFoundError(f"CSV snapshot file does not exist: {path}")
        return path

    @staticmethod
    def _load_returns(path: Path) -> pd.DataFrame:
        frame = pd.read_csv(path)
        if "date" not in frame.columns:
            raise ValueError(f"returns.csv must include a date column: {path}")
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.set_index("date").sort_index()
        if frame.empty or len(frame.columns) == 0:
            raise ValueError(f"returns.csv must include at least one symbol column: {path}")
        return frame.apply(pd.to_numeric, errors="coerce").fillna(0.0)

    @staticmethod
    def _load_benchmark(path: Path) -> pd.Series:
        frame = pd.read_csv(path)
        required = {"date", "benchmark_return"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"benchmark.csv missing columns {sorted(missing)}: {path}")
        frame["date"] = pd.to_datetime(frame["date"])
        benchmark = pd.to_numeric(frame["benchmark_return"], errors="coerce").fillna(0.0)
        benchmark.index = frame["date"]
        benchmark = benchmark.sort_index()
        benchmark.name = "benchmark"
        return benchmark

    @staticmethod
    def _load_metadata(path: Path) -> pd.DataFrame:
        frame = pd.read_csv(path)
        missing = REQUIRED_METADATA_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"metadata.csv missing columns {sorted(missing)}: {path}")
        frame = frame.set_index("symbol")
        numeric_columns = ["quality", "growth", "value", "liquidity"]
        frame[numeric_columns] = frame[numeric_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        frame["sector"] = frame["sector"].fillna("unknown").astype(str)
        return frame
