"""
自定义仓：自动买入选股雷达 Top3，跟踪多周期实际表现。
"""
import os
import json
import sqlite3
import numpy as np
from datetime import datetime, date, timedelta

DB_PATH = os.path.join("data_cache", "quant.db")


def _init_tracking_table():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS custom_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT, name TEXT, board TEXT,
        buy_date TEXT, buy_price REAL, shares INTEGER, score INTEGER,
        price_5d REAL, price_20d REAL, price_60d REAL, price_120d REAL,
        pnl_5d REAL, pnl_20d REAL, pnl_60d REAL, pnl_120d REAL,
        last_calibrated TEXT,
        status TEXT DEFAULT 'tracking'
    )
    """)
    conn.commit()
    conn.close()


_init_tracking_table()


def auto_buy_top3_from_scan() -> list[str]:
    """
    从选股雷达最近扫描结果中取评分 Top3，自动买入自定义仓。
    """
    from desktop.ai_portfolio import buy, get_state, check_trading_time

    conn = sqlite3.connect(DB_PATH, timeout=5)

    # 读取扫描结果
    cur = conn.execute("SELECT value FROM kv_store WHERE key='last_scan_results'")
    row = cur.fetchone()
    if not row:
        conn.close()
        return ["无扫描结果，请先在选股雷达执行扫描"]

    try:
        candidates = json.loads(row[0])
    except Exception:
        conn.close()
        return ["扫描结果解析失败"]

    # 按评分排序取 Top3
    candidates.sort(key=lambda x: int(x.get("评分", "0")), reverse=True)
    top3 = candidates[:3]

    if not top3:
        conn.close()
        return ["扫描结果为空"]

    state = get_state("custom")
    existing_codes = {p["code"] for p in state["positions"]}

    results = []
    for c in top3:
        code = c.get("代码", "")
        name = c.get("名称", "")
        price_str = c.get("价格", "0")
        score = int(c.get("评分", "0"))
        board = c.get("板块", "")

        try:
            price = float(price_str.replace(",", ""))
        except (ValueError, TypeError):
            continue

        if not code or price <= 0:
            continue

        if code in existing_codes:
            results.append(f"{code} {name} 已在仓中，跳过")
            continue

        # 计算买入股数（均分资金，100股整数倍）
        available = state["cash"]
        per_stock = available / max(3 - len(state["positions"]), 1)
        shares = int(per_stock / price / 100) * 100
        if shares < 100:
            shares = 100

        stop_loss = round(price * 0.92, 2)
        msg = buy("custom", code, name, price, shares, stop_loss,
                   f"雷达Top3 评分{score}")
        results.append(msg)

        # 记录跟踪
        conn.execute(
            "INSERT INTO custom_tracking (code,name,board,buy_date,buy_price,shares,score) "
            "VALUES (?,?,?,?,?,?,?)",
            (code, name, board, date.today().isoformat(), price, shares, score),
        )
        state = get_state("custom")
        existing_codes.add(code)

    conn.commit()
    conn.close()
    return results if results else ["Top3 已全部在仓中"]


def auto_buy_board_top3(board_name: str) -> list[str]:
    """
    从指定板块中取评分 Top3 买入自定义仓。
    """
    from desktop.ai_portfolio import buy, get_state
    from desktop.ai_trader import _compute_strategy_scores

    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board_name,))
    codes = [r[0] for r in cur.fetchall()]

    names = {}
    try:
        cur_n = conn.execute("SELECT code, name FROM stock_list")
        names = {r[0]: r[1] for r in cur_n.fetchall()}
    except Exception:
        pass

    scored = []
    for code in codes[:60]:
        cur2 = conn.execute(
            "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 260",
            (code,),
        )
        rows = cur2.fetchall()
        if len(rows) < 50:
            continue
        rows = rows[::-1]
        closes = np.array([r[0] for r in rows])
        highs = np.array([r[1] for r in rows])
        lows = np.array([r[2] for r in rows])
        vols = np.array([r[3] for r in rows])
        scores = _compute_strategy_scores(code, closes, highs, lows, vols)
        scored.append((code, names.get(code, ""), float(closes[-1]), scores["score"], board_name))

    conn.close()
    scored.sort(key=lambda x: x[3], reverse=True)
    top3 = scored[:3]

    state = get_state("custom")
    existing = {p["code"] for p in state["positions"]}

    results = []
    conn2 = sqlite3.connect(DB_PATH, timeout=5)
    for code, name, price, score, board in top3:
        if code in existing:
            results.append(f"{code} {name} 已在仓中")
            continue
        if price <= 0:
            continue

        available = state["cash"]
        per_stock = available / max(3 - len(state["positions"]), 1)
        shares = int(per_stock / price / 100) * 100
        if shares < 100:
            shares = 100

        stop_loss = round(price * 0.92, 2)
        msg = buy("custom", code, name, price, shares, stop_loss,
                   f"板块{board}Top3 评分{score}")
        results.append(msg)

        conn2.execute(
            "INSERT INTO custom_tracking (code,name,board,buy_date,buy_price,shares,score) "
            "VALUES (?,?,?,?,?,?,?)",
            (code, name, board, date.today().isoformat(), price, shares, score),
        )
        state = get_state("custom")
        existing.add(code)

    conn2.commit()
    conn2.close()
    return results if results else ["Top3 已在仓中"]


def calibrate_tracking() -> list[dict]:
    """
    校准跟踪记录：对比买入后 5日/20日/60日/120日 的实际价格和收益。
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.execute(
        "SELECT id, code, buy_date, buy_price FROM custom_tracking WHERE status='tracking'"
    )
    rows = cur.fetchall()

    results = []
    today = date.today()

    for tid, code, buy_date, buy_price in rows:
        if buy_price <= 0:
            continue

        cur2 = conn.execute(
            "SELECT date, close FROM daily_kline WHERE code=? AND date>=? ORDER BY date",
            (code, buy_date),
        )
        klines = cur2.fetchall()
        if not klines:
            continue

        updates = {}
        for days, col_price, col_pnl in [
            (5, "price_5d", "pnl_5d"),
            (20, "price_20d", "pnl_20d"),
            (60, "price_60d", "pnl_60d"),
            (120, "price_120d", "pnl_120d"),
        ]:
            if len(klines) > days:
                actual_price = klines[days][1]
                pnl = (actual_price / buy_price - 1) * 100
                updates[col_price] = round(actual_price, 2)
                updates[col_pnl] = round(pnl, 2)

        if updates:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            vals = list(updates.values()) + [today.isoformat(), tid]
            conn.execute(
                f"UPDATE custom_tracking SET {set_clause}, last_calibrated=? WHERE id=?",
                vals,
            )

        entry = {"code": code, "buy_date": buy_date, "buy_price": buy_price}
        entry.update(updates)
        results.append(entry)

    conn.commit()
    conn.close()
    return results


def get_tracking_summary() -> list[dict]:
    """获取所有跟踪记录（含已校准的多周期收益）。"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cur = conn.execute("""
        SELECT code, name, board, buy_date, buy_price, shares, score,
               pnl_5d, pnl_20d, pnl_60d, pnl_120d, last_calibrated
        FROM custom_tracking ORDER BY buy_date DESC
    """)
    results = []
    for r in cur.fetchall():
        results.append({
            "code": r[0], "name": r[1], "board": r[2],
            "buy_date": r[3], "buy_price": r[4], "shares": r[5], "score": r[6],
            "pnl_5d": r[7], "pnl_20d": r[8], "pnl_60d": r[9], "pnl_120d": r[10],
            "calibrated": r[11],
        })
    conn.close()
    return results
