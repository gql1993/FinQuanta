"""
板块成分股日线数据批量补全
从腾讯 K 线接口拉取缺失股票的日线，经统一 data_access 写入 DB。
"""
import os
import json
import urllib.request
from datetime import datetime

from desktop.data_access import (
    get_repo,
    insert_ignore_board_pairs,
    insert_ignore_stock_list_rows,
    set_kv_json,
    upsert_daily_kline_rows,
)


def get_missing_codes(board_codes: list[str]) -> list[str]:
    """找出板块中没有日线数据的股票代码。"""
    repo = get_repo()
    existing = {r[0] for r in repo.fetchall("SELECT DISTINCT code FROM daily_kline", ())}
    return [c for c in board_codes if c not in existing]


def fetch_index_daily(code: str) -> list[tuple]:
    """从腾讯拉取指数日线数据（沪深300、上证指数等）。"""
    # 指数代码：000001/000300/000016 → sh，399001/399006 → sz
    if code.startswith("39"):
        symbol = f"sz{code}"
    else:
        symbol = f"sh{code}"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,600,"
    try:
        req = urllib.request.Request(url, headers={
            "Referer": "https://gu.qq.com/",
            "User-Agent": "Mozilla/5.0",
        })
        text = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        obj = json.loads(text)
        data = obj.get("data", {}).get(symbol, {})
        rows_raw = data.get("day") or data.get("qfqday") or []
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


