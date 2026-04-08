@echo off
cd /d %~dp0
REM 先设置 FINQUANTA_POSTGRES_DSN，再执行导入；可选先运行: python infra/migrate_sqlite_to_postgres.py export
python infra/migrate_sqlite_to_postgres.py import --snapshot infra/sqlite_export_snapshot.json %*
