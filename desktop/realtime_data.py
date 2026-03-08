"""
实时行情数据模块
多源实时行情：新浪（秒级）+ 腾讯（分钟级）+ 东方财富（快照）
支持单股/批量查询，自动降级和缓存。
"""
import os
import json
import time
import sqlite3
import urllib.request
import logging
from datetime import datetime, date

_log = logging.getLogger("realtime_data")
DB_PATH = os.path.join("data_cache", "quant.db")

_quote_cache = {}
_CACHE_TTL = 10  # 秒级缓存


def _init_realtime_table():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS realtime_quotes (
        code TEXT PRIMARY KEY,
        name TEXT,
        price REAL, open REAL, high REAL, low REAL,
        prev_close REAL, volume REAL, amount REAL,
        bid1_price REAL, bid1_vol REAL,
        ask1_price REAL, ask1_vol REAL,
        pct_change REAL, turnover_rate REAL,
        updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS tick_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT, timestamp TEXT,
        price REAL, volume REAL, direction TEXT
    );
    CREATE TABLE IF NOT EXISTS min60_kline (
        code TEXT, datetime TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
        PRIMARY KEY (code, datetime)
    );
    """)
    conn.commit()
    conn.close()


_init_realtime_table()


def fetch_realtime_sina(codes: list[str]) -> dict[str, dict]:
    """
    新浪实时行情（秒级刷新，含五档盘口）。
    返回 {code: {name, price, open, high, low, prev_close, volume, amount, bid/ask, pct, turnover}}
    """
    if not codes:
        return {}

    symbols = []
    for code in codes:
        if code.startswith("6"):
            symbols.append(f"sh{code}")
        else:
            symbols.append(f"sz{code}")

    url = f"https://hq.sinajs.cn/list={','.join(symbols)}"
    try:
        req = urllib.request.Request(url, headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0",
        })
        text = urllib.request.urlopen(req, timeout=8).read().decode("gbk", errors="ignore")
    except Exception as e:
        _log.warning(f"sina realtime failed: {e}")
        return {}

    results = {}
    for line in text.strip().split("\n"):
        if '="' not in line:
            continue
        var_name = line.split("=")[0].split("_")[-1]
        code = var_name[2:]
        data = line.split('"')[1].split(",")
        if len(data) < 32:
            continue

        try:
            prev_close = float(data[2])
            price = float(data[3])
            pct = (price / prev_close - 1) * 100 if prev_close > 0 else 0

            results[code] = {
                "name": data[0],
                "open": float(data[1]),
                "prev_close": prev_close,
                "price": price,
                "high": float(data[4]),
                "low": float(data[5]),
                "volume": float(data[8]),
                "amount": float(data[9]),
                "bid1_vol": float(data[10]),
                "bid1_price": float(data[11]),
                "bid2_price": float(data[13]),
                "bid3_price": float(data[15]),
                "ask1_vol": float(data[20]),
                "ask1_price": float(data[21]),
                "ask2_price": float(data[23]),
                "ask3_price": float(data[25]),
                "pct_change": round(pct, 2),
                "date": data[30],
                "time": data[31],
            }
        except (ValueError, IndexError):
            continue

    return results


def fetch_realtime_tencent(codes: list[str]) -> dict[str, dict]:
    """腾讯实时行情（备用源）。"""
    if not codes:
        return {}

    symbols = []
    for code in codes:
        symbols.append(f"sh{code}" if code.startswith("6") else f"sz{code}")

    url = f"https://qt.gtimg.cn/q={','.join(symbols)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=8).read().decode("gbk", errors="ignore")
    except Exception:
        return {}

    results = {}
    for line in text.strip().split(";"):
        if "~" not in line:
            continue
        parts = line.split("~")
        if len(parts) < 45:
            continue
        try:
            code = parts[2]
            price = float(parts[3])
            prev_close = float(parts[4])
            pct = (price / prev_close - 1) * 100 if prev_close > 0 else 0
            results[code] = {
                "name": parts[1],
                "price": price,
                "prev_close": prev_close,
                "open": float(parts[5]),
                "high": float(parts[33]) if parts[33] else price,
                "low": float(parts[34]) if parts[34] else price,
                "volume": float(parts[6]) * 100,
                "amount": float(parts[37]) * 10000 if parts[37] else 0,
                "pct_change": round(pct, 2),
                "turnover_rate": float(parts[38]) if len(parts) > 38 and parts[38] else 0,
            }
        except (ValueError, IndexError):
            continue
    return results


def get_realtime_quotes(codes: list[str], force: bool = False) -> dict[str, dict]:
    """
    获取实时行情（带缓存 + 多源降级）。
    优先新浪 → 腾讯备用 → SQLite 缓存。
    """
    now = time.time()
    if not force:
        cached = {}
        miss = []
        for code in codes:
            c = _quote_cache.get(code)
            if c and now - c["_ts"] < _CACHE_TTL:
                cached[code] = c
            else:
                miss.append(code)
        if not miss:
            return cached
        codes_to_fetch = miss
    else:
        cached = {}
        codes_to_fetch = list(codes)

    results = fetch_realtime_sina(codes_to_fetch)
    if len(results) < len(codes_to_fetch) * 0.5:
        backup = fetch_realtime_tencent(
            [c for c in codes_to_fetch if c not in results]
        )
        results.update(backup)

    # 存入缓存和 SQLite
    ts = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=5)
    for code, q in results.items():
        q["_ts"] = now
        _quote_cache[code] = q
        try:
            conn.execute(
                "INSERT OR REPLACE INTO realtime_quotes "
                "(code,name,price,open,high,low,prev_close,volume,amount,"
                "bid1_price,bid1_vol,ask1_price,ask1_vol,pct_change,turnover_rate,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (code, q.get("name", ""), q.get("price", 0),
                 q.get("open", 0), q.get("high", 0), q.get("low", 0),
                 q.get("prev_close", 0), q.get("volume", 0), q.get("amount", 0),
                 q.get("bid1_price", 0), q.get("bid1_vol", 0),
                 q.get("ask1_price", 0), q.get("ask1_vol", 0),
                 q.get("pct_change", 0), q.get("turnover_rate", 0), ts),
            )
        except Exception:
            pass
    conn.commit()

    # 从 SQLite 补全仍缺失的
    for code in codes_to_fetch:
        if code not in results:
            try:
                cur = conn.execute(
                    "SELECT name,price,prev_close,pct_change FROM realtime_quotes WHERE code=?",
                    (code,),
                )
                row = cur.fetchone()
                if row:
                    results[code] = {
                        "name": row[0], "price": row[1], "prev_close": row[2],
                        "pct_change": row[3], "_ts": now, "_source": "cache",
                    }
            except Exception:
                pass

    conn.close()
    results.update(cached)
    return results


def fetch_min60_kline(code: str, count: int = 120) -> list[dict]:
    """获取60分钟K线（腾讯源）并存入 SQLite。"""
    prefix = "sh" if code.startswith("6") else "sz"
    symbol = f"{prefix}{code}"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param={symbol},m60,,{count}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gu.qq.com/",
        })
        text = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        obj = json.loads(text)
        data = obj.get("data", {}).get(symbol, {})
        rows = data.get("m60", data.get("qfqm60", []))
    except Exception:
        return []

    results = []
    conn = sqlite3.connect(DB_PATH, timeout=5)
    for r in rows:
        if len(r) < 6:
            continue
        dt_str = str(r[0])
        item = {
            "datetime": dt_str,
            "open": float(r[1]),
            "close": float(r[2]),
            "high": float(r[3]),
            "low": float(r[4]),
            "volume": float(r[5]),
        }
        results.append(item)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO min60_kline (code,datetime,open,high,low,close,volume) "
                "VALUES (?,?,?,?,?,?,?)",
                (code, dt_str, item["open"], item["high"], item["low"], item["close"], item["volume"]),
            )
        except Exception:
            pass
    conn.commit()
    conn.close()
    return results


def get_min60_kline(code: str) -> list[dict]:
    """读取60分钟K线（先查本地，不足则拉取）。"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cur = conn.execute(
        "SELECT datetime,open,high,low,close,volume FROM min60_kline WHERE code=? ORDER BY datetime",
        (code,),
    )
    rows = [
        {"datetime": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
        for r in cur.fetchall()
    ]
    conn.close()

    if len(rows) < 20:
        rows = fetch_min60_kline(code, 120)
    return rows
