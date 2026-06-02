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


def _to_float(value, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "-", "--", "nan", "None"):
            return default
        text = str(value).replace(",", "").replace("%", "").strip()
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def sync_financial_csv_to_db(path: str | None = None) -> dict:
    """Sync data_cache/financial.csv into the financial table."""
    import csv

    csv_path = path or os.path.join("data_cache", "financial.csv")
    result = {"financial": 0, "path": csv_path, "missing": False}
    if not os.path.exists(csv_path):
        result["missing"] = True
        return result

    rows: list[tuple] = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            code = str(
                r.get("code")
                or r.get("代码")
                or r.get("股票代码")
                or r.get("SECURITY_CODE")
                or ""
            ).strip()
            if "." in code:
                code = code.split(".")[0]
            code = code.zfill(6) if code.isdigit() and len(code) < 6 else code
            if not (code.isdigit() and len(code) == 6):
                continue
            name = str(r.get("name") or r.get("名称") or r.get("股票简称") or r.get("SECURITY_NAME_ABBR") or "")
            pe = _to_float(r.get("pe_dynamic") or r.get("动态市盈率") or r.get("市盈率") or r.get("PE"))
            pb = _to_float(r.get("pb") or r.get("市净率") or r.get("PB"))
            total_mv = _to_float(r.get("total_mv") or r.get("总市值") or r.get("TOTAL_MARKET_CAP"))
            circ_mv = _to_float(r.get("circ_mv") or r.get("流通市值") or r.get("CIRC_MARKET_CAP"))
            rows.append((code, name, pe, pb, total_mv, circ_mv, datetime.now().isoformat()))

    if rows:
        repo = get_repo()
        repo.executemany(
            "INSERT OR REPLACE INTO financial "
            "(code, name, pe_dynamic, pb, total_mv, circ_mv, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            rows,
        )
    result["financial"] = len(rows)
    return result


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


def collect_kline_refresh_codes(repo=None) -> list[str]:
    """Collect stock codes for scheduled K-line refresh (positions first, then board universe)."""
    from desktop.data_access import get_kv_json

    repo = repo or get_repo()
    priority_codes: list[str] = []
    seen: set[str] = set()

    def _add(code: str):
        c = str(code or "").strip()
        if len(c) == 6 and c.isdigit() and c not in seen:
            seen.add(c)
            priority_codes.append(c)

    try:
        for r in repo.fetchall(
            "SELECT DISTINCT code FROM ai_positions WHERE status='open'", ()
        ):
            _add(r[0])
    except Exception:
        pass
    try:
        mp = get_kv_json("manual_portfolio", {}) or {}
        for p in mp.get("positions", []):
            _add(p.get("code", ""))
    except Exception:
        pass
    try:
        for r in repo.fetchall("SELECT DISTINCT code FROM board_stocks", ()):
            _add(r[0])
    except Exception:
        pass
    return priority_codes


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
    result = {"daily": 0, "stocks": 0, "boards": 0, "financial": 0}

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

    try:
        fin = sync_financial_csv_to_db(os.path.join(cache, "financial.csv"))
        result["financial"] = int(fin.get("financial", 0) or 0)
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