def refresh_latest_kline(codes: list[str] = None, max_codes: int = 500,
                         threads: int = 8,
                         progress_callback=None,
                         stale_after_days: int = 2) -> dict:
    """
    并发刷新指定股票的最新日线数据（多线程，速度更快）。
    默认拉取最近 600 天（覆盖所有缺失），INSERT OR REPLACE 自动去重。
    """
    import threading
    import queue as _queue

    from datetime import date as _date, timedelta
    stale_after_days = max(0, int(stale_after_days))
    cutoff = (_date.today() - timedelta(days=stale_after_days)).strftime("%Y-%m-%d")

    repo = get_repo()
    if codes is None:
        codes = [r[0] for r in repo.fetchall("SELECT DISTINCT code FROM daily_kline", ())]

    latest_map = {}
    for row in repo.fetchall("SELECT code, MAX(date) FROM daily_kline GROUP BY code", ()):
        d = row[1]
        latest_map[row[0]] = str(d)[:10] if d else ""

    codes_to_fetch = [
        c for c in codes
        if c.isdigit() and len(c) == 6 and latest_map.get(c, "") < cutoff
    ]
    codes_to_fetch = codes_to_fetch[:max_codes]

    if not codes_to_fetch:
        return {"codes_processed": 0, "fetched": 0, "rows_updated": 0, "failed": 0}

    result_q = _queue.Queue()

    def _fetch_worker(chunk):
        for code in chunk:
            sym_prefix = "sh" if code.startswith("6") else "sz"
            symbol = f"{sym_prefix}{code}"
            url = (
                f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                f"?param={symbol},day,,,600,qfq"
            )
            try:
                req = urllib.request.Request(url, headers={
                    "Referer": "https://gu.qq.com/",
                    "User-Agent": "Mozilla/5.0",
                })
                text = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
                obj = json.loads(text)
                data = obj.get("data", {}).get(symbol, {})
                rows_raw = data.get("qfqday") or data.get("day") or []
                rows = []
                for r in rows_raw:
                    if len(r) >= 6:
                        rows.append((
                            str(code), str(r[0]),
                            float(r[1]), float(r[3]), float(r[4]), float(r[2]),
                            float(r[5]), 0, 0,
                        ))
                result_q.put((code, rows))
            except Exception:
                result_q.put((code, []))
            import time as _time
            _time.sleep(0.02)

    # Split into thread chunks
    n = len(codes_to_fetch)
    chunk_size = max(1, (n + threads - 1) // threads)
    ts = []
    for i in range(0, n, chunk_size):
        t = threading.Thread(target=_fetch_worker, args=(codes_to_fetch[i:i + chunk_size],), daemon=True)
        t.start()
        ts.append(t)

    fetched = failed = rows_updated = 0
    done = 0
    pending = []

    while done < n:
        try:
            code, rows = result_q.get(timeout=30)
        except _queue.Empty:
            break
        done += 1
        if rows:
            pending.extend(rows)
            fetched += 1
            rows_updated += len(rows)
        else:
            failed += 1
        if progress_callback:
            progress_callback(done, n, code)
        if len(pending) >= 3000:
            upsert_daily_kline_rows(pending)
            pending.clear()

    if pending:
        upsert_daily_kline_rows(pending)

    return {
        "codes_processed": n,
        "fetched": fetched,
        "rows_updated": rows_updated,
        "failed": failed,
    }


def sync_board_stocks(board_name: str = None, max_fetch: int = 50,
                      progress_callback=None) -> dict:
    """补全指定板块（或全部板块）的日线数据。"""
    builtin_path = os.path.join("data_cache", "board_builtin.json")
    all_codes = set()

    repo = get_repo()
    if board_name and board_name.strip():
        all_codes = {r[0] for r in repo.fetchall("SELECT code FROM board_stocks WHERE board=?", (board_name,))}
    else:
        all_codes = {r[0] for r in repo.fetchall("SELECT DISTINCT code FROM board_stocks", ())}

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

    for i, code in enumerate(to_fetch):
        if progress_callback:
            progress_callback(i, len(to_fetch), code)
        rows = fetch_daily_tencent(code)
        if rows:
            upsert_daily_kline_rows(rows)
            fetched += 1
        else:
            failed += 1

    return {
        "total_missing": len(missing),
        "fetched": fetched,
        "failed": failed,
        "remaining": len(missing) - len(to_fetch),
    }


# ═══════════════════════════════════════════════════
#  CSV/JSON → SQLite 迁移（原 sync_db.py 功能，合并于此）
# ═══════════════════════════════════════════════════

def sync_csv_to_db() -> dict:
    """将本地 CSV/JSON 缓存同步到数据库（启动时调用）。"""
    cache = "data_cache"
    result = {"daily": 0, "stocks": 0, "boards": 0}

    repo = get_repo()
    sl_path = os.path.join(cache, "stock_list.csv")
    if os.path.exists(sl_path):
        try:
            import csv

            with open(sl_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = [(r.get("code", ""), r.get("name", ""), "") for r in reader if r.get("code")]
            if rows:
                insert_ignore_stock_list_rows(rows)
                result["stocks"] = len(rows)
        except Exception:
            pass

    builtin_path = os.path.join(cache, "board_builtin.json")
    if os.path.exists(builtin_path):
        try:
            with open(builtin_path, "r", encoding="utf-8") as f:
                boards = json.load(f)
            for bn, codes in boards.items():
                if codes:
                    insert_ignore_board_pairs([(bn, c) for c in codes])
                    result["boards"] += 1
        except Exception:
            pass

    pf_path = "portfolio.json"
    if os.path.exists(pf_path):
        try:
            with open(pf_path, "r", encoding="utf-8") as f:
                pf = json.load(f)
            existing = repo.fetchone("SELECT 1 FROM kv_store WHERE key=?", ("manual_portfolio",))
            if not existing:
                set_kv_json("manual_portfolio", pf)
        except Exception:
            pass

    return result


if __name__ == "__main__":
    import sys
    board = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].strip() else None
    max_n = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    def _progress(i, total, code):
        print(f"  [{i+1}/{total}] {code}...")

    result = sync_board_stocks(board, max_fetch=max_n, progress_callback=_progress)
    print(f"补全完成: 拉取 {result['fetched']} 只, 失败 {result['failed']}, 剩余 {result['remaining']}")
