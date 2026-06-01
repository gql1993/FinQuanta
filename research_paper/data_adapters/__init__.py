"""Research data adapters.

Adapters in this package are paper-only and should be read-only when connected
to project data sources.
"""

from research_paper.data_adapters.csv_snapshot import CsvSnapshotDataAdapter
from research_paper.data_adapters.synthetic import MarketDataset, SyntheticResearchDataAdapter

__all__ = ["CsvSnapshotDataAdapter", "MarketDataset", "SyntheticResearchDataAdapter"]
