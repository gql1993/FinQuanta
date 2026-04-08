"""
本地数据层：默认 SQLite；当 FINQUANTA_DB_BACKEND=postgres 时走 api_server.storage.repo。

替代 CSV 文件缓存，提供毫秒级查询。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

from api_server.config import settings

DB_PATH = os.path.join("data_cache", "quant.db")

_INIT_SQLITE = """
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

        CREATE TABLE IF NOT EXISTS system_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            source TEXT,
            category TEXT,
            level TEXT,
            title TEXT,
            detail TEXT
        );

        CREATE TABLE IF NOT EXISTS task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            task_name TEXT,
            trigger_source TEXT,
            status TEXT,
            elapsed_ms REAL,
            summary TEXT,
            detail TEXT
        );
        """


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _repo():
    from api_server.storage import repo

    return repo


def _ensure_sqlite_dir() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def get_conn():
    """与 api_server.storage.repo 共用连接（SQLite / PostgreSQL）。优先使用 desktop.data_access.get_repo()。"""
    if settings.db_backend != "postgres":
        _ensure_sqlite_dir()
    repo = _repo()
    with repo.conn() as conn:
        yield conn


def init_db() -> None:
    repo = _repo()
    if settings.db_backend == "postgres":
        sql_path = _project_root() / "infra" / "postgres_init.sql"
        repo.executescript(sql_path.read_text(encoding="utf-8"))
        return
    _ensure_sqlite_dir()
    repo.executescript(_INIT_SQLITE)


def upsert_daily(code: str, df: pd.DataFrame):
    if df is None or df.empty:
        return
    rows = []
    for _, r in df.iterrows():
        rows.append(
            (
                str(code),
                str(pd.Timestamp(r.get("date")).strftime("%Y-%m-%d") if pd.notna(r.get("date")) else ""),
                float(r.get("open", 0) or 0),
                float(r.get("high", 0) or 0),
                float(r.get("low", 0) or 0),
                float(r.get("close", 0) or 0),
                float(r.get("volume", 0) or 0),
                float(r.get("amount", 0) or 0),
                float(r.get("pct_change", 0) or 0),
            )
        )
    repo = _repo()
    if settings.db_backend == "postgres":
        sql = """
        INSERT INTO daily_kline (code, date, open, high, low, close, volume, amount, pct_change)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT (code, date) DO UPDATE SET
        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
        volume=EXCLUDED.volume, amount=EXCLUDED.amount, pct_change=EXCLUDED.pct_change
        """
        repo.executemany(sql, rows)
    else:
        repo.executemany(
            "INSERT OR REPLACE INTO daily_kline VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )


def get_daily(code: str) -> pd.DataFrame:
    repo = _repo()
    with repo.conn() as conn:
        if settings.db_backend == "postgres":
            sql = "SELECT * FROM daily_kline WHERE code=%s ORDER BY date"
        else:
            sql = "SELECT * FROM daily_kline WHERE code=? ORDER BY date"
        return pd.read_sql_query(
            sql,
            conn,
            params=(str(code),),
            parse_dates=["date"],
        )


def upsert_stock_list(df: pd.DataFrame):
    if df is None or df.empty:
        return
    ts = datetime.now().isoformat()
    rows = [(str(r["code"]), str(r.get("name", "")), ts) for _, r in df.iterrows()]
    repo = _repo()
    if settings.db_backend == "postgres":
        sql = """
        INSERT INTO stock_list (code, name, updated_at) VALUES (?,?,?)
        ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, updated_at=EXCLUDED.updated_at
        """
        repo.executemany(sql, rows)
    else:
        repo.executemany("INSERT OR REPLACE INTO stock_list VALUES (?,?,?)", rows)


def get_stock_list_db() -> pd.DataFrame:
    repo = _repo()
    with repo.conn() as conn:
        return pd.read_sql_query("SELECT code, name FROM stock_list", conn)


def upsert_board(board_name: str, codes: list[str]):
    repo = _repo()
    repo.execute("DELETE FROM board_stocks WHERE board=?", (board_name,))
    repo.executemany(
        "INSERT INTO board_stocks VALUES (?,?)",
        [(board_name, c) for c in codes],
    )


def get_board_stocks_db(board_name: str) -> list[str]:
    rows = _repo().fetchall("SELECT code FROM board_stocks WHERE board=?", (board_name,))
    return [r[0] for r in rows]


def get_all_boards_db() -> dict[str, int]:
    rows = _repo().fetchall(
        "SELECT board, COUNT(*) FROM board_stocks GROUP BY board ORDER BY board"
    )
    return {r[0]: r[1] for r in rows}


def kv_set(key: str, value):
    _repo().kv_set(key, value)


def kv_get(key: str, default=None):
    return _repo().kv_get(key, default)
