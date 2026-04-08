"""
风控（第一阶段：全局开关 + 额度占位，与 kv_store 对齐）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from desktop import data_access


@dataclass
class RiskCheckResult:
    ok: bool
    reason: str = ""


class RiskManager:
    """
    读取统一 kv：
    - TRADING_HALT: 非空则禁止新开仓（Paper/Real 均应检查）
    - risk_max_single_position_pct: 单票上限（可选，0-100）
    """

    def __init__(self):
        pass

    def is_halted(self) -> bool:
        v = data_access.get_kv_json("TRADING_HALT", None)
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        s = str(v).strip().lower()
        return s in {"1", "true", "yes", "on", "halt"}

    def check_new_order(self, side: str, symbol: str, volume: int, price: float) -> RiskCheckResult:
        if self.is_halted() and side.upper() == "BUY":
            return RiskCheckResult(ok=False, reason="TRADING_HALT")
        return RiskCheckResult(ok=True)

    def snapshot(self) -> dict[str, Any]:
        return {"halted": self.is_halted()}
