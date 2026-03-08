"""
每日持仓检查
获取最新价格，检查止损/止盈/时间止损，输出操作建议。
"""
from datetime import datetime, date
from portfolio import (
    load_portfolio, save_portfolio, sell_stock,
    get_latest_prices, print_portfolio_report,
)


def check_risk(state, live_prices):
    """检查所有持仓的风控条件"""
    alerts = []

    for pos in state.positions:
        code = pos["code"]
        price = live_prices.get(code)
        if price is None:
            continue

        entry = pos["entry_price"]
        stop = pos["stop_loss"]
        pnl_pct = (price - entry) / entry

        # 更新最高价
        if price > pos.get("highest_price", 0):
            pos["highest_price"] = price

        highest = pos.get("highest_price", entry)
        drawdown_from_peak = (highest - price) / highest if highest > 0 else 0

        # 持仓天数
        entry_date = datetime.strptime(pos["entry_date"], "%Y-%m-%d").date()
        days_held = (date.today() - entry_date).days

        # 1. 硬止损 8%
        if price <= stop:
            alerts.append({
                "code": code, "name": pos["name"],
                "type": "STOP_LOSS", "urgency": "!!!",
                "msg": f"触发硬止损: 现价 {price:.2f} <= 止损 {stop:.2f}，亏损 {pnl_pct:.1%}",
                "action": f"立即卖出 {code}",
            })

        # 2. 渐进式止损
        elif pnl_pct >= 0.20:
            new_stop = round(entry * 1.15, 2)
            if price <= new_stop:
                alerts.append({
                    "code": code, "name": pos["name"],
                    "type": "PROGRESSIVE_STOP", "urgency": "!!",
                    "msg": f"盈利回落: 曾盈利{pnl_pct:.1%}，现价 {price:.2f} 触发渐进止损 {new_stop:.2f}",
                    "action": f"卖出 {code} 锁定利润",
                })
            elif not pos.get("partial_sold"):
                alerts.append({
                    "code": code, "name": pos["name"],
                    "type": "PARTIAL_PROFIT", "urgency": "+",
                    "msg": f"盈利 {pnl_pct:.1%}，达到部分止盈目标 20%",
                    "action": f"可考虑卖出 {code} 一半仓位",
                })

        elif pnl_pct >= 0.10:
            new_stop = round(entry * 1.05, 2)
            if pos["stop_loss"] < new_stop:
                alerts.append({
                    "code": code, "name": pos["name"],
                    "type": "RAISE_STOP", "urgency": "~",
                    "msg": f"盈利 {pnl_pct:.1%}，建议上移止损至 {new_stop:.2f}（+5%）",
                    "action": f"更新 {code} 止损价",
                })

        elif pnl_pct >= 0.05:
            new_stop = entry
            if pos["stop_loss"] < new_stop:
                alerts.append({
                    "code": code, "name": pos["name"],
                    "type": "RAISE_STOP", "urgency": "~",
                    "msg": f"盈利 {pnl_pct:.1%}，建议上移止损至保本价 {new_stop:.2f}",
                    "action": f"更新 {code} 止损价",
                })

        # 3. 从峰值回撤 >12%
        if drawdown_from_peak >= 0.12 and pnl_pct > 0:
            alerts.append({
                "code": code, "name": pos["name"],
                "type": "PEAK_DRAWDOWN", "urgency": "!!",
                "msg": f"从高点 {highest:.2f} 回撤 {drawdown_from_peak:.1%}，保护利润",
                "action": f"卖出 {code}",
            })

        # 4. 时间止损 (20 个交易日约 28 天)
        if days_held >= 28 and pnl_pct < 0.02:
            alerts.append({
                "code": code, "name": pos["name"],
                "type": "TIME_STOP", "urgency": "!",
                "msg": f"持有 {days_held} 天仅涨 {pnl_pct:.1%}，考虑时间止损",
                "action": f"卖出 {code}，资金换股",
            })

    return alerts


def main():
    state = load_portfolio()

    if not state.positions:
        print("  模拟仓为空，请先运行 init_portfolio.py 建仓")
        return

    codes = [p["code"] for p in state.positions]
    print(f"获取 {len(codes)} 只持仓股票最新价格...\n")
    prices = get_latest_prices(codes)

    # 打印持仓报告
    print_portfolio_report(state, prices)

    # 风控检查
    alerts = check_risk(state, prices)

    if alerts:
        print(f"  {'=' * 60}")
        print(f"  风控预警 ({len(alerts)} 条)")
        print(f"  {'=' * 60}\n")

        for a in sorted(alerts, key=lambda x: {"!!!": 0, "!!": 1, "!": 2, "+": 3, "~": 4}.get(x["urgency"], 5)):
            print(f"  [{a['urgency']}] {a['code']} {a['name']}")
            print(f"      {a['msg']}")
            print(f"      操作: {a['action']}")
            print()
    else:
        print(f"  [OK] 所有持仓正常，无风控预警\n")

    save_portfolio(state)


if __name__ == "__main__":
    main()
