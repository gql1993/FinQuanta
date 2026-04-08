"""命令行自检：Paper 下单 / 撤单 / 持仓 / 成交（python -m desktop.engine.smoke_paper）。"""
from __future__ import annotations

from desktop.broker_gateway import OrderRequest
from desktop.engine.main_engine import MainEngine


def main() -> None:
    eng = MainEngine()
    print("mode:", eng.mode)
    print("balance0:", eng.account.get_balance())

    buy = OrderRequest(symbol="600000", side="BUY", price=10.0, volume=100, order_type="MARKET")
    st1 = eng.send_order(buy)
    print("buy:", st1)
    print("positions:", eng.account.get_positions_dict())
    print("balance1:", eng.account.get_balance())

    lim = OrderRequest(
        symbol="600000",
        side="BUY",
        price=0.0,
        volume=200,
        order_type="LIMIT",
        limit_price=9.0,
    )
    st2 = eng.send_order(lim)
    print("limit:", st2)
    c = eng.cancel_order(st2.order_id)
    print("cancel:", c)

    sell = OrderRequest(symbol="600000", side="SELL", price=10.5, volume=100, order_type="MARKET")
    st3 = eng.send_order(sell)
    print("sell:", st3)
    print("positions_end:", eng.account.get_positions_dict())
    print("snapshot:", eng.snapshot())


if __name__ == "__main__":
    main()
