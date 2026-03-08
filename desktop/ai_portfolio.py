"""
AI 双模拟仓：自主仓(auto) + 推荐仓(manual)
两个仓完全独立，各自 100 万初始资金。
遵守 A 股真实交易时间：工作日 9:15-11:30、13:00-15:00，排除法定节假日。
"""
import os
import json
import sqlite3
from datetime import datetime, date, timedelta

DB_PATH = os.path.join("data_cache", "quant.db")

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


def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_table():
    conn = _get_conn()
    conn.executescript("""
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
    """)
    # 初始化四个仓的资金
    for key in ["ai_auto_cash", "ai_manual_cash", "ai_full_auto_cash", "ai_custom_cash"]:
        cur = conn.execute("SELECT value FROM kv_store WHERE key=?", (key,))
        if not cur.fetchone():
            conn.execute(
                "INSERT INTO kv_store VALUES (?,?,?)",
                (key, json.dumps({"cash": 1_000_000.0, "initial": 1_000_000.0}), datetime.now().isoformat()),
            )
    conn.commit()
    conn.close()


_init_table()


def _cash_key(mode: str) -> str:
    _MAP = {"auto": "ai_auto_cash", "manual": "ai_manual_cash",
            "full_auto": "ai_full_auto_cash", "custom": "ai_custom_cash"}
    return _MAP.get(mode, "ai_manual_cash")


def get_state(mode: str = "auto") -> dict:
    """获取指定仓的状态。"""
    conn = _get_conn()
    cur = conn.execute("SELECT value FROM kv_store WHERE key=?", (_cash_key(mode),))
    row = cur.fetchone()
    cash_data = json.loads(row[0]) if row else {"cash": 1_000_000.0, "initial": 1_000_000.0}

    cur2 = conn.execute(
        "SELECT id, code, name, entry_date, entry_price, shares, stop_loss "
        "FROM ai_positions WHERE mode=? AND status='open'",
        (mode,),
    )
    positions = [
        {"id": r[0], "code": r[1], "name": r[2], "entry_date": r[3],
         "entry_price": r[4], "shares": r[5], "stop_loss": r[6]}
        for r in cur2.fetchall()
    ]

    cur3 = conn.execute(
        "SELECT code, name, entry_date, entry_price, exit_date, exit_price, shares, pnl, exit_reason "
        "FROM ai_positions WHERE mode=? AND status='closed' ORDER BY exit_date DESC LIMIT 50",
        (mode,),
    )
    closed = [
        {"code": r[0], "name": r[1], "entry_date": r[2], "entry_price": r[3],
         "exit_date": r[4], "exit_price": r[5], "shares": r[6], "pnl": r[7], "reason": r[8]}
        for r in cur3.fetchall()
    ]
    conn.close()

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

    state = get_state(mode)
    cost = price * shares * 1.0003
    if cost > state["cash"]:
        return f"资金不足: 需要 ¥{cost:,.0f}，可用 ¥{state['cash']:,.0f}"

    conn = _get_conn()
    conn.execute(
        "INSERT INTO ai_positions (mode,code,name,entry_date,entry_price,shares,stop_loss,status) VALUES (?,?,?,?,?,?,?,?)",
        (mode, code, name, date.today().isoformat(), price, shares, stop_loss, "open"),
    )
    new_cash = state["cash"] - cost
    conn.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
        (_cash_key(mode), json.dumps({"cash": new_cash, "initial": state["initial_capital"]}),
         datetime.now().isoformat()),
    )
    conn.execute(
        "INSERT INTO ai_trade_log (mode,timestamp,action,code,detail) VALUES (?,?,?,?,?)",
        (mode, datetime.now().isoformat(), "BUY", code, f"{shares}股@{price:.2f} {reason}"),
    )
    conn.commit()
    conn.close()
    label = "自主仓" if mode == "auto" else "推荐仓"
    return f"[{label}] 买入: {code} {name} {shares}股 @ ¥{price:.2f}"


def sell(mode: str, code: str, price: float, reason: str = "") -> str:
    reject = check_trading_time()
    if reject:
        return f"⛔ 非交易时间，卖出被拒绝: {reject}"

    conn = _get_conn()
    cur = conn.execute(
        "SELECT id, entry_price, shares, entry_date FROM ai_positions WHERE mode=? AND code=? AND status='open'",
        (mode, code),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return f"未持有 {code}"

    pos_id, entry_price, shares, entry_date = row

    # T+1: 当天买入不能卖出
    if entry_date == date.today().isoformat():
        conn.close()
        return f"⛔ T+1限制: {code} 今日买入，最早明日可卖出"

    revenue = price * shares * (1 - 0.0003 - 0.001)
    pnl = revenue - entry_price * shares

    conn.execute(
        "UPDATE ai_positions SET status='closed', exit_date=?, exit_price=?, exit_reason=?, pnl=? WHERE id=?",
        (date.today().isoformat(), price, reason, round(pnl, 2), pos_id),
    )
    state = get_state(mode)
    new_cash = state["cash"] + revenue
    conn.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
        (_cash_key(mode), json.dumps({"cash": new_cash, "initial": state["initial_capital"]}),
         datetime.now().isoformat()),
    )
    conn.execute(
        "INSERT INTO ai_trade_log (mode,timestamp,action,code,detail) VALUES (?,?,?,?,?)",
        (mode, datetime.now().isoformat(), "SELL", code, f"{shares}股@{price:.2f} pnl={pnl:+.2f} {reason}"),
    )
    conn.commit()
    conn.close()
    _labels = {"auto": "半自主仓", "manual": "推荐仓", "full_auto": "完全自主仓"}
    label = _labels.get(mode, mode)
    return f"[{label}] 卖出: {code} {shares}股 @ ¥{price:.2f}，盈亏 ¥{pnl:+,.2f}"


def get_log(mode: str = "auto", limit: int = 30) -> list[dict]:
    conn = _get_conn()
    cur = conn.execute(
        "SELECT timestamp, action, code, detail FROM ai_trade_log WHERE mode=? ORDER BY id DESC LIMIT ?",
        (mode, limit),
    )
    logs = [{"time": r[0], "action": r[1], "code": r[2], "detail": r[3]} for r in cur.fetchall()]
    conn.close()
    return logs


def get_comparison() -> dict:
    """获取四个仓的对比数据。"""
    auto = get_state("auto")
    manual = get_state("manual")
    full_auto = get_state("full_auto")
    custom = get_state("custom")

    def _calc(state, prices):
        mv = sum(prices.get(p["code"], p["entry_price"]) * p["shares"] for p in state["positions"])
        eq = state["cash"] + mv
        ret = (eq - state["initial_capital"]) / state["initial_capital"] * 100
        trades = state["closed_trades"]
        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        total = len(trades)
        return {
            "equity": eq, "return_pct": ret, "cash": state["cash"],
            "positions": len(state["positions"]),
            "total_trades": total, "win_rate": wins / total * 100 if total > 0 else 0,
            "total_pnl": sum(t.get("pnl", 0) for t in trades),
        }

    # 获取现价
    prices = {}
    try:
        conn = _get_conn()
        all_codes = set()
        for s in [auto, manual, full_auto, custom]:
            for p in s["positions"]:
                all_codes.add(p["code"])
        for code in all_codes:
            cur = conn.execute("SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1", (code,))
            row = cur.fetchone()
            if row:
                prices[code] = row[0]
        conn.close()
    except Exception:
        pass

    return {
        "auto": _calc(auto, prices),
        "manual": _calc(manual, prices),
        "full_auto": _calc(full_auto, prices),
        "custom": _calc(custom, prices),
        "prices": prices,
    }
