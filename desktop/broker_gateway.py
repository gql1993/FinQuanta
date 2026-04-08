"""
实盘底座准备：券商/交易网关抽象层

当前不接真实券商，只建立统一接口与事件模型，
为后续接入 vn.py / 券商API / 模拟撮合打基础。

双轨：
- PaperGateway：完整撮合/持仓/资金（见 desktop.engine.paper_gateway）
- RealGateway：真实接口占位（见 desktop.engine.real_gateway）
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class OrderRequest:
    symbol: str
    side: str  # BUY / SELL
    price: float
    volume: int
    account_id: str = ""
    strategy: str = ""
    remark: str = ""
    order_type: str = "MARKET"  # MARKET / LIMIT
    limit_price: float = 0.0
    client_order_id: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class OrderStatus:
    order_id: str
    symbol: str
    side: str
    price: float
    volume: int
    filled: int = 0
    status: str = "SUBMITTED"  # SUBMITTED/FILLED/PARTIAL/CANCELLED/REJECTED
    timestamp: str = ""
    message: str = ""
    avg_fill_price: float = 0.0


@dataclass
class PositionSnapshot:
    account_id: str
    symbol: str
    volume: int
    available: int
    avg_price: float
    market_price: float = 0.0
    pnl: float = 0.0


class BrokerGateway(Protocol):
    def place_order(self, req: OrderRequest) -> OrderStatus:
        ...

    def cancel_order(self, order_id: str) -> OrderStatus:
        ...

    def query_positions(self, account_id: str = "") -> list[PositionSnapshot]:
        ...

    def query_balance(self, account_id: str = "") -> dict:
        ...

    def query_order(self, order_id: str) -> OrderStatus | None:
        ...


class SimulatedGateway:
    """
    兼容旧名：等价于立即成交的极简网关（无持仓资金逻辑）。
    新代码请优先使用 PaperGateway。
    """

    def place_order(self, req: OrderRequest) -> OrderStatus:
        return OrderStatus(
            order_id=f"SIM-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            symbol=req.symbol,
            side=req.side,
            price=req.price,
            volume=req.volume,
            filled=req.volume,
            status="FILLED",
            timestamp=datetime.now().isoformat(),
            message="simulated execution",
            avg_fill_price=req.price,
        )

    def cancel_order(self, order_id: str) -> OrderStatus:
        return OrderStatus(
            order_id=order_id,
            symbol="",
            side="",
            price=0.0,
            volume=0,
            status="CANCELLED",
            timestamp=datetime.now().isoformat(),
            message="simulated cancel",
        )

    def query_positions(self, account_id: str = "") -> list[PositionSnapshot]:
        return []

    def query_balance(self, account_id: str = "") -> dict:
        return {"account_id": account_id, "cash": 0.0, "available": 0.0, "equity": 0.0}

    def query_order(self, order_id: str) -> OrderStatus | None:
        return None


def gateway_to_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return obj


def get_default_gateway():
    """默认使用 PaperGateway（可复现下单/撤单/持仓）。"""
    from desktop.engine.paper_gateway import PaperGateway

    return PaperGateway()
