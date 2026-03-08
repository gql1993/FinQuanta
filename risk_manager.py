"""
风险管理模块 (对应《股票魔法师》第10-12章)
实现 Minervini 完整的买入后管理规则:
  - 硬止损 / 渐进式移动止损 / 均线跟踪止损
  - 部分止盈 / 时间止损 / 8周持仓规则
  - 高潮顶部检测 / Stage 3-4 退出
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import RiskConfig


@dataclass
class Position:
    """持仓记录"""
    code: str
    entry_date: str
    entry_price: float
    shares: int
    stop_loss: float
    status: str = "open"
    partial_sold: bool = False
    highest_since_entry: float = 0.0
    days_held: int = 0
    is_fast_gainer: bool = False        # 是否触发8周持仓规则
    fast_gain_lock_until: int = 0       # 8周锁定到第N个交易日
    highest_profit_pct: float = 0.0     # 历史最高盈利百分比
    strategy_id: str = ""               # 来源策略
    entry_reason: str = ""              # 入场诊断理由
    entry_phase: str = ""               # 入场情绪阶段
    entry_heat: float = 0.0             # 入场赛道热度
    entry_valuation: float = 0.0        # 入场估值分位
    entry_crowding: float = 0.0         # 入场拥挤度

    def __post_init__(self):
        if self.highest_since_entry == 0:
            self.highest_since_entry = self.entry_price


class RiskManager:
    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    # ------------------------------------------------------------------
    # 仓位计算 (第10章: 用风险决定仓位)
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_price: float | None = None,
    ) -> int:
        """
        仓位 = (总资金 × 单笔风险比例) / (入场价 - 止损价)
        A 股最小单位 100 股。
        """
        if stop_price is None:
            stop_price = entry_price * (1 - self.config.stop_loss_pct)

        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0:
            return 0

        max_risk_amount = capital * self.config.risk_per_trade
        shares = int(max_risk_amount / risk_per_share)
        shares = (shares // 100) * 100

        max_per_position = capital / self.config.max_positions
        max_shares_by_capital = int(max_per_position / entry_price)
        max_shares_by_capital = (max_shares_by_capital // 100) * 100

        return min(shares, max_shares_by_capital)

    def get_stop_loss_price(self, entry_price: float) -> float:
        """初始止损 = 入场价 × (1 - 8%)"""
        return round(entry_price * (1 - self.config.stop_loss_pct), 2)

    # ------------------------------------------------------------------
    # 核心: 综合出场信号检查
    # ------------------------------------------------------------------

    def check_exit_signals(
        self,
        position: Position,
        current_price: float,
        current_high: float,
        current_low: float,
        current_volume: float,
        day_data: dict,
        df_history: pd.DataFrame | None = None,
    ) -> dict:
        """
        综合检查所有卖出规则，按优先级返回。

        参数:
            position: 持仓
            current_price: 当日收盘价
            current_high: 当日最高价
            current_low: 当日最低价
            current_volume: 当日成交量
            day_data: 当日完整行情字典
            df_history: 该股票的历史数据(用于均线/阶段分析)

        返回:
            {"action": "hold"/"partial_sell"/"full_sell", "reason": str}
        """
        position.days_held += 1
        position.highest_since_entry = max(position.highest_since_entry, current_high)
        profit_pct = (current_price - position.entry_price) / position.entry_price
        position.highest_profit_pct = max(position.highest_profit_pct, profit_pct)

        # ============================================================
        # 规则 1: 硬止损 (第10章 - 绝对止损线，不可协商)
        # ============================================================
        if current_price <= position.stop_loss:
            return {"action": "full_sell", "reason": f"硬止损: 跌至{current_price:.2f} <= 止损{position.stop_loss:.2f}"}

        # ============================================================
        # 规则 2: 高潮顶部卖出 (第12章 - 竭尽信号)
        # ============================================================
        climax = self._check_climax_top(position, current_price, current_high,
                                         current_low, current_volume, day_data, df_history)
        if climax is not None:
            return climax

        # ============================================================
        # 规则 3: Stage 3/4 退出 (第5章 - 趋势阶段变化)
        # ============================================================
        stage_exit = self._check_stage_exit(position, current_price, df_history)
        if stage_exit is not None:
            return stage_exit

        # ============================================================
        # 规则 4: 渐进式止损更新 (第10章 - 随着盈利锁定利润)
        # ============================================================
        self._update_progressive_stop(position, profit_pct)

        # ============================================================
        # 规则 5: 从最高点回撤保护
        # ============================================================
        if position.highest_since_entry > 0 and profit_pct > 0:
            drawdown = (position.highest_since_entry - current_price) / position.highest_since_entry
            if drawdown >= self.config.max_drawdown_from_peak:
                return {"action": "full_sell",
                        "reason": f"从高点{position.highest_since_entry:.2f}回撤{drawdown:.1%}，保护利润"}

        # ============================================================
        # 规则 6: 8周持仓规则检查 (第12章 - 给大赢家空间)
        # ============================================================
        self._check_fast_gainer(position, profit_pct)
        if position.is_fast_gainer and position.days_held < position.fast_gain_lock_until:
            # 锁定期内只触发硬止损，不做其他卖出
            return {"action": "hold", "reason": "8周持仓锁定中"}

        # ============================================================
        # 规则 7: 部分止盈 (第11章 - 兑现部分利润)
        # ============================================================
        if profit_pct >= self.config.profit_target_partial and not position.partial_sold:
            return {"action": "partial_sell",
                    "reason": f"盈利{profit_pct:.1%}达到部分止盈目标{self.config.profit_target_partial:.0%}"}

        # ============================================================
        # 规则 8: 均线移动止损 (第11章 - 部分止盈后跟踪)
        # ============================================================
        if position.partial_sold and df_history is not None:
            ma_exit = self._check_trailing_ma_stop(position, current_price, df_history)
            if ma_exit is not None:
                return ma_exit

        # ============================================================
        # 规则 9: 时间止损 (第10章 - 该涨不涨就离场)
        # ============================================================
        if position.days_held >= self.config.time_stop_days:
            if profit_pct < self.config.time_stop_min_move:
                return {"action": "full_sell",
                        "reason": f"时间止损: 持有{position.days_held}天仅涨{profit_pct:.1%}"}

        return {"action": "hold", "reason": ""}

    # ------------------------------------------------------------------
    # 规则 2: 高潮顶部检测 (第12章)
    # ------------------------------------------------------------------

    def _check_climax_top(
        self,
        position: Position,
        current_price: float,
        current_high: float,
        current_low: float,
        current_volume: float,
        day_data: dict,
        df_history: pd.DataFrame | None,
    ) -> dict | None:
        """
        高潮顶部的五种典型信号:
        a) 竭尽放量: 超大成交量 + 超大振幅
        b) 竭尽跳空: 长期上涨后向上跳空
        c) 铁轨反转: 大阳线后紧接大阴线
        d) 长上影线: 冲高回落
        """
        if df_history is None or len(df_history) < self.config.climax_run_days:
            return None

        profit_pct = (current_price - position.entry_price) / position.entry_price
        # 只有在已经获利一段时间后才检测高潮顶
        if position.days_held < 20 or profit_pct < 0.15:
            return None

        # 计算基准指标
        vol_50 = df_history["volume"].iloc[-50:].mean()
        spread_20 = (df_history["high"].iloc[-20:] - df_history["low"].iloc[-20:]).mean()
        current_spread = current_high - current_low

        # (a) 竭尽放量 + 超大振幅
        if (current_volume > vol_50 * self.config.climax_volume_ratio
                and current_spread > spread_20 * self.config.climax_spread_ratio):
            return {"action": "full_sell",
                    "reason": f"高潮顶: 成交量{current_volume/vol_50:.1f}x均量 + 振幅{current_spread/spread_20:.1f}x均幅"}

        # (b) 竭尽跳空: 今开 > 昨高 且幅度大
        prev_high = float(df_history["high"].iloc[-2]) if len(df_history) >= 2 else 0
        today_open = float(day_data.get("open", 0))
        if prev_high > 0 and today_open > 0:
            gap_pct = (today_open - prev_high) / prev_high
            if gap_pct >= self.config.exhaustion_gap_pct and current_volume > vol_50 * 2:
                return {"action": "full_sell",
                        "reason": f"竭尽跳空: 跳空{gap_pct:.1%}+放量，长期上涨后见顶"}

        # (c) 铁轨反转: 昨日大阳 + 今日大阴(收盘吞没)
        if len(df_history) >= 2:
            prev_row = df_history.iloc[-2]
            prev_change = (float(prev_row["close"]) - float(prev_row["open"])) / float(prev_row["open"]) if float(prev_row["open"]) > 0 else 0
            today_change = (current_price - today_open) / today_open if today_open > 0 else 0
            if (prev_change >= self.config.railroad_reversal_pct
                    and today_change <= -self.config.railroad_reversal_pct):
                return {"action": "full_sell",
                        "reason": f"铁轨反转: 昨涨{prev_change:.1%}+今跌{today_change:.1%}"}

        # (d) 长上影线 (冲高回落: 上影 > 实体 × 2)
        body = abs(current_price - today_open) if today_open > 0 else 0
        upper_shadow = current_high - max(current_price, today_open)
        if body > 0 and upper_shadow > body * 2 and current_volume > vol_50 * 2:
            return {"action": "full_sell",
                    "reason": f"长上影线冲高回落: 上影{upper_shadow:.2f} > 实体{body:.2f}×2"}

        return None

    # ------------------------------------------------------------------
    # 规则 3: 阶段退出 (第5章)
    # ------------------------------------------------------------------

    def _check_stage_exit(
        self,
        position: Position,
        current_price: float,
        df_history: pd.DataFrame | None,
    ) -> dict | None:
        """
        Stage 3 预警: 股价连续数天收在50日均线下方
        Stage 4 确认: 200日均线开始下行
        """
        if df_history is None or len(df_history) < 200:
            return None

        close_series = df_history["close"]
        ma50 = close_series.rolling(self.config.stage3_break_ma).mean()
        ma200 = close_series.rolling(200).mean()

        # Stage 3: 连续 N 天收在 50MA 下方
        n = self.config.stage3_consecutive_days
        if len(ma50) >= n:
            recent_ma50 = ma50.iloc[-n:].values
            recent_close = close_series.iloc[-n:].values
            if not np.any(np.isnan(recent_ma50)):
                below_count = sum(1 for c, m in zip(recent_close, recent_ma50) if c < m)
                if below_count >= n:
                    return {"action": "full_sell",
                            "reason": f"Stage 3 预警: 连续{n}天收于50日均线下方"}

        # Stage 4: 200日均线连续下降
        decline_days = self.config.stage4_ma_declining_days
        if len(ma200) >= decline_days:
            recent_ma200 = ma200.iloc[-decline_days:].values
            if not np.any(np.isnan(recent_ma200)):
                if all(recent_ma200[i] < recent_ma200[i - 1] for i in range(1, len(recent_ma200))):
                    return {"action": "full_sell",
                            "reason": f"Stage 4: 200日均线连续{decline_days}天下行，趋势反转"}

        return None

    # ------------------------------------------------------------------
    # 规则 4: 渐进式止损 (第10章)
    # ------------------------------------------------------------------

    def _update_progressive_stop(self, position: Position, profit_pct: float):
        """
        随着盈利增长，逐级提升止损位:
        盈利5%  → 止损提至保本
        盈利10% → 止损提至+5%
        盈利15% → 止损提至+10%
        盈利20% → 止损提至+15%
        """
        for threshold, stop_offset in self.config.progressive_stops:
            if profit_pct >= threshold:
                new_stop = position.entry_price * (1 + stop_offset)
                if new_stop > position.stop_loss:
                    position.stop_loss = round(new_stop, 2)

    # ------------------------------------------------------------------
    # 规则 6: 8周持仓规则 (第12章)
    # ------------------------------------------------------------------

    def _check_fast_gainer(self, position: Position, profit_pct: float):
        """
        1-3周内暴涨20%+的股票 → 标记为快速获利者，至少持有8周(40个交易日)
        锁定期内只触发硬止损，其他卖出信号暂时屏蔽。
        """
        if position.is_fast_gainer:
            return

        fast_gain_days = self.config.fast_gain_weeks * 5  # 周 → 交易日
        if (position.days_held <= fast_gain_days
                and profit_pct >= self.config.fast_gain_pct):
            position.is_fast_gainer = True
            position.fast_gain_lock_until = self.config.eight_week_hold_days

    # ------------------------------------------------------------------
    # 规则 8: 均线跟踪止损 (第11章)
    # ------------------------------------------------------------------

    def _check_trailing_ma_stop(
        self,
        position: Position,
        current_price: float,
        df_history: pd.DataFrame,
    ) -> dict | None:
        """
        部分止盈后，剩余仓位用均线跟踪。
        RS强势股用10日EMA，普通股用21日EMA。
        """
        if len(df_history) < self.config.trailing_stop_ma:
            return None

        ma_slow = df_history["close"].ewm(span=self.config.trailing_stop_ma, adjust=False).mean()
        ma_fast = df_history["close"].ewm(span=self.config.trailing_stop_ma_fast, adjust=False).mean()

        # 如果盈利超过30%，用更宽松的21日均线; 否则用10日
        if position.highest_profit_pct >= 0.30:
            trailing_ma = float(ma_slow.iloc[-1])
            ma_label = f"{self.config.trailing_stop_ma}日EMA"
        else:
            trailing_ma = float(ma_fast.iloc[-1])
            ma_label = f"{self.config.trailing_stop_ma_fast}日EMA"

        if current_price < trailing_ma:
            return {"action": "full_sell",
                    "reason": f"跌破{ma_label}({trailing_ma:.2f})移动止损"}

        return None

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def can_open_position(self, current_positions: int) -> bool:
        return current_positions < self.config.max_positions

    def execute_partial_sell(self, position: Position) -> int:
        """部分止盈: 卖出一半仓位"""
        sell_shares = int(position.shares * self.config.partial_sell_ratio)
        sell_shares = (sell_shares // 100) * 100
        if sell_shares <= 0:
            sell_shares = position.shares
        return sell_shares
