"""
统一数据访问入口（桌面 / daemon / API 业务层共用）

规则：
- 新代码禁止直接 sqlite3.connect；请通过本模块或 api_server.storage.repo。
- 平台审计表（system_event_log / task_run_log）一律经此处写入，保证 SQLite / PostgreSQL 双轨一致。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from api_server.config import settings
from api_server.storage import repo
from core.audit.event_models import create_system_event, event_from_log_row


def insert_ignore_stock_list_rows(rows: list[tuple]) -> None:
    """rows: (code, name, updated_at占位) 与旧 sync 一致；PostgreSQL 用 ON CONFLICT。"""
    if not rows:
        return
    r = get_repo()
    if settings.db_backend == "postgres":
        sql = """
        INSERT INTO stock_list (code, name, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (code) DO NOTHING
        """
        r.executemany(sql, [(x[0], x[1]) for x in rows])
    else:
        r.executemany("INSERT OR IGNORE INTO stock_list VALUES (?,?,?)", rows)


def insert_ignore_board_pairs(pairs: list[tuple]) -> None:
    """pairs: (board, code)"""
    if not pairs:
        return
    r = get_repo()
    if settings.db_backend == "postgres":
        sql = """
        INSERT INTO board_stocks (board, code) VALUES (?,?)
        ON CONFLICT (board, code) DO NOTHING
        """
        r.executemany(sql, pairs)
    else:
        r.executemany("INSERT OR IGNORE INTO board_stocks VALUES (?,?)", pairs)


def upsert_daily_kline_rows(rows: list[tuple]) -> None:
    """
    批量写入日 K（SQLite: INSERT OR REPLACE；PostgreSQL: ON CONFLICT）。
    每行 9 列: code, date, open, high, low, close, volume, amount, pct_change
    """
    if not rows:
        return
    r = get_repo()
    if settings.db_backend == "postgres":
        sql = """
        INSERT INTO daily_kline (code, date, open, high, low, close, volume, amount, pct_change)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT (code, date) DO UPDATE SET
        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
        volume=EXCLUDED.volume, amount=EXCLUDED.amount, pct_change=EXCLUDED.pct_change
        """
        r.executemany(sql, rows)
    else:
        r.executemany(
            "INSERT OR REPLACE INTO daily_kline VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )

_PLATFORM_SQLITE_DDL = """
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


def get_repo():
    """返回全局仓储（SQLite 或 PostgreSQL，由环境变量决定）。"""
    return repo


def ensure_platform_tables() -> None:
    """确保审计与任务表存在（PostgreSQL 由 infra/postgres_init.sql 初始化，此处仅补 SQLite）。"""
    if settings.db_backend == "postgres":
        return
    repo.executescript(_PLATFORM_SQLITE_DDL)


def append_system_event(
    source: str,
    category: str,
    title: str,
    detail: str = "",
    level: str = "info",
    *,
    trace_id: str = "",
    decision_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    ensure_platform_tables()
    event = create_system_event(
        source=source,
        category=category,
        title=title,
        detail=detail,
        level=level,
        trace_id=trace_id,
        decision_id=decision_id,
        metadata=metadata,
    )
    repo.execute(
        "INSERT INTO system_event_log (timestamp, source, category, level, title, detail) VALUES (?,?,?,?,?,?)",
        event.to_log_row(),
    )


def append_task_run(
    task_name: str,
    trigger_source: str,
    status: str,
    elapsed_ms: float,
    summary: str = "",
    detail: str = "",
) -> None:
    ensure_platform_tables()
    ts = datetime.now().isoformat()
    repo.execute(
        "INSERT INTO task_run_log (timestamp, task_name, trigger_source, status, elapsed_ms, summary, detail) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            ts,
            task_name,
            trigger_source,
            status,
            round(elapsed_ms, 1),
            summary,
            detail,
        ),
    )


def fetch_recent_task_runs(limit: int = 50) -> list[dict[str, Any]]:
    ensure_platform_tables()
    rows = repo.fetchall(
        "SELECT timestamp, task_name, trigger_source, status, elapsed_ms, summary "
        "FROM task_run_log ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [
        {
            "timestamp": r[0],
            "task_name": r[1],
            "trigger_source": r[2],
            "status": r[3],
            "elapsed_ms": r[4],
            "summary": r[5],
        }
        for r in rows
    ]


def fetch_recent_system_events(limit: int = 50) -> list[dict[str, Any]]:
    ensure_platform_tables()
    rows = repo.fetchall(
        "SELECT timestamp, source, category, level, title, detail "
        "FROM system_event_log ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [event_from_log_row(r) for r in rows]


def get_kv_json(key: str, default=None):
    raw = repo.kv_get(key, default=None)
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def set_kv_json(key: str, value: Any) -> None:
    repo.kv_set(key, value)


class _DummyCursor:
    """INSERT/UPDATE/DELETE 后占位，兼容 fetchone 链式调用。"""

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    @property
    def rowcount(self):
        return -1


class _RepoCursor:
    """SELECT 结果游标，兼容 execute().fetchone() / 迭代。"""

    def __init__(self, r, sql: str, params: tuple):
        self._r = r
        self._sql = sql
        self._params = params

    def fetchone(self):
        return self._r.fetchone(self._sql, self._params)

    def fetchall(self):
        return self._r.fetchall(self._sql, self._params)

    def __iter__(self):
        return iter(self.fetchall())


class RepoCompatConnection:
    """
    兼容旧代码 conn.execute(...).fetchone() 与 for row in conn.execute(...)。
    底层走 get_repo()，支持 SQLite / PostgreSQL。
    """

    def __init__(self):
        self._r = get_repo()

    def execute(self, sql: str, params: tuple = ()):
        t = sql.strip().upper()
        is_select = t.startswith("SELECT") or t.startswith("WITH ") or t.startswith("EXPLAIN")
        if is_select:
            return _RepoCursor(self._r, sql, params)
        self._r.execute(sql, params)
        return _DummyCursor()

    def executemany(self, sql: str, seq_of_params):
        self._r.executemany(sql, list(seq_of_params))
        return _DummyCursor()

    def executescript(self, sql: str):
        self._r.executescript(sql)

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


def read_sql_query(sql: str, params: tuple | list = ()):
    """
    pandas.read_sql_query，连接走 repo（SQLite / PostgreSQL）。
    SQL 使用 ? 占位符（内部在 PostgreSQL 下转为 %s）。
    """
    import pandas as pd

    r = get_repo()
    q = sql
    if settings.db_backend == "postgres":
        q = sql.replace("?", "%s")
    tup = tuple(params)
    with r.conn() as conn:
        return pd.read_sql_query(q, conn, params=tup)
