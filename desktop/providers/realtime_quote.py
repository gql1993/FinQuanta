"""实时行情：默认新浪等。"""
from __future__ import annotations

from typing import Any


class RealtimeQuoteProvider:
    def get_quotes(self, codes: list[str], force: bool = False) -> dict[str, Any]:
        from desktop.realtime_data import get_realtime_quotes

        return get_realtime_quotes(codes, force=force)
