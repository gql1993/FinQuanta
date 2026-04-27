"""
SQLite -> PostgreSQL 迁移工具

1) 导出 SQLite 快照为 JSON（默认）
2) 将快照导入 PostgreSQL（需 psycopg、已初始化的库）

用法：
  python infra/migrate_sqlite_to_postgres.py
  python infra/migrate_sqlite_to_postgres.py export --out infra/sqlite_export_snapshot.json
  python infra/migrate_sqlite_to_postgres.py import --dsn "postgresql://user:pass@localhost:5432/finquanta"
  set FINQUANTA_POSTGRES_DSN=... && python infra/migrate_sqlite_to_postgres.py import --snapshot infra/sqlite_export_snapshot.json

导入前会在目标库执行 infra/postgres_init.sql，并对旧库补全缺失列（ALTER ... IF NOT EXISTS）。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

SQLITE_DB = os.path.join("data_cache", "quant.db")

ROOT = Path(__file__).resolve().parent.parent

TABLES_EXPORT = [
    "kv_store",
    "stock_list",
    "board_stocks",
    "daily_kline",
    "ai_positions",
    "ai_trade_log",
    "ai_decision_memory",
    "trend_verify",
    "system_event_log",
    "task_run_log",
    "operation_log",
    "daily_nav",
    "api_users",
    "api_tokens",
    "auth_audit_log",
    "ai_chat_history",
]

# PostgreSQL 列顺序（须与 INSERT 一致）；id 为 BIGSERIAL 的表显式插入 id 以保留 SQLite 主键
PG_INSERT_COLUMNS: dict[str, list[str]] = {
    "kv_store": ["key", "value", "updated_at"],
    "stock_list": ["code", "name", "updated_at"],
    "board_stocks": ["board", "code"],
    "daily_kline": ["code", "date", "open", "high", "low", "close", "volume", "amount", "pct_change"],
    "ai_positions": [
        "id",
        "mode",
        "code",
        "name",
        "entry_date",
        "entry_price",
        "shares",
        "stop_loss",
        "status",
        "exit_date",
        "exit_price",
        "exit_reason",
        "pnl",
    ],
    "ai_trade_log": ["id", "mode", "timestamp", "action", "code", "detail"],
    "ai_decision_memory": [
        "id",
        "timestamp",
        "mode",
        "boards",
        "decisions",
        "raw_decisions",
        "analysis",
        "intel_summary",
        "candidates_count",
        "market_regime",
        "verification_summary",
        "guardrail_summary",
        "execution_plan",
        "actual_results",
        "calibrated",
    ],
    "trend_verify": [
        "id",
        "code",
        "name",
        "board",
        "signal_date",
        "signal_price",
        "score",
        "signal_type",
        "strategy",
        "vcp",
        "breakout",
        "price_1d",
        "price_2d",
        "price_3d",
        "price_5d",
        "price_10d",
        "price_20d",
        "price_60d",
        "pnl_1d",
        "pnl_2d",
        "pnl_3d",
        "pnl_5d",
        "pnl_10d",
        "pnl_20d",
        "pnl_60d",
        "analysis",
        "correct",
        "last_calibrated",
        "status",
    ],
    "system_event_log": ["id", "timestamp", "source", "category", "level", "title", "detail"],
    "task_run_log": ["id", "timestamp", "task_name", "trigger_source", "status", "elapsed_ms", "summary", "detail"],
    "operation_log": ["id", "timestamp", "module", "action", "detail"],
    "daily_nav": ["date", "mode", "equity", "cash", "positions_value", "n_positions", "daily_return"],
    "api_users": ["username", "password", "role", "updated_at"],
    "api_tokens": ["token", "username", "role", "expires_at", "created_at"],
    "auth_audit_log": ["id", "timestamp", "actor", "username", "action", "success", "detail"],
    "ai_chat_history": ["id", "session_id", "role", "content", "created_at"],
}

JSONB_COLUMNS = {
    ("kv_store", "value"),
    ("ai_decision_memory", "decisions"),
}

DATE_COLUMNS = {
    ("daily_kline", "date"),
    ("ai_positions", "entry_date"),
    ("ai_positions", "exit_date"),
    ("trend_verify", "signal_date"),
    ("trend_verify", "last_calibrated"),
    ("daily_nav", "date"),
}


def _parse_iso_date(val: Any) -> Any:
    if val is None or val == "":
        return None
    if isinstance(val, (date, datetime)):
        return val.date() if isinstance(val, datetime) else val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if "T" in s or " " in s:
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
            except Exception:
                pass
        try:
            return date.fromisoformat(s[:10])
        except Exception:
            return None
    return val


def _parse_timestamp(val: Any) -> Any:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return s
    return val


def _coerce_cell(table: str, col: str, val: Any) -> Any:
    if (table, col) in JSONB_COLUMNS:
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return None
            try:
                return json.loads(s)
            except Exception:
                return s
        return val

    if (table, col) in DATE_COLUMNS:
        return _parse_iso_date(val)

    if col == "timestamp" and table in (
        "ai_trade_log",
        "system_event_log",
        "task_run_log",
        "operation_log",
        "ai_decision_memory",
    ):
        return _parse_timestamp(val)

    return val


def _row_to_tuple(table: str, row: dict[str, Any]) -> tuple[Any, ...]:
    cols = PG_INSERT_COLUMNS[table]
    out: list[Any] = []
    for c in cols:
        v = row.get(c)
        out.append(_coerce_cell(table, c, v))
    return tuple(out)


def export_sqlite_snapshot(out_path: str = "infra/sqlite_export_snapshot.json") -> None:
    conn = sqlite3.connect(SQLITE_DB, timeout=10)
    snapshot: dict[str, Any] = {}
    for table in TABLES_EXPORT:
        try:
            cur = conn.execute(f"SELECT * FROM {table}")
            cols = [d[0] for d in cur.description]
            rows = []
            for r in cur.fetchall():
                rows.append({cols[i]: r[i] for i in range(len(cols))})
            snapshot[table] = rows
            print(f"{table}: {len(rows)} rows")
        except Exception as e:
            snapshot[table] = {"error": str(e)}
            print(f"{table}: skipped ({e})")
    conn.close()
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
    print(f"exported to {out_p}")


def _run_sql_file(conn: Any, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    statements = [s.strip() for s in text.split(";") if s.strip()]
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt + ";")


def _patch_legacy_schema(conn: Any) -> None:
    """旧版 postgres_init 已建库时补列。"""
    patches = [
        "ALTER TABLE ai_decision_memory ADD COLUMN IF NOT EXISTS intel_summary TEXT",
        "ALTER TABLE ai_decision_memory ADD COLUMN IF NOT EXISTS candidates_count INTEGER",
        "ALTER TABLE ai_decision_memory ADD COLUMN IF NOT EXISTS market_regime TEXT",
        "ALTER TABLE ai_decision_memory ADD COLUMN IF NOT EXISTS raw_decisions TEXT",
        "ALTER TABLE ai_decision_memory ADD COLUMN IF NOT EXISTS verification_summary TEXT",
        "ALTER TABLE ai_decision_memory ADD COLUMN IF NOT EXISTS guardrail_summary TEXT",
        "ALTER TABLE ai_decision_memory ADD COLUMN IF NOT EXISTS execution_plan TEXT",
        "ALTER TABLE ai_decision_memory ADD COLUMN IF NOT EXISTS actual_results TEXT",
        "ALTER TABLE ai_decision_memory ADD COLUMN IF NOT EXISTS calibrated INTEGER DEFAULT 0",
    ]
    with conn.cursor() as cur:
        for p in patches:
            try:
                cur.execute(p)
            except Exception:
                pass
    conn.commit()


def _truncate_tables(conn: Any, preserve_tables: frozenset[str] | None = None) -> None:
    preserve_tables = preserve_tables or frozenset()
    names = [t for t in PG_INSERT_COLUMNS if t not in preserve_tables]
    if not names:
        return
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {', '.join(names)} RESTART IDENTITY CASCADE")
    conn.commit()


# 超过此行数时对 daily_kline 使用 COPY FROM STDIN（显著快于 executemany）
DAILY_KLINE_COPY_THRESHOLD = 5000


def _import_daily_kline_copy(cur: Any, rows_raw: list[dict[str, Any]]) -> int:
    cols = PG_INSERT_COLUMNS["daily_kline"]
    col_list = ", ".join(cols)
    n = 0
    with cur.copy(f"COPY daily_kline ({col_list}) FROM STDIN") as copy:
        for r in rows_raw:
            copy.write_row(_row_to_tuple("daily_kline", r))
            n += 1
    return n


def import_snapshot_to_postgres(
    dsn: str,
    snapshot_path: str | Path,
    *,
    init_sql: Path | None = None,
    truncate: bool = True,
    skip_tables: frozenset[str] | None = None,
    daily_kline_copy_threshold: int = DAILY_KLINE_COPY_THRESHOLD,
) -> None:
    try:
        import psycopg
    except Exception as exc:
        raise RuntimeError("需要安装 psycopg: pip install 'psycopg[binary]'") from exc

    init_sql = init_sql or ROOT / "infra" / "postgres_init.sql"
    snap = Path(snapshot_path)
    with open(snap, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    skip_tables = skip_tables or frozenset()
    unknown = skip_tables - frozenset(PG_INSERT_COLUMNS.keys())
    if unknown:
        raise ValueError(f"未知表名（--skip-table）: {sorted(unknown)}")

    conn = psycopg.connect(dsn)
    try:
        _run_sql_file(conn, init_sql)
        _patch_legacy_schema(conn)
        if truncate:
            _truncate_tables(conn, preserve_tables=skip_tables)

        with conn.cursor() as cur:
            for table, cols in PG_INSERT_COLUMNS.items():
                if table in skip_tables:
                    print(f"{table}: skipped (--skip-table)")
                    continue
                rows_raw = data.get(table)
                if rows_raw is None:
                    print(f"{table}: 0 rows (snapshot 中无此表键)")
                    continue
                if not isinstance(rows_raw, list):
                    if isinstance(rows_raw, dict) and "error" in rows_raw:
                        print(f"{table}: skip (export error: {rows_raw['error']})")
                    continue
                if not rows_raw:
                    print(f"{table}: 0 rows")
                    continue

                if (
                    table == "daily_kline"
                    and len(rows_raw) >= daily_kline_copy_threshold
                ):
                    n = _import_daily_kline_copy(cur, rows_raw)
                    print(f"{table}: imported {n} rows (COPY)")
                    continue

                placeholders = ", ".join(["%s"] * len(cols))
                col_list = ", ".join(cols)
                sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
                batch = [_row_to_tuple(table, r) for r in rows_raw]
                cur.executemany(sql, batch)
                print(f"{table}: imported {len(batch)} rows")
        conn.commit()
        print("import finished OK")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite <-> PostgreSQL migration")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="CMD")

    p_exp = sub.add_parser("export", help="Export SQLite to JSON")
    p_exp.add_argument("--out", default="infra/sqlite_export_snapshot.json")

    p_imp = sub.add_parser("import", help="Import JSON snapshot into PostgreSQL")
    p_imp.add_argument("--dsn", default=os.environ.get("FINQUANTA_POSTGRES_DSN", ""))
    p_imp.add_argument("--snapshot", default="infra/sqlite_export_snapshot.json")
    p_imp.add_argument("--init-sql", default="", help="Override path to postgres_init.sql")
    p_imp.add_argument("--no-truncate", action="store_true", help="Do not truncate target tables before insert")
    p_imp.add_argument(
        "--skip-table",
        action="append",
        default=[],
        metavar="NAME",
        help="跳过某表的导入，且 truncate 时保留该表已有数据（可重复指定）",
    )
    p_imp.add_argument(
        "--copy-threshold",
        type=int,
        default=DAILY_KLINE_COPY_THRESHOLD,
        metavar="N",
        help=f"daily_kline 行数≥N 时用 COPY 导入（默认 {DAILY_KLINE_COPY_THRESHOLD}）",
    )

    args = parser.parse_args()

    if args.cmd == "export":
        export_sqlite_snapshot(args.out)
        return

    if args.cmd == "import":
        dsn = (args.dsn or "").strip()
        if not dsn:
            raise SystemExit("请设置 --dsn 或环境变量 FINQUANTA_POSTGRES_DSN")
        init_path = Path(args.init_sql) if args.init_sql else None
        skip = frozenset(t.strip() for t in args.skip_table if t.strip())
        import_snapshot_to_postgres(
            dsn,
            args.snapshot,
            init_sql=init_path,
            truncate=not args.no_truncate,
            skip_tables=skip,
            daily_kline_copy_threshold=max(1, args.copy_threshold),
        )
        return


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        export_sqlite_snapshot()
    else:
        main()
