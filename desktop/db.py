"""
SQLite 本地数据层
替代 CSV 文件缓存，提供毫秒级查询。
"""
import os
import sqlite3
import json
from datetime import datetime, date
from contextlib import contextmanager

import pandas as pd

DB_PATH = os.path.join("data_cache", "quant.db")


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def get_conn():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS daily_kline (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL, pct_change REAL,
            PRIMARY KEY (code, date)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_code ON daily_kline(code);
        CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_kline(date);

        CREATE TABLE IF NOT EXISTS stock_list (
            code TEXT PRIMARY KEY,
            name TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS financial (
            code TEXT PRIMARY KEY,
            name TEXT,
            pe_dynamic REAL, pb REAL,
            total_mv REAL, circ_mv REAL,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS board_stocks (
            board TEXT NOT NULL,
            code TEXT NOT NULL,
            PRIMARY KEY (board, code)
        );
        CREATE INDEX IF NOT EXISTS idx_board ON board_stocks(board);

        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT, name TEXT,
            entry_date TEXT, entry_price REAL,
            shares INTEGER, stop_loss REAL,
            cost REAL, notes TEXT,
            status TEXT DEFAULT 'open',
            exit_date TEXT, exit_price REAL, exit_reason TEXT, pnl REAL
        );

        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS predictions (
            code TEXT NOT NULL,
            strategy TEXT NOT NULL,
            predict_date TEXT NOT NULL,
            horizon TEXT NOT NULL,
            predicted_price REAL,
            actual_price REAL,
            PRIMARY KEY (code, strategy, predict_date, horizon)
        );
        CREATE INDEX IF NOT EXISTS idx_pred_code ON predictions(code);
        """)


def upsert_daily(code: str, df: pd.DataFrame):
    if df is None or df.empty:
        return
    rows = []
    for _, r in df.iterrows():
        rows.append((
            str(code),
            str(pd.Timestamp(r.get("date")).strftime("%Y-%m-%d") if pd.notna(r.get("date")) else ""),
            float(r.get("open", 0) or 0),
            float(r.get("high", 0) or 0),
            float(r.get("low", 0) or 0),
            float(r.get("close", 0) or 0),
            float(r.get("volume", 0) or 0),
            float(r.get("amount", 0) or 0),
            float(r.get("pct_change", 0) or 0),
        ))
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_kline VALUES (?,?,?,?,?,?,?,?,?)", rows
        )


def get_daily(code: str) -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM daily_kline WHERE code=? ORDER BY date",
            conn, params=(str(code),), parse_dates=["date"],
        )
    return df


def upsert_stock_list(df: pd.DataFrame):
    if df is None or df.empty:
        return
    ts = datetime.now().isoformat()
    rows = [(str(r["code"]), str(r.get("name", "")), ts) for _, r in df.iterrows()]
    with get_conn() as conn:
        conn.executemany("INSERT OR REPLACE INTO stock_list VALUES (?,?,?)", rows)


def get_stock_list_db() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query("SELECT code, name FROM stock_list", conn)


def upsert_board(board_name: str, codes: list[str]):
    with get_conn() as conn:
        conn.execute("DELETE FROM board_stocks WHERE board=?", (board_name,))
        conn.executemany(
            "INSERT INTO board_stocks VALUES (?,?)",
            [(board_name, c) for c in codes],
        )


def get_board_stocks_db(board_name: str) -> list[str]:
    with get_conn() as conn:
        cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board_name,))
        return [r[0] for r in cur.fetchall()]


def get_all_boards_db() -> dict[str, int]:
    with get_conn() as conn:
        cur = conn.execute("SELECT board, COUNT(*) FROM board_stocks GROUP BY board ORDER BY board")
        return {r[0]: r[1] for r in cur.fetchall()}


def kv_set(key: str, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
            (key, json.dumps(value, ensure_ascii=False), datetime.now().isoformat()),
        )


def kv_get(key: str, default=None):
    with get_conn() as conn:
        cur = conn.execute("SELECT value FROM kv_store WHERE key=?", (key,))
        row = cur.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                return row[0]
    return default
