"""
模拟仓服务层
封装 portfolio.py，提供 Streamlit 友好的接口。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio import (
    PortfolioState, load_portfolio, save_portfolio,
    buy_stock, sell_stock, calculate_position_size,
    get_latest_prices, is_trading_day, next_trading_day, is_trading_hours,
    _check_trading_time,
)


def get_portfolio() -> PortfolioState:
    return load_portfolio()


def save(state: PortfolioState):
    save_portfolio(state)


def check_trading_day() -> tuple[bool, str]:
    """
    检查当前交易状态，返回 (可交易, 提示文本)。
    细分时段：盘前 / 集合竞价 / 上午盘 / 午休 / 下午盘 / 已收盘 / 非交易日
    """
    from datetime import date, datetime
    today = date.today()
    now = datetime.now()
    t = now.hour * 100 + now.minute
    weekday_cn = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    day_str = f"{today.strftime('%Y-%m-%d')} {weekday_cn[today.weekday()]}"

    if not is_trading_day(today):
        nxt = next_trading_day(today)
        return False, f"{day_str} 非交易日（下个交易日: {nxt.strftime('%m-%d')}）"

    if t < 915:
        return False, f"{day_str} 盘前（{now.strftime('%H:%M')}，09:15 集合竞价）"
    elif 915 <= t < 925:
        return True, f"{day_str} 集合竞价中（{now.strftime('%H:%M')}）"
    elif 925 <= t < 930:
        return False, f"{day_str} 集合竞价撮合（{now.strftime('%H:%M')}，09:30 开盘）"
    elif 930 <= t <= 1130:
        return True, f"{day_str} 上午盘交易中（{now.strftime('%H:%M')}）"
    elif 1130 < t < 1300:
        return False, f"{day_str} 午间休市（{now.strftime('%H:%M')}，13:00 开盘）"
    elif 1300 <= t <= 1500:
        return True, f"{day_str} 下午盘交易中（{now.strftime('%H:%M')}）"
    else:
        return False, f"{day_str} 已收盘（{now.strftime('%H:%M')}）"


def execute_buy(state: PortfolioState, code: str, name: str, price: float,
                shares: int, stop_loss_pct: float = 0.08,
                rs: float = 0, pivot: float = 0, notes: str = "") -> tuple[bool, str]:
    """执行买入，返回 (成功, 消息)"""
    result = buy_stock(state, code, name, price, shares,
                       stop_loss_pct=stop_loss_pct, rs=rs, pivot=pivot, notes=notes)
    if result is True:
        save(state)
        return True, f"买入成功: {code} {name} {shares}股 @ {price:.2f}"
    elif isinstance(result, str):
        return False, result
    return False, "买入失败"


def execute_sell(state: PortfolioState, code: str, price: float,
                 reason: str, shares: int = 0) -> tuple[bool, str]:
    """执行卖出，返回 (成功, 消息)"""
    result = sell_stock(state, code, price, reason, shares)
    if result is True:
        save(state)
        return True, f"卖出成功: {code}"
    elif isinstance(result, str):
        return False, result
    return False, f"卖出失败: 未找到 {code}"


def get_portfolio_summary(state: PortfolioState, live_prices: dict | None = None,
                          prev_close_prices: dict | None = None) -> dict:
    """
    计算持仓摘要（对标同花顺资产总览）。
    live_prices: 实时价格
    prev_close_prices: 昨日收盘价（用于计算当日盈亏）
    """
    position_value = 0.0
    total_cost = 0.0
    unrealized_pnl = 0.0
    today_pnl = 0.0

    pos_details = []
    for pos in state.positions:
        code = pos["code"]
        entry = pos["entry_price"]
        shares = pos["shares"]
        raw_current = live_prices.get(code, 0) if live_prices else 0
        current = float(raw_current) if raw_current and float(raw_current) > 0 else entry
        raw_prev = prev_close_prices.get(code, 0) if prev_close_prices else 0
        prev_c = float(raw_prev) if raw_prev and float(raw_prev) > 0 else current

        mv = current * shares
        position_value += mv
        cost = entry * shares
        total_cost += cost
        pnl = mv - cost
        unrealized_pnl += pnl
        pnl_pct = pnl / cost * 100 if cost > 0 else 0

        day_pnl = (current - prev_c) * shares
        today_pnl += day_pnl
        day_pnl_pct = (current - prev_c) / prev_c * 100 if prev_c > 0 else 0

        pos_details.append({
            "代码": code,
            "名称": pos.get("name", ""),
            "买入价": round(entry, 2),
            "现价": round(current, 2),
            "昨收": round(prev_c, 2),
            "股数": shares,
            "市值": round(mv, 2),
            "成本": round(cost, 2),
            "浮动盈亏": round(pnl, 2),
            "盈亏%": round(pnl_pct, 2),
            "当日盈亏": round(day_pnl, 2),
            "当日%": round(day_pnl_pct, 2),
            "止损": round(pos.get("stop_loss", 0), 2),
            "买入日": pos.get("entry_date", ""),
        })

    total_equity = state.cash + position_value
    total_return = (total_equity - state.initial_capital) / state.initial_capital * 100
    realized_pnl = sum(t.get("pnl", 0) for t in state.closed_trades)

    return {
        "initial_capital": state.initial_capital,
        "total_equity": round(total_equity, 2),
        "position_value": round(position_value, 2),
        "total_cost": round(total_cost, 2),
        "cash": round(state.cash, 2),
        "available_cash": round(state.cash, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "unrealized_pnl_pct": round(unrealized_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
        "today_pnl": round(today_pnl, 2),
        "realized_pnl": round(realized_pnl, 2),
        "total_pnl": round(unrealized_pnl + realized_pnl, 2),
        "total_return": round(total_return, 2),
        "position_ratio": round(position_value / total_equity * 100, 1) if total_equity > 0 else 0,
        "num_positions": len(state.positions),
        "max_positions": 8,
        "positions": pos_details,
        "closed_trades": state.closed_trades,
    }


def calc_position_size(state: PortfolioState, price: float,
                       stop_loss_pct: float = 0.08) -> int:
    """计算建议仓位"""
    total_equity = state.cash
    for p in state.positions:
        total_equity += p["entry_price"] * p["shares"]

    return calculate_position_size(state.cash, total_equity, price, stop_loss_pct)


def fetch_live_prices(state: PortfolioState) -> dict[str, float]:
    """获取所有持仓的最新价格"""
    codes = [p["code"] for p in state.positions]
    if not codes:
        return {}
    return get_latest_prices(codes)
