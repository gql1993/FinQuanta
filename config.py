"""
Minervini SEPA 策略全局配置
基于《股票魔法师》各章节的具体交易规则。
"""
from dataclasses import dataclass, field
from datetime import date


@dataclass
class TrendTemplateConfig:
    """趋势模板筛选参数 (第5章: 确认 Stage 2 上升趋势)"""
    ma_short: int = 50
    ma_mid: int = 150
    ma_long: int = 200
    ma_long_uptrend_days: int = 22       # 200日均线至少上升1个月
    above_52w_low_pct: float = 1.25      # 股价 > 52周低点 × 125%
    within_52w_high_pct: float = 0.75    # 股价 >= 52周高点 × 75%
    rs_rating_min: float = 70            # RS 评级 >= 70
    trading_days_per_year: int = 250


@dataclass
class VCPConfig:
    """VCP 形态参数 (第8章: 波动收缩形态)"""
    lookback_days: int = 120             # 基底形态回溯天数
    min_contractions: int = 2            # 最少收缩次数
    max_contractions: int = 4            # 最多收缩次数
    contraction_window: int = 20         # 收缩窗口大小
    min_contraction_ratio: float = 0.4   # 后一次/前一次幅度比下限
    max_contraction_ratio: float = 0.85  # 后一次/前一次幅度比上限
    volume_decline_ratio: float = 0.8    # 形态内成交量萎缩阈值
    breakout_volume_ratio: float = 1.2   # 突破日放量倍数(相对50日均量)
    pivot_tolerance: float = 0.02        # 枢纽点容差 2%
    tight_close_days: int = 5            # 突破前紧密收盘天数
    tight_close_range: float = 0.015     # 紧密收盘幅度 1.5%


@dataclass
class FundamentalConfig:
    """基本面过滤参数 (第6-7章: 基本面加速)"""
    min_quarterly_eps_growth: float = 0.20   # 最近季度EPS同比增长 >= 20%
    min_annual_eps_growth: float = 0.25      # 最近年度EPS增长 >= 25%
    min_revenue_growth: float = 0.20         # 营收同比增长 >= 20%
    min_roe: float = 0.15                    # ROE >= 15%
    min_profit_margin: float = 0.0           # 净利润率 > 0


@dataclass
class RiskConfig:
    """
    风险管理参数 (第10-12章: 买入、卖出与仓位管理)

    Minervini 的核心卖出规则:
    1. 硬止损: 入场价下方 7-8%
    2. 渐进式止损: 盈利增长时逐步收紧止损
    3. 部分止盈: 盈利20-25%时卖出部分
    4. 移动止损: 用 10日/21日均线跟踪
    5. 时间止损: 买入后3-4周无表现则出局
    6. 8周持仓规则: 1-3周内暴涨20%+，至少持有8周
    7. 高潮顶部: 竭尽放量/跳空/铁轨形态 → 立即卖出
    8. 阶段退出: 跌破50日均线(Stage 3)、200日均线下行(Stage 4) → 卖出
    """
    # --- 基本止损 ---
    stop_loss_pct: float = 0.08              # 硬止损 8%
    risk_per_trade: float = 0.01             # 单笔风险 ≤ 总资金 1%
    max_positions: int = 8                   # 最大同时持仓

    # --- 渐进式止损 (第10章: 逐步锁定利润) ---
    progressive_stops: list = field(default_factory=lambda: [
        # (盈利阈值, 止损提升至入场价+百分比)
        (0.05, 0.00),    # 盈利5%  → 止损提至保本
        (0.10, 0.05),    # 盈利10% → 止损提至+5%
        (0.15, 0.10),    # 盈利15% → 止损提至+10%
        (0.20, 0.15),    # 盈利20% → 止损提至+15%
    ])

    # --- 部分止盈 ---
    profit_target_partial: float = 0.20      # 盈利20%触发部分止盈
    partial_sell_ratio: float = 0.5          # 部分止盈卖出比例

    # --- 移动止损 (第11章) ---
    trailing_stop_ma: int = 21               # 部分止盈后用21日均线跟踪
    trailing_stop_ma_fast: int = 10          # 快速强势股用10日均线

    # --- 时间止损 (第10章: 如果要涨，很快就会涨) ---
    time_stop_days: int = 20                 # 买入后N个交易日无表现
    time_stop_min_move: float = 0.02         # 期间至少涨2%才算"有表现"

    # --- 8周持仓规则 (第12章: 给大赢家空间) ---
    fast_gain_pct: float = 0.20              # 1-3周内涨幅达到此值
    fast_gain_weeks: int = 3                 # 在此周数内
    eight_week_hold_days: int = 40           # 至少持有8周(40个交易日)

    # --- 高潮顶部检测 (第12章: 识别卖出信号) ---
    climax_volume_ratio: float = 3.0         # 成交量 > 50日均量 × 3倍
    climax_spread_ratio: float = 2.0         # 当日振幅 > 近20日平均振幅 × 2倍
    climax_run_days: int = 60                # 至少上涨N天才判断高潮顶
    climax_run_gain: float = 0.30            # 运行期间至少涨30%
    exhaustion_gap_pct: float = 0.03         # 竭尽跳空: 跳空幅度 >= 3%
    railroad_reversal_pct: float = 0.03      # 铁轨反转: 大阳后大阴 >= 3%

    # --- 阶段退出 (第5章: 趋势阶段分析) ---
    stage3_break_ma: int = 50                # 跌破50日均线 → Stage 3预警
    stage3_consecutive_days: int = 3         # 连续N天收在50MA下方确认
    stage4_ma_declining_days: int = 10       # 200日均线连续下降N天 → Stage 4

    # --- 从高点回撤保护 ---
    max_drawdown_from_peak: float = 0.12     # 从持仓高点回撤超过12%强制卖出


