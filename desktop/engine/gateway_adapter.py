"""
网关适配器：在网关外加一层日志 + order_bus 广播（可选）。
"""
from __future__ import annotations

from desktop.broker_gateway import BrokerGateway, OrderRequest, OrderStatus, PositionSnapshot
from desktop.order_bus import GLOBAL_EVENT_BUS


class GatewayAdapter:
    def __init__(self, inner: BrokerGateway, bus_source: str = "gateway_adapter"):
        self._inner = inner
        self._bus_source = bus_source

    def place_order(self, req: OrderRequest) -> OrderStatus:
        st = self._inner.place_order(req)
        GLOBAL_EVENT_BUS.publish(
            "order",
            self._bus_source,
            {"action": "place", "symbol": req.symbol, "side": req.side, "status": st.status},
        )
        return st

    def cancel_order(self, order_id: str) -> OrderStatus:
        st = self._inner.cancel_order(order_id)
        GLOBAL_EVENT_BUS.publish(
            "order",
            self._bus_source,
            {"action": "cancel", "order_id": order_id, "status": st.status},
        )
        return st

    def query_positions(self, account_id: str = "") -> list[PositionSnapshot]:
        return self._inner.query_positions(account_id)

    def query_balance(self, account_id: str = "") -> dict:
        return self._inner.query_balance(account_id)

    def query_order(self, order_id: str) -> OrderStatus | None:
        q = getattr(self._inner, "query_order", None)
        if callable(q):
            return q(order_id)
        return None
