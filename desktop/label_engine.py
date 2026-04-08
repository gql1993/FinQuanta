"""
统一标签引擎

用途：
1. 为因子研究、走势验证、回测、学习引擎提供统一的未来收益标签
2. 统一“1日/2日/3日/5日/10日/20日/60日”收益率口径
3. 后续可扩展为分类标签（上涨/下跌/强上涨等）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


SUPPORTED_HORIZONS = [1, 2, 3, 5, 10, 20, 60, 120, 250]


@dataclass
class LabelSet:
    code: str
    labels: dict[str, float]


def future_return(prices: Iterable[float], horizon: int) -> float | None:
    """
    基于价格序列计算未来 horizon 日收益率（百分比）。
    约定：prices[-1] 为当前日，prices[-(horizon+1)] 为 horizon 日前。
    """
    arr = np.asarray(list(prices), dtype=float)
    if len(arr) < horizon + 1:
        return None
    base = float(arr[-(horizon + 1)])
    last = float(arr[-1])
    if base <= 0:
        return None
    return (last / base - 1) * 100


def build_return_labels(code: str, prices: Iterable[float], horizons: list[int] | None = None) -> LabelSet:
    horizons = horizons or SUPPORTED_HORIZONS
    labels = {}
    for h in horizons:
        v = future_return(prices, h)
        labels[f"ret_{h}d"] = round(v, 4) if v is not None else None
    return LabelSet(code=code, labels=labels)


def classify_return(ret_pct: float | None) -> str:
    """
    对未来收益做简单分类：
    - strong_up / up / flat / down / strong_down
    """
    if ret_pct is None:
        return "unknown"
    if ret_pct >= 10:
        return "strong_up"
    if ret_pct >= 2:
        return "up"
    if ret_pct <= -10:
        return "strong_down"
    if ret_pct <= -2:
        return "down"
    return "flat"


def summarize_labels(prices: Iterable[float]) -> dict[str, float | str | None]:
    """
    一次性输出常用标签摘要，方便策略和学习模块调用。
    """
    arr = np.asarray(list(prices), dtype=float)
    out: dict[str, float | str | None] = {}
    for h in [1, 2, 3, 5, 10, 20, 60]:
        ret = future_return(arr, h)
        out[f"ret_{h}d"] = round(ret, 4) if ret is not None else None
        out[f"class_{h}d"] = classify_return(ret)
    return out
