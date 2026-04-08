"""
订单管理服务（OMS）：幂等键、风控、网关调用、事件投递。
"""
from __future__ import annotations

import logging
from typing import Any

from desktop.broker_gateway import BrokerGateway, OrderRequest, OrderStatus
from desktop.engine.constants import EVENT_ORDER, EVENT_ORDER_REJECT, EVENT_TRADE
from desktop.engine.event_engine import EventEngine
from desktop.engine.risk_manager import RiskManager

_log = logging.getLogger("oms")


class OrderManagementService:
    def __init__(self, gateway: BrokerGateway, risk: RiskManager | None = None, engine: EventEngine | None = None):
        self._gw = gateway
        self._risk = risk or RiskManager()
        self._engine = engine
        self._idempotent: dict[str, OrderStatus] = {}

    def submit(self, req: OrderRequest) -> OrderStatus:
        cid = (req.client_order_id or "").strip()
        if cid and cid in self._idempotent:
            return self._idempotent[cid]

        rc = self._risk.check_new_order(req.side, req.symbol, req.volume, req.price)
        if not rc.ok:
            st = OrderStatus(
                order_id="",
                symbol=req.symbol,
                side=req.side,
                price=req.price,
                volume=req.volume,
                filled=0,
                status="REJECTED",
                message=rc.reason,
            )
            self._emit(EVENT_ORDER_REJECT, {"request": req, "status": st, "reason": rc.reason})
            if cid:
                self._idempotent[cid] = st
            return st

        st = self._gw.place_order(req)
        self._emit(EVENT_ORDER, {"request": req, "status": st})
        if st.status == "FILLED":
            self._emit(
                EVENT_TRADE,
                {
                    "order_id": st.order_id,
                    "symbol": st.symbol,
                    "side": st.side,
                    "price": st.avg_fill_price or st.price,
                    "volume": st.filled,
                },
            )
        if cid:
            self._idempotent[cid] = st
        return st

    def cancel(self, order_id: str) -> OrderStatus:
        st = self._gw.cancel_order(order_id)
        self._emit(EVENT_ORDER, {"cancel": True, "status": st})
        return st

    def _emit(self, et: str, data: dict[str, Any]) -> None:
        if self._engine is None:
            return
        try:
            self._engine.put(et, data)
        except Exception as e:
            _log.warning("event emit failed: %s", e)
