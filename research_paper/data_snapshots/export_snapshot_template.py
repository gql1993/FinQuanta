"""Export a frozen CSV research snapshot for paper experiments.

This template intentionally avoids production imports and production writes. The
current implementation supports a deterministic ``demo-synthetic`` mode so the
CSV snapshot pipeline can be tested end to end before connecting approved
read-only market data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_paper.common.config import load_config, validate_isolation  # noqa: E402
from research_paper.data_adapters.csv_snapshot import CsvSnapshotDataAdapter  # noqa: E402
from research_paper.data_adapters.synthetic import MarketDataset, SyntheticResearchDataAdapter  # noqa: E402

DEFAULT_CONFIG = PROJECT_ROOT / "research_paper" / "configs" / "mvp_hs300_monthly_csv_snapshot.yaml"


def _resolve_snapshot_paths(config: dict[str, Any]) -> dict[str, Path]:
    snapshot = config.get("data", {}).get("snapshot", {})
    if not isinstance(snapshot, dict):
        raise ValueError("data.snapshot must be configured.")

    required = {
        "returns": "returns_path",
        "benchmark": "benchmark_path",
        "metadata": "metadata_path",
    }
    paths: dict[str, Path] = {}
    for name, key in required.items():
        raw_path = snapshot.get(key)
        if not raw_path:
            raise ValueError(f"Missing data.snapshot.{key}")
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        paths[name] = path
    return paths


def _ensure_writable(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Snapshot files already exist. Use --force to overwrite: {joined}")
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)


def _load_demo_synthetic_dataset(config: dict[str, Any]) -> MarketDataset:
    synthetic_config = dict(config)
    synthetic_config["data"] = dict(config["data"])
    synthetic_config["data"]["source"] = "synthetic"
    return SyntheticResearchDataAdapter().load(synthetic_config)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_dataset(dataset: MarketDataset, paths: dict[str, Path]) -> None:
    returns = dataset.returns.copy()
    returns.insert(0, "date", returns.index.strftime("%Y-%m-%d"))
    returns.to_csv(paths["returns"], index=False)

    benchmark = pd.DataFrame(
        {
            "date": dataset.benchmark.index.strftime("%Y-%m-%d"),
            "benchmark_return": dataset.benchmark.to_numpy(),
        }
    )
    benchmark.to_csv(paths["benchmark"], index=False)

    metadata = dataset.metadata.reset_index()
    metadata.to_csv(paths["metadata"], index=False)


def _write_manifest(config: dict[str, Any], dataset: MarketDataset, paths: dict[str, Path], mode: str) -> Path:
    manifest_path = paths["returns"].parent / "snapshot_manifest.json"
    manifest = {
        "experiment": config["experiment"]["name"],
        "mode": mode,
        "data_mode": dataset.data_mode,
        "start_date": config["data"]["start_date"],
        "end_date": config["data"]["end_date"],
        "rows": {
            "returns": int(len(dataset.returns)),
            "benchmark": int(len(dataset.benchmark)),
            "metadata": int(len(dataset.metadata)),
        },
        "symbols": int(len(dataset.returns.columns)),
        "files": {
            name: {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sha256": _file_sha256(path),
            }
            for name, path in paths.items()
        },
        "note": "Demo synthetic snapshot. Replace mode with an approved read-only data export for paper evidence.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def export_snapshot(config_path: Path, mode: str, force: bool) -> Path:
    config = load_config(config_path)
    validate_isolation(config)
    paths = _resolve_snapshot_paths(config)
    _ensure_writable(paths, force=force)

    if mode != "demo-synthetic":
        raise ValueError("Only --mode demo-synthetic is implemented in the template.")

    dataset = _load_demo_synthetic_dataset(config)
    _write_dataset(dataset, paths)
    manifest_path = _write_manifest(config, dataset, paths, mode)

    # Validate the exported files through the same adapter used by experiments.
    CsvSnapshotDataAdapter(PROJECT_ROOT).load(config)
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a paper research CSV snapshot.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="CSV snapshot experiment config.")
    parser.add_argument("--mode", default="demo-synthetic", choices=["demo-synthetic"])
    parser.add_argument("--force", action="store_true", help="Overwrite existing snapshot CSV files.")
    args = parser.parse_args()

    manifest_path = export_snapshot(args.config.resolve(), mode=args.mode, force=args.force)
    print(f"CSV snapshot exported and validated. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
