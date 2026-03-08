"""
模拟仓管理系统
基于 Minervini SEPA 策略的纸面交易组合管理。

功能:
  - 初始化/加载持仓
  - 买入/卖出（含佣金、印花税、滑点）
  - A股交易日校验（排除周末和法定节假日）
  - 实时获取最新价格、计算盈亏
  - 风控检查（止损、止盈、时间止损）
  - 持仓报告
"""
import json
import os
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field, asdict

import pandas as pd

from config import StrategyConfig
from data_fetcher import DataFetcher


PORTFOLIO_FILE = "portfolio.json"

_config = StrategyConfig()
COMMISSION_RATE = _config.trading_cost.commission_rate
STAMP_TAX_RATE = _config.trading_cost.stamp_tax_rate
SLIPPAGE = _config.trading_cost.slippage

# A股节假日日历：优先从外部 JSON 文件加载，回退到内置列表。
_CN_HOLIDAYS_BUILTIN = {
    date(2025, 1, 1), date(2025, 1, 28), date(2025, 1, 29), date(2025, 1, 30),
    date(2025, 1, 31), date(2025, 2, 1), date(2025, 2, 2), date(2025, 2, 3), date(2025, 2, 4),
    date(2025, 4, 4), date(2025, 4, 5), date(2025, 4, 6),
    date(2025, 5, 1), date(2025, 5, 2), date(2025, 5, 3), date(2025, 5, 4), date(2025, 5, 5),
    date(2025, 10, 1), date(2025, 10, 2), date(2025, 10, 3), date(2025, 10, 4),
    date(2025, 10, 5), date(2025, 10, 6), date(2025, 10, 7),
    date(2026, 1, 1), date(2026, 1, 2),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19),
    date(2026, 2, 20), date(2026, 2, 21), date(2026, 2, 22),
    date(2026, 4, 5), date(2026, 4, 6), date(2026, 4, 7),
    date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3), date(2026, 5, 4), date(2026, 5, 5),
    date(2026, 6, 19), date(2026, 6, 20), date(2026, 6, 21),
    date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27),
    date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4),
    date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7),
}


def _load_holidays() -> set[date]:
    """从外部 JSON 文件加载节假日列表，找不到则使用内置列表。"""
    path = _config.data.holidays_file
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
            if isinstance(items, list):
                return {date.fromisoformat(d) for d in items if isinstance(d, str)}
        except Exception:
            pass
    return set(_CN_HOLIDAYS_BUILTIN)


_CN_HOLIDAYS = _load_holidays()


def is_trading_day(d: date | None = None) -> bool:
    """判断给定日期是否为 A 股交易日（排除周末和法定节假日）"""
    if d is None:
        d = date.today()
    if d.weekday() >= 5:
        return False
    if d in _CN_HOLIDAYS:
        return False
    return True


def is_trading_hours() -> bool:
    """判断当前是否在 A 股可交易时段"""
    now = datetime.now()
    if not is_trading_day(now.date()):
        return False
    t = now.hour * 100 + now.minute
    # 集合竞价 9:15-9:25, 上午盘 9:30-11:30, 下午盘 13:00-15:00
    return (915 <= t <= 1130) or (1300 <= t <= 1500)


def _check_trading_time(force: bool = False) -> str | None:
    """
    校验当前是否允许交易，返回 None 表示允许，否则返回拒绝原因。
    A股交易时段：
      - 集合竞价: 9:15 - 9:25
      - 上午连续竞价: 9:30 - 11:30
      - 下午连续竞价: 13:00 - 15:00
    """
    if force:
        return None

    today = date.today()
    now = datetime.now()
    t = now.hour * 100 + now.minute

    if not is_trading_day(today):
        nxt = next_trading_day(today)
        return (f"今天 {today.strftime('%m-%d')} {_WEEKDAY_CN[today.weekday()]} 非交易日，"
                f"下个交易日: {nxt.strftime('%Y-%m-%d')}")

    if t < 915:
        return f"未开盘（当前 {now.strftime('%H:%M')}），A股 9:15 开始集合竞价"
    elif 1130 < t < 1300:
        return f"午间休市（当前 {now.strftime('%H:%M')}），下午盘 13:00 开始"
    elif t > 1500:
        return f"已收盘（当前 {now.strftime('%H:%M')}），A股 15:00 收盘"

    return None


