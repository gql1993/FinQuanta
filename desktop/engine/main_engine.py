"""
主引擎（参考 vn.py MainEngine）：聚合 EventEngine、OMS、Risk、Account、网关。
"""
from __future__ import annotations

import os
from typing import Any, Literal

from desktop.broker_gateway import BrokerGateway, OrderRequest, OrderStatus
from desktop.engine.account_service import AccountService
from desktop.engine.event_engine import EventEngine, get_default_engine
from desktop.engine.oms import OrderManagementService
from desktop.engine.paper_gateway import PaperGateway
from desktop.engine.real_gateway import RealGateway
from desktop.engine.risk_manager import RiskManager


Mode = Literal["paper", "real"]


def _mode_from_env() -> Mode:
    m = (os.environ.get("FINQUANTA_TRADING_MODE") or "paper").strip().lower()
    return "real" if m == "real" else "paper"


class MainEngine:
    def __init__(
        self,
        gateway: BrokerGateway | None = None,
        mode: Mode | None = None,
        event_engine: EventEngine | None = None,
    ):
        self.mode: Mode = mode or _mode_from_env()
        self.event_engine = event_engine or get_default_engine()
        self.risk = RiskManager()

        if gateway is not None:
            self.gateway = gateway
        elif self.mode == "real":
            self.gateway = RealGateway()
        else:
            self.gateway = PaperGateway()

        self.oms = OrderManagementService(self.gateway, risk=self.risk, engine=self.event_engine)
        self.account = AccountService(self.gateway)

    def send_order(self, req: OrderRequest) -> OrderStatus:
        return self.oms.submit(req)

    def cancel_order(self, order_id: str) -> OrderStatus:
        return self.oms.cancel(order_id)

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "risk": self.risk.snapshot(),
            "balance": self.account.get_balance(),
            "positions": self.account.get_positions_dict(),
        }


_DEFAULT_MAIN: MainEngine | None = None


def get_default_main_engine() -> MainEngine:
    """进程内单例，供快照/API 与桌面共用同一 Paper/OMS 状态。"""
    global _DEFAULT_MAIN
    if _DEFAULT_MAIN is None:
        _DEFAULT_MAIN = MainEngine()
    return _DEFAULT_MAIN
