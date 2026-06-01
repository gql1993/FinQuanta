# Data Manifest

This directory records the exact data assumptions used by paper experiments.

Each experiment should document:

- Universe definition and constituent source.
- Date range.
- Price adjustment method.
- ST, suspension, listing-age, and liquidity filters.
- Benchmark symbols and source.
- Point-in-time data guarantees.
- Data snapshot hash or export timestamp.

Recommended file naming:

```text
paper_v1_mvp_hs300_monthly_manifest.yaml
```

No production database writes should happen from this directory or from scripts
that consume these manifests.

## Current MVP Data Source

`mvp_hs300_monthly.yaml` currently uses:

```yaml
data:
  source: synthetic
```

This means the experiment validates the research pipeline with deterministic
synthetic returns and factor metadata. It is not evidence for the paper yet.
The next data milestone is a read-only adapter that exports a frozen research
snapshot from approved market data.

## CSV Snapshot Mode

`mvp_hs300_monthly_csv_snapshot.yaml` uses:

```yaml
data:
  source: csv_snapshot
```

This mode reads frozen files from `research_paper/data_snapshots/` and never
writes to production storage. See `research_paper/data_snapshots/README.md` for
the exact CSV schema.
