# Data Snapshots

This directory is reserved for frozen research datasets used by paper
experiments.

Large market data snapshots should normally stay out of Git unless a separate
artifact policy is defined. Keep small schema examples and manifests in Git.

## CSV Snapshot Schema

`csv_snapshot` experiments expect three files.

### returns.csv

Daily asset returns in wide format:

```csv
date,000001.SZ,000002.SZ,600000.SH
2018-01-02,0.0123,-0.0045,0.0067
2018-01-03,-0.0030,0.0011,0.0022
```

Rules:

- `date` must be parseable as a calendar date.
- Each symbol column must contain daily returns, not prices.
- Missing returns are filled with `0.0` by the adapter.

### benchmark.csv

Daily benchmark returns:

```csv
date,benchmark_return
2018-01-02,0.0065
2018-01-03,-0.0021
```

Rules:

- `benchmark_return` is a daily return series.
- The current MVP uses one benchmark series for information-ratio comparison.

### metadata.csv

Per-symbol static research metadata:

```csv
symbol,sector,quality,growth,value,liquidity
000001.SZ,bank,0.62,0.41,0.70,0.91
000002.SZ,real_estate,0.51,0.35,0.66,0.88
```

Required columns:

- `symbol`
- `sector`
- `quality`
- `growth`
- `value`
- `liquidity`

The MVP baselines use these fields to create simple dry-run factor scores.
Later paper versions can add point-in-time factor panels, but this static file
is enough to validate the CSV adapter and non-LLM baseline pipeline.

## Template Config

Use this config after preparing the files:

```bash
python research_paper/experiments/run_experiment.py --config research_paper/configs/mvp_hs300_monthly_csv_snapshot.yaml
```

## Export Template

The template exporter currently supports a deterministic demo mode:

```bash
python research_paper/data_snapshots/export_snapshot_template.py --config research_paper/configs/mvp_hs300_monthly_csv_snapshot.yaml
```

It writes:

- `returns.csv`
- `benchmark.csv`
- `metadata.csv`
- `snapshot_manifest.json`

The script validates the exported files through the same `csv_snapshot` adapter
used by experiments. It refuses to overwrite existing snapshot files unless
`--force` is passed.

The `demo-synthetic` mode is only for validating the research pipeline. For
paper evidence, replace the loading step with an approved read-only export from
frozen market data.
