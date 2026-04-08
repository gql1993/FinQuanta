"""量子组合优化 — 全局配置"""
from dataclasses import dataclass


@dataclass
class QOptConfig:
    """所有可调参数集中管理，不硬编码在算法里。"""
    # 金融参数
    risk_aversion: float = 1.0          # 风险厌恶系数 lambda
    max_holdings: int = 5               # 最多持仓 K
    risk_free_rate: float = 0.03        # 无风险利率（年化）
    lookback_days: int = 60             # 历史回看天数

    # QUBO 参数
    penalty_strength: float = 0.0       # 0=自动计算，>0=手动设定
    penalty_auto_scale: float = 10.0    # 自动惩罚 = scale * max(|Q|)

    # 退火参数
    sa_iterations: int = 5000           # 模拟退火迭代数
    sa_temp_start: float = 100.0
    sa_temp_end: float = 0.001
    sa_tunnel_strength: float = 0.2     # 量子隧穿模拟强度

    # Tabu Search 参数
    tabu_iterations: int = 3000
    tabu_tenure: int = 10

    # QAOA 参数
    qaoa_layers: int = 3                # QAOA 层数 p
    qaoa_optimizer_maxiter: int = 200   # 经典优化器最大迭代
    qaoa_shots: int = 1024              # 采样次数

    # 随机种子
    seed: int = 42
