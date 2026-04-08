"""
账户服务：封装网关资金与持仓查询，返回稳定 dict / 域模型。
"""
from __future__ import annotations

from typing import Any

from desktop.broker_gateway import BrokerGateway, PositionSnapshot


class AccountService:
    def __init__(self, gateway: BrokerGateway, account_id: str = ""):
        self._gateway = gateway
        self._account_id = account_id

    def get_balance(self) -> dict[str, Any]:
        return self._gateway.query_balance(self._account_id)

    def get_positions(self) -> list[PositionSnapshot]:
        return self._gateway.query_positions(self._account_id)

    def get_positions_dict(self) -> list[dict[str, Any]]:
        rows = []
        for p in self.get_positions():
            rows.append(
                {
                    "account_id": p.account_id,
                    "symbol": p.symbol,
                    "volume": p.volume,
                    "available": p.available,
                    "avg_price": p.avg_price,
                    "market_price": p.market_price,
                    "pnl": p.pnl,
                }
            )
        return rows
