"""
真实券商网关占位：后续可接 XTP / 掘金 / 券商 HTTP 等。

环境变量（示例）：
  FINQUANTA_REAL_BROKER=stub|xtp|...  未实现时一律拒绝或返回明确错误。
"""
from __future__ import annotations

import os
from datetime import datetime

from desktop.broker_gateway import OrderRequest, OrderStatus, PositionSnapshot


class RealGateway:
    """
    真实交易接口预留：当前默认拒绝下单，避免误连生产。

    接入时在此类中实现 BrokerGateway 协议，并由 MainEngine 注入。
    """

    def __init__(self, account_id: str = ""):
        self._account_id = account_id or os.environ.get("FINQUANTA_ACCOUNT_ID", "")

    def place_order(self, req: OrderRequest) -> OrderStatus:
        return OrderStatus(
            order_id="",
            symbol=req.symbol,
            side=req.side,
            price=req.price,
            volume=req.volume,
            filled=0,
            status="REJECTED",
            timestamp=datetime.now().isoformat(),
            message="RealGateway not configured; set broker adapter in engine",
            avg_fill_price=0.0,
        )

    def cancel_order(self, order_id: str) -> OrderStatus:
        return OrderStatus(
            order_id=order_id,
            symbol="",
            side="",
            price=0.0,
            volume=0,
            filled=0,
            status="REJECTED",
            timestamp=datetime.now().isoformat(),
            message="RealGateway not configured",
            avg_fill_price=0.0,
        )

    def query_positions(self, account_id: str = "") -> list[PositionSnapshot]:
        return []

    def query_balance(self, account_id: str = "") -> dict:
        return {
            "account_id": account_id or self._account_id,
            "cash": 0.0,
            "available": 0.0,
            "equity": 0.0,
            "note": "real broker not connected",
        }

    def query_order(self, order_id: str) -> OrderStatus | None:
        return None
