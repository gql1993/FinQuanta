"""
AI 双模拟仓：完全自主仓(full_auto) + AI推荐仓(auto)
四个仓完全独立，各自 100 万初始资金。
遵守 A 股真实交易时间：工作日 9:15-11:30、13:00-15:00，排除法定节假日。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, date, timedelta

from desktop.data_access import get_kv_json, get_repo, set_kv_json

_log = logging.getLogger("ai_portfolio")
from desktop.order_bus import GLOBAL_EVENT_BUS


def _safe_float(v, default: float = 1_000_000.0) -> float:
    if v is None:
        return default
    try:
        x = float(v)
        return default if x != x else x  # NaN -> default
    except (TypeError, ValueError):
        return default

_CN_HOLIDAYS = {
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

_WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

_INIT_SQLITE = """
CREATE TABLE IF NOT EXISTS ai_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL DEFAULT 'auto',
    code TEXT NOT NULL,
    name TEXT,
    entry_date TEXT,
    entry_price REAL,
    shares INTEGER,
    stop_loss REAL,
    status TEXT DEFAULT 'open',
    exit_date TEXT,
    exit_price REAL,
    exit_reason TEXT,
    pnl REAL
);
CREATE TABLE IF NOT EXISTS ai_trade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL DEFAULT 'auto',
    timestamp TEXT,
    action TEXT,
    code TEXT,
    detail TEXT
);
"""


def is_trading_day(d: date | None = None) -> bool:
    if d is None:
        d = date.today()
    if d.weekday() >= 5:
        return False
    return d not in _CN_HOLIDAYS


def is_trading_hours() -> bool:
    now = datetime.now()
    if not is_trading_day(now.date()):
        return False
    t = now.hour * 100 + now.minute
    return (915 <= t <= 1130) or (1300 <= t <= 1500)


def next_trading_day(d: date | None = None) -> date:
    if d is None:
        d = date.today()
    nxt = d + timedelta(days=1)
    while not is_trading_day(nxt):
        nxt += timedelta(days=1)
    return nxt


def check_trading_time() -> str | None:
    """校验当前是否允许交易。返回 None 表示允许，否则返回拒绝原因。"""
    today = date.today()
    now = datetime.now()
    t = now.hour * 100 + now.minute

    if not is_trading_day(today):
        nxt = next_trading_day(today)
        return (
            f"今天 {today.strftime('%m-%d')} {_WEEKDAY_CN[today.weekday()]} 非交易日，"
            f"下一个交易日: {nxt.strftime('%Y-%m-%d')}"
        )
    if t < 915:
        return f"未到开盘时间（当前 {now.strftime('%H:%M')}，开盘 9:15）"
    if 1131 <= t < 1300:
        return f"午间休市（当前 {now.strftime('%H:%M')}，13:00 恢复）"
    if t > 1500:
        return f"已收盘（当前 {now.strftime('%H:%M')}，15:00 收盘）"
    return None


def _init_table() -> None:
    from api_server.config import settings

    repo = get_repo()
    if settings.db_backend != "postgres":
        repo.executescript(_INIT_SQLITE)
    for key in [
        "ai_auto_cash",
        "ai_manual_cash",
        "ai_full_auto_cash",
        "ai_custom_cash",
        "ai_quantum_cash",
    ]:
        if get_kv_json(key, None) is None:
            set_kv_json(key, {"cash": 1_000_000.0, "initial": 1_000_000.0})


_init_table()


def _cash_key(mode: str) -> str:
    _MAP = {
        "auto": "ai_auto_cash",
        "manual": "ai_manual_cash",
        "full_auto": "ai_full_auto_cash",
        "custom": "ai_custom_cash",
        "quantum": "ai_quantum_cash",
    }
    return _MAP.get(mode, "ai_manual_cash")


def get_state(mode: str = "auto") -> dict:
    """获取指定仓的状态。"""
    repo = get_repo()
    raw = get_kv_json(_cash_key(mode), {"cash": 1_000_000.0, "initial": 1_000_000.0})
    if isinstance(raw, dict):
        cash_data = {
            "cash": _safe_float(raw.get("cash"), 1_000_000.0),
            "initial": _safe_float(raw.get("initial"), 1_000_000.0),
        }
    else:
        cash_data = {"cash": 1_000_000.0, "initial": 1_000_000.0}

    cur2 = repo.fetchall(
        "SELECT id, code, name, entry_date, entry_price, shares, stop_loss "
        "FROM ai_positions WHERE mode=? AND status='open'",
        (mode,),
    )
    positions = [
        {"id": r[0], "code": r[1], "name": r[2], "entry_date": r[3],
         "entry_price": r[4], "shares": r[5], "stop_loss": r[6]}
        for r in cur2
    ]

    cur3 = repo.fetchall(
        "SELECT code, name, entry_date, entry_price, exit_date, exit_price, shares, pnl, exit_reason "
        "FROM ai_positions WHERE mode=? AND status='closed' ORDER BY exit_date DESC LIMIT 50",
        (mode,),
    )
    closed = [
        {"code": r[0], "name": r[1], "entry_date": r[2], "entry_price": r[3],
         "exit_date": r[4], "exit_price": r[5], "shares": r[6], "pnl": r[7], "reason": r[8]}
        for r in cur3
    ]

    return {
        "cash": cash_data["cash"],
        "initial_capital": cash_data["initial"],
        "positions": positions,
        "closed_trades": closed,
        "mode": mode,
    }


def buy(mode: str, code: str, name: str, price: float, shares: int, stop_loss: float, reason: str = "") -> str:
    reject = check_trading_time()
    if reject:
        return f"⛔ 非交易时间，买入被拒绝: {reject}"

    if len(code) != 6 or not code.isdigit():
        return f"⛔ 无效股票代码: {code}"
    if shares <= 0 or shares % 100 != 0:
        return f"⛔ 买入数量必须为100的整数倍，当前: {shares}"
    if price <= 0:
        return f"⛔ 价格异常: {price}"

    try:
        repo = get_repo()
        row = repo.fetchone(
            "SELECT close, date FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
            (code,),
        )
        if row and row[0] > 0:
            kline_close = row[0]
            deviation = abs(price - kline_close) / kline_close
            if deviation > 0.15:
                _log.warning(
                    f"价格偏差过大: {code} 买入价{price:.2f} vs 最新收盘{kline_close:.2f} "
                    f"(偏差{deviation:.0%})，使用收盘价替代"
                )
                price = kline_close
    except Exception:
        pass

    state = get_state(mode)
    try:
        from desktop.portfolio_tracker import apply_slippage
        price = apply_slippage(price, is_buy=True)
    except Exception:
        pass

    cost = price * shares * 1.0003

    if cost > state["cash"]:
        max_shares = int(state["cash"] / (price * 1.0003) / 100) * 100
        if max_shares <= 0:
            return f"资金不足: 需要 ¥{cost:,.0f}，可用 ¥{state['cash']:,.0f}"
        shares = max_shares
        cost = price * shares * 1.0003
        _log.info(f"资金不足，自动减仓: {code} → {shares}股")

    repo = get_repo()
    repo.execute(
        "INSERT INTO ai_positions (mode,code,name,entry_date,entry_price,shares,stop_loss,status) VALUES (?,?,?,?,?,?,?,?)",
        (mode, code, name, date.today().isoformat(), price, shares, stop_loss, "open"),
    )
    new_cash = state["cash"] - cost
    set_kv_json(
        _cash_key(mode),
        {"cash": round(new_cash, 2), "initial": state["initial_capital"]},
    )
    repo.execute(
        "INSERT INTO ai_trade_log (mode,timestamp,action,code,detail) VALUES (?,?,?,?,?)",
        (mode, datetime.now().isoformat(), "BUY", code, f"{shares}股@{price:.2f} {reason}"),
    )
    _mode_labels = {"auto": "AI推荐仓", "full_auto": "完全自主仓",
                    "manual": "AI推荐仓", "custom": "自定义仓", "quantum": "量子仓"}
    label = _mode_labels.get(mode, mode)
    GLOBAL_EVENT_BUS.publish(
        "ORDER_FILLED",
        "ai_portfolio",
        {"mode": mode, "action": "BUY", "code": code, "name": name, "price": price, "shares": shares},
    )
    return f"[{label}] 买入: {code} {name} {shares}股 @ ¥{price:.2f}"


def sell(mode: str, code: str, price: float, reason: str = "") -> str:
    reject = check_trading_time()
    if reject:
        return f"⛔ 非交易时间，卖出被拒绝: {reject}"

    repo = get_repo()
    row = repo.fetchone(
        "SELECT id, entry_price, shares, entry_date FROM ai_positions WHERE mode=? AND code=? AND status='open'",
        (mode, code),
    )
    if not row:
        return f"未持有 {code}"

    pos_id, entry_price, shares, entry_date = row

    if entry_date == date.today().isoformat():
        return f"⛔ T+1限制: {code} 今日买入，最早明日可卖出"

    revenue = price * shares * (1 - 0.0003 - 0.001)
    pnl = revenue - entry_price * shares

    repo.execute(
        "UPDATE ai_positions SET status='closed', exit_date=?, exit_price=?, exit_reason=?, pnl=? WHERE id=?",
        (date.today().isoformat(), price, reason, round(pnl, 2), pos_id),
    )
    state = get_state(mode)
    new_cash = state["cash"] + revenue
    set_kv_json(
        _cash_key(mode),
        {"cash": new_cash, "initial": state["initial_capital"]},
    )
    repo.execute(
        "INSERT INTO ai_trade_log (mode,timestamp,action,code,detail) VALUES (?,?,?,?,?)",
        (mode, datetime.now().isoformat(), "SELL", code, f"{shares}股@{price:.2f} pnl={pnl:+.2f} {reason}"),
    )
    _labels = {"auto": "AI推荐仓", "manual": "AI推荐仓", "full_auto": "完全自主仓"}
    label = _labels.get(mode, mode)
    GLOBAL_EVENT_BUS.publish(
        "ORDER_FILLED",
        "ai_portfolio",
        {"mode": mode, "action": "SELL", "code": code, "price": price, "shares": shares, "pnl": round(pnl, 2)},
    )
    return f"[{label}] 卖出: {code} {shares}股 @ ¥{price:.2f}，盈亏 ¥{pnl:+,.2f}"


def get_log(mode: str = "auto", limit: int = 30) -> list[dict]:
    repo = get_repo()
    cur = repo.fetchall(
        "SELECT timestamp, action, code, detail FROM ai_trade_log WHERE mode=? ORDER BY id DESC LIMIT ?",
        (mode, limit),
    )
    return [{"time": r[0], "action": r[1], "code": r[2], "detail": r[3]} for r in cur]


def _get_trade_count(mode: str) -> int:
    repo = get_repo()
    row = repo.fetchone(
        "SELECT COUNT(1) FROM ai_trade_log WHERE mode=? AND UPPER(action) IN ('BUY','SELL')",
        (mode,),
    )
    try:
        return int(row[0]) if row and row[0] is not None else 0
    except (TypeError, ValueError):
        return 0


def get_comparison() -> dict:
    """获取四个仓的对比数据。"""
    auto = get_state("auto")
    manual = get_state("manual")
    full_auto = get_state("full_auto")
    custom = get_state("custom")
    quantum = get_state("quantum")

    def _calc(state, prices, mode):
        mv = sum(prices.get(p["code"], p["entry_price"]) * p["shares"] for p in state["positions"])
        cost = sum(p["entry_price"] * p["shares"] for p in state["positions"])
        unrealized_pnl = mv - cost
        eq = state["cash"] + mv
        ic = state["initial_capital"]
        if ic and ic > 0:
            ret = (eq - ic) / ic * 100
        else:
            ret = 0.0
        closed = state["closed_trades"]
        realized_pnl = sum(t.get("pnl", 0) for t in closed)
        wins = sum(1 for t in closed if t.get("pnl", 0) > 0)
        total_trades = _get_trade_count(mode)
        open_wins = sum(1 for p in state["positions"]
                        if prices.get(p["code"], p["entry_price"]) > p["entry_price"])
        closed_trade_count = len(closed)
        open_position_count = len(state["positions"])
        win_rate = wins / closed_trade_count * 100 if closed_trade_count > 0 else 0
        open_win_rate = open_wins / open_position_count * 100 if open_position_count > 0 else 0
        return {
            "equity": eq, "return_pct": ret, "cash": state["cash"],
            "positions": len(state["positions"]),
            "total_trades": total_trades,
            "win_rate": win_rate,
            "open_win_rate": open_win_rate,
            "closed_trade_count": closed_trade_count,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": realized_pnl + unrealized_pnl,
        }

    prices = {}
    all_codes = set()
    for s in [auto, manual, full_auto, custom, quantum]:
        for p in s["positions"]:
            all_codes.add(p["code"])

    if all_codes:
        try:
            from desktop.realtime_data import get_realtime_quotes
            quotes = get_realtime_quotes(list(all_codes), force=True)
            for code, q in quotes.items():
                px = q.get("price", 0)
                if px and px > 0:
                    prices[code] = float(px)
        except Exception:
            pass

    missing = [c for c in all_codes if c not in prices]
    if missing:
        try:
            repo = get_repo()
            for code in missing:
                row = repo.fetchone(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
                    (code,),
                )
                if row and row[0] is not None:
                    try:
                        px = float(row[0])
                        if px > 0:
                            prices[code] = px
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass

    return {
        "auto": _calc(auto, prices, "auto"),
        "manual": _calc(manual, prices, "manual"),
        "full_auto": _calc(full_auto, prices, "full_auto"),
        "custom": _calc(custom, prices, "custom"),
        "quantum": _calc(quantum, prices, "quantum"),
        "prices": prices,
    }