def next_trading_day(d: date | None = None) -> date:
    """获取下一个交易日"""
    if d is None:
        d = date.today()
    d = d + timedelta(days=1)
    while not is_trading_day(d):
        d = d + timedelta(days=1)
    return d


def prev_trading_day(d: date | None = None) -> date:
    """获取上一个交易日"""
    if d is None:
        d = date.today()
    d = d - timedelta(days=1)
    while not is_trading_day(d):
        d = d - timedelta(days=1)
    return d


@dataclass
class PortfolioPosition:
    code: str
    name: str
    entry_date: str
    entry_price: float
    shares: int
    stop_loss: float
    cost: float  # total cost including fees
    notes: str = ""
    rs_rating: float = 0
    pivot_price: float = 0
    highest_price: float = 0
    partial_sold: bool = False


@dataclass
class PortfolioState:
    initial_capital: float = 1_000_000.0
    cash: float = 1_000_000.0
    positions: list = field(default_factory=list)
    closed_trades: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def total_cost(self) -> float:
        return sum(p["cost"] for p in self.positions)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PortfolioState":
        state = cls()
        state.initial_capital = d.get("initial_capital", 1_000_000)
        state.cash = d.get("cash", state.initial_capital)
        state.positions = d.get("positions", [])
        state.closed_trades = d.get("closed_trades", [])
        state.created_at = d.get("created_at", "")
        state.updated_at = d.get("updated_at", "")
        return state


def load_portfolio() -> PortfolioState:
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return PortfolioState.from_dict(json.load(f))
    return PortfolioState()


def save_portfolio(state: PortfolioState):
    state.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not state.created_at:
        state.created_at = state.updated_at
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)


def _validate_stock_code(code: str) -> str | None:
    """校验 A 股代码格式，返回 None 表示合法，否则返回错误信息"""
    if not code or not code.isdigit():
        return f"股票代码必须为纯数字，当前: {code}"
    if len(code) != 6:
        return f"A股代码必须为6位，当前 {code} 为{len(code)}位"
    valid_prefixes = ("00", "30", "60", "68")
    if not code.startswith(valid_prefixes):
        return f"不合法的A股代码前缀: {code}（合法: 00/30/60/68开头）"
    return None


def buy_stock(state: PortfolioState, code: str, name: str, price: float,
              shares: int, stop_loss_pct: float = 0.08,
              rs: float = 0, pivot: float = 0, notes: str = "",
              force: bool = False) -> bool | str:
    """
    买入股票。
    返回 True 成功，或错误信息字符串。
    force=True 跳过交易日检查（用于补录历史交易）。
    """
    err = _validate_stock_code(code)
    if err:
        return err

    if shares <= 0 or shares % 100 != 0:
        return f"股数必须为100的正整数倍，当前: {shares}"

    if price <= 0:
        return f"价格必须大于0，当前: {price}"

    time_err = _check_trading_time(force)
    if time_err:
        return time_err

    actual_price = round(price * (1 + SLIPPAGE), 2)
    amount = actual_price * shares
    commission = max(amount * COMMISSION_RATE, 5)
    total_cost = amount + commission

    if total_cost > state.cash:
        return f"资金不足: 需要 {total_cost:,.0f}，可用 {state.cash:,.0f}"

    stop_loss = round(actual_price * (1 - stop_loss_pct), 2)

    # 交易日使用当天日期，非交易日（force模式）也用当天
    trade_date = date.today().strftime("%Y-%m-%d")

    pos = asdict(PortfolioPosition(
        code=code,
        name=name,
        entry_date=trade_date,
        entry_price=actual_price,
        shares=shares,
        stop_loss=stop_loss,
        cost=round(total_cost, 2),
        notes=notes,
        rs_rating=rs,
        pivot_price=pivot,
        highest_price=actual_price,
    ))

    state.positions.append(pos)
    state.cash -= total_cost
    state.cash = round(state.cash, 2)
    return True


