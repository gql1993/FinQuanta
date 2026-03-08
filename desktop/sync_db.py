"""
将现有 CSV/JSON 缓存数据同步到 SQLite 数据库。
客户端启动时自动执行，保证 DB 有数据可用。
"""
import os
import json
import glob

import pandas as pd

from desktop.db import (
    init_db, get_conn, upsert_daily, upsert_stock_list, upsert_board, kv_set,
)

CACHE_DIR = "data_cache"


def sync_all():
    """一键同步全部本地缓存到 SQLite。"""
    init_db()
    n_daily = _sync_daily_klines()
    n_stocks = _sync_stock_list()
    n_boards = _sync_boards()
    _sync_portfolio()
    return {"daily": n_daily, "stocks": n_stocks, "boards": n_boards}


def _sync_stock_list() -> int:
    path = os.path.join(CACHE_DIR, "stock_list.csv")
    if not os.path.exists(path):
        return 0
    try:
        df = pd.read_csv(path, dtype={"code": str})
        if df.empty or "code" not in df.columns:
            return 0
        if "name" not in df.columns:
            df["name"] = df["code"]
        upsert_stock_list(df[["code", "name"]])
        return len(df)
    except Exception:
        return 0


def _sync_daily_klines() -> int:
    pattern = os.path.join(CACHE_DIR, "daily_*.csv")
    files = glob.glob(pattern)
    count = 0
    for fpath in files:
        fname = os.path.basename(fpath)
        code = fname.replace("daily_", "").replace(".csv", "")
        if not code.isdigit() or len(code) != 6:
            continue
        try:
            df = pd.read_csv(fpath)
            if df.empty or "close" not in df.columns:
                continue
            upsert_daily(code, df)
            count += 1
        except Exception:
            continue
    return count


def _sync_boards() -> int:
    builtin_path = os.path.join(CACHE_DIR, "board_builtin.json")
    builtin = {}
    if os.path.exists(builtin_path):
        try:
            with open(builtin_path, "r", encoding="utf-8") as f:
                builtin = json.load(f)
        except Exception:
            pass

    count = 0
    for bn, codes in builtin.items():
        if codes:
            upsert_board(bn, codes)
            count += 1

    pattern = os.path.join(CACHE_DIR, "board_*.json")
    for fpath in glob.glob(pattern):
        fname = os.path.basename(fpath)
        if fname == "board_builtin.json":
            continue
        bn = fname.replace("board_", "").replace(".json", "")
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                codes = json.load(f)
            if isinstance(codes, list) and codes:
                upsert_board(bn, codes)
                count += 1
        except Exception:
            continue
    return count


def _sync_portfolio():
    path = "portfolio.json"
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            pf = json.load(f)
        kv_set("portfolio_raw", pf)
    except Exception:
        pass


if __name__ == "__main__":
    result = sync_all()
    print(f"同步完成: 日线 {result['daily']} 只, 股票列表 {result['stocks']} 只, 板块 {result['boards']} 个")
