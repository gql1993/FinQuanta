"""
板块成分股日线数据批量补全
从腾讯 K 线接口拉取缺失股票的日线，写入 SQLite。
"""
import os
import json
import sqlite3
import urllib.request
from datetime import datetime

DB_PATH = os.path.join("data_cache", "quant.db")


def get_missing_codes(board_codes: list[str]) -> list[str]:
    """找出板块中在 SQLite 里没有日线数据的股票代码。"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    existing = set()
    cur = conn.execute("SELECT DISTINCT code FROM daily_kline")
    for row in cur.fetchall():
        existing.add(row[0])
    conn.close()
    return [c for c in board_codes if c not in existing]


def fetch_daily_tencent(code: str) -> list[tuple]:
    """从腾讯拉日线（前复权，最近 600 天）。"""
    if not code.isdigit() or len(code) != 6:
        return []
    prefix = "sh" if code.startswith("6") else "sz"
    symbol = f"{prefix}{code}"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,600,qfq"
    try:
        req = urllib.request.Request(url, headers={
            "Referer": "https://gu.qq.com/",
            "User-Agent": "Mozilla/5.0",
        })
        text = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        obj = json.loads(text)
        data = obj.get("data", {}).get(symbol, {})
        rows_raw = data.get("qfqday") or data.get("day") or []
        result = []
        for r in rows_raw:
            if len(r) < 6:
                continue
            result.append((
                str(code), str(r[0]),
                float(r[1]), float(r[3]), float(r[4]), float(r[2]),
                float(r[5]), 0, 0,
            ))
        return result
    except Exception:
        return []


def sync_board_stocks(board_name: str = None, max_fetch: int = 50,
                      progress_callback=None) -> dict:
    """补全指定板块（或全部板块）的日线数据。"""
    builtin_path = os.path.join("data_cache", "board_builtin.json")
    all_codes = set()

    conn = sqlite3.connect(DB_PATH, timeout=5)
    if board_name and board_name.strip():
        cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board_name,))
    else:
        cur = conn.execute("SELECT DISTINCT code FROM board_stocks")
    all_codes = {r[0] for r in cur.fetchall()}
    conn.close()

    if not all_codes and os.path.exists(builtin_path):
        with open(builtin_path, "r", encoding="utf-8") as f:
            builtin = json.load(f)
        if board_name and board_name.strip():
            all_codes = set(builtin.get(board_name, []))
        else:
            for codes_list in builtin.values():
                all_codes.update(codes_list)

    missing = get_missing_codes(list(all_codes))
    to_fetch = missing[:max_fetch]

    fetched = 0
    failed = 0
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")

    for i, code in enumerate(to_fetch):
        if progress_callback:
            progress_callback(i, len(to_fetch), code)
        rows = fetch_daily_tencent(code)
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO daily_kline VALUES (?,?,?,?,?,?,?,?,?)", rows
            )
            fetched += 1
        else:
            failed += 1

    conn.commit()
    conn.close()

    return {
        "total_missing": len(missing),
        "fetched": fetched,
        "failed": failed,
        "remaining": len(missing) - len(to_fetch),
    }


if __name__ == "__main__":
    import sys
    board = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].strip() else None
    max_n = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    def _progress(i, total, code):
        print(f"  [{i+1}/{total}] {code}...")

    result = sync_board_stocks(board, max_fetch=max_n, progress_callback=_progress)
    print(f"补全完成: 拉取 {result['fetched']} 只, 失败 {result['failed']}, 剩余 {result['remaining']}")