@dataclass
class BacktestConfig:
    """回测参数"""
    initial_capital: float = 1_000_000.0     # 初始资金 100万
    commission_rate: float = 0.0003          # 佣金 万三
    stamp_tax_rate: float = 0.001            # 印花税 千一(仅卖出)
    slippage: float = 0.001                  # 滑点 0.1%
    limit_up_pct: float = 0.10               # 主板涨停 10%
    limit_up_pct_star: float = 0.20          # 科创/创业涨停 20%
    t_plus_1: bool = True                    # T+1


@dataclass
class MarketRegimeConfig:
    """
    市场环境判断参数 (第9章: 顺势而为)
    当大盘出现多个分布日时，减少仓位或停止买入。
    """
    index_code: str = "000300"               # 跟踪沪深300
    distribution_drop_pct: float = 0.002     # 指数下跌 > 0.2% 且放量 = 分布日
    distribution_window: int = 25            # 25个交易日窗口
    max_distribution_days: int = 5           # 窗口内超过5个分布日 → 市场转弱
    rally_confirmation_days: int = 3         # 连续3天放量上涨 → 确认反弹


@dataclass
class TradingCostConfig:
    """交易成本常量（统一管理，回测+模拟仓共用）"""
    commission_rate: float = 0.0003      # 佣金 万三
    stamp_tax_rate: float = 0.001        # 印花税 千一（仅卖出）
    slippage: float = 0.001              # 滑点 0.1%
    min_commission: float = 5.0          # 最低佣金 5 元


@dataclass
class DataConfig:
    """数据配置"""
    cache_dir: str = "data_cache"
    start_date: str = "20200101"
    end_date: str = ""
    exclude_st: bool = True
    min_listing_days: int = 250
    holidays_file: str = ""

    def __post_init__(self):
        if not self.end_date:
            self.end_date = date.today().strftime("%Y%m%d")
        if not self.holidays_file:
            self.holidays_file = f"{self.cache_dir}/cn_holidays.json"


@dataclass
class StrategyConfig:
    """策略总配置"""
    trend: TrendTemplateConfig = field(default_factory=TrendTemplateConfig)
    vcp: VCPConfig = field(default_factory=VCPConfig)
    fundamental: FundamentalConfig = field(default_factory=FundamentalConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    data: DataConfig = field(default_factory=DataConfig)
    market: MarketRegimeConfig = field(default_factory=MarketRegimeConfig)
    trading_cost: TradingCostConfig = field(default_factory=TradingCostConfig)
