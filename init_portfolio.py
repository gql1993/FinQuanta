"""
初始化模拟仓: 100 万资金
基于 SEPA 筛选结果 + 当前市场环境进行建仓

当前市场状态: 偏弱（分布日=7）
Minervini 原则: 弱市仓位 ≤ 30%，优先选突破确认股
"""
from portfolio import (
    PortfolioState, save_portfolio, buy_stock,
    calculate_position_size, get_latest_prices,
    print_portfolio_report,
)


# 第一梯队: 已突破枢纽点（优先买入）
TIER1_BREAKOUT = [
    {"code": "603881", "name": "数据港",     "rs": 90, "pivot": 43.53, "notes": "VCP突破,收缩4次,数据中心龙头"},
    {"code": "002975", "name": "博智林份",   "rs": 91, "pivot": 84.96, "notes": "VCP突破,收缩4次,智能制造"},
    {"code": "688001", "name": "华兴源创",   "rs": 80, "pivot": 35.06, "notes": "站上枢纽,收缩5次,半导体检测"},
]

# 第二梯队: 接近枢纽点（少量试探）
TIER2_NEAR_PIVOT = [
    {"code": "002150", "name": "通润泰源",   "rs": 96, "pivot": 29.15, "notes": "距枢纽-2.6%,RS极强"},
    {"code": "002925", "name": "盈趣科技",   "rs": 73, "pivot": 21.91, "notes": "距枢纽-1.0%,极度缩量0.61"},
]

# 第三梯队: 观察名单（暂不买入）
WATCHLIST = [
    {"code": "300604", "name": "长城科技",   "rs": 98, "pivot": 140.10, "notes": "RS98,缩量,等右侧"},
    {"code": "688498", "name": "源杰科技",   "rs": 98, "pivot": 830.50, "notes": "RS98,高价股,距枢纽远"},
    {"code": "688195", "name": "腾景科技",   "rs": 99, "pivot": 247.00, "notes": "RS99全市场最强,基底构建"},
    {"code": "300467", "name": "迅游科技",   "rs": 86, "pivot": 34.85,  "notes": "距枢纽-3.5%,关注突破"},
    {"code": "001218", "name": "联合实业",   "rs": 77, "pivot": 26.65,  "notes": "紧密收盘,距枢纽-3.2%"},
    {"code": "001332", "name": "威装股份",   "rs": 78, "pivot": 60.36,  "notes": "收缩7次,量比0.66"},
    {"code": "300648", "name": "星云股份",   "rs": 71, "pivot": 61.15,  "notes": "触及枢纽,缩量"},
    {"code": "601717", "name": "中建海峡",   "rs": 79, "pivot": 25.76,  "notes": "收缩6次,距枢纽-4.5%"},
]


def main():
    print("=" * 70)
    print("  SEPA 模拟仓初始化  |  资金: 100 万元")
    print("=" * 70)

    state = PortfolioState(
        initial_capital=1_000_000.0,
        cash=1_000_000.0,
    )

    # 获取最新价格
    all_codes = [s["code"] for s in TIER1_BREAKOUT + TIER2_NEAR_PIVOT]
    print(f"\n[1/3] 获取 {len(all_codes)} 只股票最新价格...")
    prices = get_latest_prices(all_codes)

    for code, price in prices.items():
        print(f"  {code}: {price:.2f}")

    if not prices:
        print("  无法获取价格，使用估算价格建仓")
        est_prices = {
            "603881": 42.80, "002975": 83.91, "688001": 35.06,
            "002150": 28.40, "002925": 21.69,
        }
        prices = est_prices

    # -----------------------------------------------------------
    # 建仓策略:
    #   市场偏弱 → 总仓位控制 30% (约30万)
    #   第一梯队 3 只各 ~8 万 = 24 万
    #   第二梯队 2 只各 ~3 万 = 6 万
    # -----------------------------------------------------------
    print(f"\n[2/3] 按 Minervini 弱市原则建仓（总仓位 ≤ 30%）...\n")
    print(f"  策略: 市场环境偏弱，控制总仓位约 30%")
    print(f"  第一梯队（突破型）: 3 只，每只 ~8 万")
    print(f"  第二梯队（待突破型）: 2 只，每只 ~3 万\n")

    total_equity = state.cash

    # 第一梯队: 突破型，每只约 8%
    for stock in TIER1_BREAKOUT:
        code = stock["code"]
        price = prices.get(code)
        if price is None:
            print(f"  [跳过] {code} {stock['name']}: 无价格数据")
            continue

        target_amount = total_equity * 0.08
        shares = int(target_amount / price)
        shares = (shares // 100) * 100
        if shares < 100:
            shares = 100

        stop_loss_pct = 0.08
        ok = buy_stock(
            state, code, stock["name"], price, shares,
            stop_loss_pct=stop_loss_pct,
            rs=stock["rs"], pivot=stock["pivot"],
            notes=stock["notes"],
        )
        if ok:
            actual_price = round(price * 1.001, 2)
            stop = round(actual_price * 0.92, 2)
            risk = actual_price * shares * stop_loss_pct
            print(f"  [买入] {code} {stock['name']}  "
                  f"价格 {actual_price}  股数 {shares}  "
                  f"金额 {actual_price * shares:,.0f}  "
                  f"止损 {stop}  风险 {risk:,.0f}")

    # 第二梯队: 接近枢纽，每只约 3%
    for stock in TIER2_NEAR_PIVOT:
        code = stock["code"]
        price = prices.get(code)
        if price is None:
            print(f"  [跳过] {code} {stock['name']}: 无价格数据")
            continue

        target_amount = total_equity * 0.03
        shares = int(target_amount / price)
        shares = (shares // 100) * 100
        if shares < 100:
            shares = 100

        ok = buy_stock(
            state, code, stock["name"], price, shares,
            stop_loss_pct=0.08,
            rs=stock["rs"], pivot=stock["pivot"],
            notes=stock["notes"],
        )
        if ok:
            actual_price = round(price * 1.001, 2)
            stop = round(actual_price * 0.92, 2)
            risk = actual_price * shares * 0.08
            print(f"  [买入] {code} {stock['name']}  "
                  f"价格 {actual_price}  股数 {shares}  "
                  f"金额 {actual_price * shares:,.0f}  "
                  f"止损 {stop}  风险 {risk:,.0f}")

    # 保存
    save_portfolio(state)
    print(f"\n[3/3] 持仓已保存\n")

    # 打印报告
    print_portfolio_report(state, prices)

    # 观察名单
    print(f"  --- 观察名单（暂不买入，等待右侧信号）---\n")
    for s in WATCHLIST:
        print(f"  {s['code']}  {s['name']:<8}  枢纽 {s['pivot']:>8.2f}  RS {s['rs']:>3}  {s['notes']}")

    print(f"\n  --- 后续操作指引 ---")
    print(f"  1. 每日运行 python check_portfolio.py 检查止损/止盈")
    print(f"  2. 观察名单股票突破枢纽时，运行加仓脚本")
    print(f"  3. 大盘转强后（分布日<5 + 反弹确认），可加至 60% 仓位")
    print()


if __name__ == "__main__":
    main()