_WEEKDAY_CN = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}


def sell_stock(state: PortfolioState, code: str, price: float, reason: str,
               shares_to_sell: int = 0, force: bool = False) -> bool | str:
    """
    卖出股票，shares_to_sell=0 表示全部卖出。
    返回 True 成功，或错误信息字符串。
    """
    time_err = _check_trading_time(force)
    if time_err:
        return time_err

    pos = None
    pos_idx = -1
    for i, p in enumerate(state.positions):
        if p["code"] == code:
            pos = p
            pos_idx = i
            break

    if pos is None:
        return f"未找到持仓: {code}"

    sell_shares = shares_to_sell if shares_to_sell > 0 else pos["shares"]
    sell_shares = min(sell_shares, pos["shares"])

    actual_price = round(price * (1 - SLIPPAGE), 2)
    revenue = actual_price * sell_shares
    commission = max(revenue * COMMISSION_RATE, 5)
    stamp_tax = revenue * STAMP_TAX_RATE
    net_revenue = revenue - commission - stamp_tax

    entry_cost_portion = pos["entry_price"] * sell_shares
    pnl = net_revenue - entry_cost_portion
    pnl_pct = pnl / entry_cost_portion if entry_cost_portion > 0 else 0

    trade = {
        "code": pos["code"],
        "name": pos["name"],
        "entry_date": pos["entry_date"],
        "exit_date": date.today().strftime("%Y-%m-%d"),
        "entry_price": pos["entry_price"],
        "exit_price": actual_price,
        "shares": sell_shares,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct * 100, 2),
        "reason": reason,
    }
    state.closed_trades.append(trade)
    state.cash += round(net_revenue, 2)

    if sell_shares >= pos["shares"]:
        state.positions.pop(pos_idx)
    else:
        pos["shares"] -= sell_shares
        pos["cost"] = round(pos["entry_price"] * pos["shares"], 2)
        pos["partial_sold"] = True

    return True


