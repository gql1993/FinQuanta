"""数据预处理：收益率计算、统计量估计。"""
import numpy as np
from dataclasses import dataclass, field


@dataclass
class StockStats:
    """n只股票的统计量。"""
    codes: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    n: int = 0
    mu: np.ndarray = None           # 预期年化收益向量 (n,)
    sigma: np.ndarray = None        # 年化协方差矩阵 (n, n)
    daily_returns: np.ndarray = None  # 日收益率矩阵 (T, n)
    annual_vols: np.ndarray = None  # 年化波动率 (n,)
    corr: np.ndarray = None         # 相关系数矩阵 (n, n)


def compute_stats(prices: dict[str, np.ndarray], names: dict[str, str] = None) -> StockStats:
    """
    从价格序列计算收益率和统计量。

    Args:
        prices: {code: np.array of daily close prices}
        names: {code: name}
    Returns:
        StockStats
    """
    if names is None:
        names = {}

    codes = sorted(prices.keys())
    # 对齐长度
    min_len = min(len(prices[c]) for c in codes)
    if min_len < 10:
        raise ValueError(f"价格序列太短: {min_len} 天，至少需要10天")

    # 日对数收益率（不是简单收益率，更符合金融建模）
    returns_list = []
    for c in codes:
        p = np.array(prices[c][-min_len:], dtype=float)
        log_ret = np.diff(np.log(p))
        returns_list.append(log_ret)

    daily_returns = np.column_stack(returns_list)  # (T-1, n)
    n = len(codes)
    T = daily_returns.shape[0]

    # 预期年化收益
    mu = np.mean(daily_returns, axis=0) * 250

    # 年化协方差矩阵
    sigma = np.cov(daily_returns.T) * 250

    # 年化波动率
    annual_vols = np.sqrt(np.diag(sigma))

    # 相关系数矩阵
    corr = np.corrcoef(daily_returns.T)

    return StockStats(
        codes=codes,
        names=[names.get(c, c) for c in codes],
        n=n,
        mu=mu,
        sigma=sigma,
        daily_returns=daily_returns,
        annual_vols=annual_vols,
        corr=corr,
    )
