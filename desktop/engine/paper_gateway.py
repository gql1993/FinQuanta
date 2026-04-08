"""
模拟/paper 撮合网关：资金、持仓、订单、成交、撤单（单账户、单线程安全假设）。

可与 kv_store 同步快照（键：paper_gateway_state / paper_gateway_orders）。
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from desktop import data_access
from desktop.broker_gateway import OrderRequest, OrderStatus, PositionSnapshot
from desktop.domain_models import OrderFill

KV_STATE = "paper_gateway_state"
KV_ORDERS = "paper_gateway_order_history"


@dataclass
class _Pos:
    volume: int = 0
    available: int = 0
    avg_price: float = 0.0


class PaperGateway:
    """
    Paper 网关：
    - MARKET：立即按给定 price 全部成交
    - LIMIT：挂单 SUBMITTED，可撤单；不自动撮合（后续可接 last 价触发）
    """

    def __init__(
        self,
        account_id: str = "paper",
        initial_cash: float = 1_000_000.0,
        persist: bool = True,
    ):
        self._lock = threading.Lock()
        self._account_id = account_id
        self._initial = float(initial_cash)
        self._cash = float(initial_cash)
        self._positions: dict[str, _Pos] = {}
        self._orders: dict[str, OrderStatus] = {}
        self._open_limit: dict[str, OrderRequest] = {}
        self._fills: list[OrderFill] = []
        self._seq = 0
        self._persist = persist
        self._load()

    def _next_id(self) -> str:
        self._seq += 1
        return f"PAPER-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._seq:06d}"

    def _load(self) -> None:
        if not self._persist:
            return
        raw = data_access.get_kv_json(KV_STATE, None)
        if not raw or not isinstance(raw, dict):
            return
        try:
            self._cash = float(raw.get("cash", self._initial))
            self._initial = float(raw.get("initial_capital", self._initial))
            self._seq = int(raw.get("order_seq", 0))
            pos = raw.get("positions") or {}
            self._positions = {}
            for sym, p in pos.items():
                if isinstance(p, dict):
                    self._positions[sym] = _Pos(
                        volume=int(p.get("volume", 0)),
                        available=int(p.get("available", p.get("volume", 0))),
                        avg_price=float(p.get("avg_price", 0)),
                    )
        except Exception:
            pass

    def _save(self) -> None:
        if not self._persist:
            return
        pos = {
            k: {"volume": v.volume, "available": v.available, "avg_price": v.avg_price}
            for k, v in self._positions.items()
        }
        payload = {
            "cash": self._cash,
            "initial_capital": self._initial,
            "positions": pos,
            "order_seq": self._seq,
            "account_id": self._account_id,
        }
        data_access.set_kv_json(KV_STATE, payload)

    def _record_fill(self, fill: OrderFill) -> None:
        self._fills.append(fill)
        hist = [asdict(f) for f in self._fills[-500:]]
        try:
            data_access.set_kv_json(KV_ORDERS, hist)
        except Exception:
            pass

    def place_order(self, req: OrderRequest) -> OrderStatus:
        with self._lock:
            oid = self._next_id()
            side = req.side.upper()
            ot = (req.order_type or "MARKET").upper()
            sym = str(req.symbol).strip()

            if ot == "LIMIT":
                lim = float(req.limit_price or req.price or 0.0)
                st = OrderStatus(
                    order_id=oid,
                    symbol=sym,
                    side=side,
                    price=lim,
                    volume=req.volume,
                    filled=0,
                    status="SUBMITTED",
                    timestamp=datetime.now().isoformat(),
                    message="limit order accepted",
                    avg_fill_price=0.0,
                )
                self._orders[oid] = st
                self._open_limit[oid] = req
                self._save()
                return st

            # MARKET
            px = float(req.price)
            vol = int(req.volume)
            if vol <= 0:
                st = OrderStatus(
                    order_id=oid,
                    symbol=sym,
                    side=side,
                    price=px,
                    volume=vol,
                    filled=0,
                    status="REJECTED",
                    timestamp=datetime.now().isoformat(),
                    message="invalid volume",
                    avg_fill_price=0.0,
                )
                self._orders[oid] = st
                return st

            if side == "BUY":
                need = px * vol
                if need > self._cash + 1e-6:
                    st = OrderStatus(
                        order_id=oid,
                        symbol=sym,
                        side=side,
                        price=px,
                        volume=vol,
                        filled=0,
                        status="REJECTED",
                        timestamp=datetime.now().isoformat(),
                        message="insufficient cash",
                        avg_fill_price=0.0,
                    )
                    self._orders[oid] = st
                    return st
                self._cash -= need
                p = self._positions.get(sym) or _Pos()
                new_vol = p.volume + vol
                p.avg_price = (p.avg_price * p.volume + px * vol) / new_vol if new_vol else px
                p.volume = new_vol
                p.available = new_vol
                self._positions[sym] = p
            elif side == "SELL":
                p = self._positions.get(sym) or _Pos()
                if vol > p.available:
                    st = OrderStatus(
                        order_id=oid,
                        symbol=sym,
                        side=side,
                        price=px,
                        volume=vol,
                        filled=0,
                        status="REJECTED",
                        timestamp=datetime.now().isoformat(),
                        message="insufficient position",
                        avg_fill_price=0.0,
                    )
                    self._orders[oid] = st
                    return st
                self._cash += px * vol
                p.volume -= vol
                p.available -= vol
                if p.volume <= 0:
                    self._positions.pop(sym, None)
                else:
                    self._positions[sym] = p
            else:
                st = OrderStatus(
                    order_id=oid,
                    symbol=sym,
                    side=side,
                    price=px,
                    volume=vol,
                    filled=0,
                    status="REJECTED",
                    timestamp=datetime.now().isoformat(),
                    message="invalid side",
                    avg_fill_price=0.0,
                )
                self._orders[oid] = st
                return st

            fid = f"FILL-{oid}"
            fill = OrderFill(
                fill_id=fid,
                order_id=oid,
                symbol=sym,
                side=side,
                price=px,
                volume=vol,
                timestamp=datetime.now().isoformat(),
            )
            self._record_fill(fill)

            st = OrderStatus(
                order_id=oid,
                symbol=sym,
                side=side,
                price=px,
                volume=vol,
                filled=vol,
                status="FILLED",
                timestamp=datetime.now().isoformat(),
                message="filled",
                avg_fill_price=px,
            )
            self._orders[oid] = st
            self._save()
            return st

    def cancel_order(self, order_id: str) -> OrderStatus:
        with self._lock:
            if order_id in self._open_limit:
                del self._open_limit[order_id]
                prev = self._orders.get(order_id)
                sym = prev.symbol if prev else ""
                side = prev.side if prev else ""
                price = prev.price if prev else 0.0
                vol = prev.volume if prev else 0
                st = OrderStatus(
                    order_id=order_id,
                    symbol=sym,
                    side=side,
                    price=price,
                    volume=vol,
                    filled=0,
                    status="CANCELLED",
                    timestamp=datetime.now().isoformat(),
                    message="cancelled",
                    avg_fill_price=0.0,
                )
                self._orders[order_id] = st
                self._save()
                return st
            prev = self._orders.get(order_id)
            if prev:
                return OrderStatus(
                    order_id=order_id,
                    symbol=prev.symbol,
                    side=prev.side,
                    price=prev.price,
                    volume=prev.volume,
                    filled=prev.filled,
                    status=prev.status,
                    timestamp=datetime.now().isoformat(),
                    message="not cancellable",
                    avg_fill_price=prev.avg_fill_price,
                )
            return OrderStatus(
                order_id=order_id,
                symbol="",
                side="",
                price=0.0,
                volume=0,
                status="REJECTED",
                timestamp=datetime.now().isoformat(),
                message="unknown order",
                avg_fill_price=0.0,
            )

    def query_positions(self, account_id: str = "") -> list[PositionSnapshot]:
        with self._lock:
            out: list[PositionSnapshot] = []
            for sym, p in self._positions.items():
                if p.volume <= 0:
                    continue
                out.append(
                    PositionSnapshot(
                        account_id=self._account_id,
                        symbol=sym,
                        volume=p.volume,
                        available=p.available,
                        avg_price=p.avg_price,
                        market_price=p.avg_price,
                        pnl=0.0,
                    )
                )
            return out

    def query_balance(self, account_id: str = "") -> dict:
        with self._lock:
            equity = self._cash
            for sym, p in self._positions.items():
                equity += p.avg_price * p.volume
            return {
                "account_id": self._account_id,
                "cash": round(self._cash, 2),
                "available": round(self._cash, 2),
                "equity": round(equity, 2),
                "initial_capital": self._initial,
            }

    def query_order(self, order_id: str) -> OrderStatus | None:
        with self._lock:
            return self._orders.get(order_id)

    def recent_fills(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(f) for f in self._fills[-limit:]]