def calculate_position_size(cash: float, total_equity: float, price: float,
                            stop_loss_pct: float = 0.08,
                            risk_pct: float = 0.01) -> int:
    """按 Minervini 风控计算仓位大小"""
    risk_amount = total_equity * risk_pct
    shares_by_risk = int(risk_amount / (price * stop_loss_pct))
    shares_by_risk = (shares_by_risk // 100) * 100

    max_by_cash = int(cash * 0.95 / price)
    max_by_cash = (max_by_cash // 100) * 100

    max_per_position = total_equity * 0.15
    shares_by_position = int(max_per_position / price)
    shares_by_position = (shares_by_position // 100) * 100

    return max(min(shares_by_risk, max_by_cash, shares_by_position), 100)


def get_latest_prices(codes: list[str]) -> dict[str, float]:
    """通过新浪财经 API 获取实时价格（<1秒），回退到历史收盘价"""
    import urllib.request

    prices = {}
    if not codes:
        return prices

    sina_codes = []
    code_map = {}
    for code in codes:
        if not code.isdigit() or len(code) != 6:
            continue
        prefix = "sh" if code.startswith("6") else "sz"
        sina_code = f"{prefix}{code}"
        sina_codes.append(sina_code)
        code_map[sina_code] = code

    if sina_codes:
        url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
        try:
            req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
            resp = urllib.request.urlopen(req, timeout=5)
            text = resp.read().decode("gbk", errors="ignore")
            for line in text.strip().split("\n"):
                if "=" not in line:
                    continue
                var_part, data_part = line.split("=", 1)
                sina_code = var_part.split("_")[-1]
                orig_code = code_map.get(sina_code)
                if not orig_code:
                    continue
                fields = data_part.strip('" ;\r').split(",")
                if len(fields) >= 4:
                    try:
                        current = float(fields[3])
                        if current > 0:
                            prices[orig_code] = current
                    except (ValueError, IndexError):
                        pass
        except Exception:
            pass

    # 回退
    missing = [c for c in codes if c not in prices]
    if missing:
        config = StrategyConfig()
        config.data.start_date = "20250101"
        fetcher = DataFetcher(config.data)
        for code in missing:
            try:
                df = fetcher.get_daily_data(code)
                if df is not None and not df.empty:
                    prices[code] = float(df["close"].iloc[-1])
            except Exception:
                pass
    return prices


def print_portfolio_report(state: PortfolioState, live_prices: dict[str, float] | None = None):
    """打印持仓报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'=' * 75}")
    print(f"  SEPA 模拟仓报告  |  {now}")
    print(f"{'=' * 75}")

    position_value = 0.0
    unrealized_pnl = 0.0

    if state.positions:
        print(f"\n  --- 当前持仓 ({len(state.positions)} 只) ---\n")
        print(f"  {'代码':>8}  {'名称':<8}  {'买入价':>7}  {'现价':>7}  {'股数':>6}  "
              f"{'市值':>10}  {'盈亏':>9}  {'盈亏%':>7}  {'止损':>7}  {'状态'}")
        print(f"  {'-' * 95}")

        for pos in state.positions:
            code = pos["code"]
            current = live_prices.get(code, pos["entry_price"]) if live_prices else pos["entry_price"]
            mv = current * pos["shares"]
            position_value += mv

            entry_cost = pos["entry_price"] * pos["shares"]
            pnl = mv - entry_cost
            unrealized_pnl += pnl
            pnl_pct = pnl / entry_cost * 100 if entry_cost > 0 else 0

            if current > pos.get("highest_price", current):
                pos["highest_price"] = current

            if current <= pos["stop_loss"]:
                status = "!! 触发止损"
            elif pnl_pct >= 20:
                status = "++ 可部分止盈"
            elif pnl_pct >= 10:
                status = "+ 盈利中"
            elif pnl_pct <= -5:
                status = "- 接近止损"
            else:
                status = "持有"

            pnl_str = f"{pnl:>+,.0f}"
            print(f"  {code:>8}  {pos['name']:<8}  {pos['entry_price']:>7.2f}  "
                  f"{current:>7.2f}  {pos['shares']:>6}  {mv:>10,.0f}  "
                  f"{pnl_str:>9}  {pnl_pct:>+6.1f}%  {pos['stop_loss']:>7.2f}  {status}")

    total_equity = state.cash + position_value
    total_return = (total_equity - state.initial_capital) / state.initial_capital * 100
    position_ratio = position_value / total_equity * 100 if total_equity > 0 else 0

    print(f"\n  --- 资金概览 ---\n")
    print(f"  初始资金:     {state.initial_capital:>12,.2f} 元")
    print(f"  可用现金:     {state.cash:>12,.2f} 元")
    print(f"  持仓市值:     {position_value:>12,.2f} 元")
    print(f"  总资产:       {total_equity:>12,.2f} 元")
    print(f"  浮动盈亏:     {unrealized_pnl:>+12,.2f} 元")
    print(f"  总收益率:     {total_return:>+11.2f}%")
    print(f"  仓位比例:     {position_ratio:>11.1f}%")
    print(f"  剩余可开仓:   {8 - len(state.positions):>11d} 只")

    if state.closed_trades:
        realized = sum(t["pnl"] for t in state.closed_trades)
        wins = sum(1 for t in state.closed_trades if t["pnl"] > 0)
        total_t = len(state.closed_trades)
        print(f"\n  --- 已平仓记录 ({total_t} 笔) ---\n")
        print(f"  已实现盈亏:   {realized:>+12,.2f} 元")
        print(f"  胜率:         {wins/total_t*100 if total_t else 0:>11.1f}%")

        print(f"\n  {'代码':>8}  {'名称':<8}  {'买入':>10}  {'卖出':>10}  {'盈亏':>9}  {'盈亏%':>7}  {'原因'}")
        print(f"  {'-' * 80}")
        for t in state.closed_trades[-10:]:
            print(f"  {t['code']:>8}  {t['name']:<8}  {t['entry_date']:>10}  "
                  f"{t['exit_date']:>10}  {t['pnl']:>+9,.0f}  {t['pnl_pct']:>+6.1f}%  {t['reason']}")

    print(f"\n  创建时间: {state.created_at}")
    print(f"  更新时间: {state.updated_at}")
    print(f"{'=' * 75}\n")
