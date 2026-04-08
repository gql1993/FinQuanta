"""
CSV/JSON → SQLite 同步（兼容入口）。
实际逻辑已合并到 data_sync.py，此文件保留向后兼容。
"""
from desktop.data_sync import sync_csv_to_db


def sync_all():
    """同步全部本地缓存到 SQLite。"""
    from desktop.db import init_db
    init_db()
    return sync_csv_to_db()


if __name__ == "__main__":
    result = sync_all()
    print(f"同步完成: 股票列表 {result['stocks']} 只, 板块 {result['boards']} 个")
