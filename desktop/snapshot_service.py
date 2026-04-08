"""
兼容层：桌面快照服务。

真实实现已开始迁移到 `core.application.snapshot_service`，这里暂时保留
原有导入路径，避免桌面、助手和调度器在第一阶段改造中被一并打散。
"""

from core.application.snapshot_service import (
    build_system_snapshot,
    get_system_snapshot,
    save_system_snapshot,
)

__all__ = [
    "build_system_snapshot",
    "get_system_snapshot",
    "save_system_snapshot",
]
