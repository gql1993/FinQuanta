"""
回测引擎 (对应《股票魔法师》完整交易系统)
支持:
  - A 股特有规则: T+1、涨跌停、印花税
  - 市场环境过滤: 大盘转弱时停止买入
  - 完整卖出规则: 硬止损、渐进止损、高潮顶、时间止损、8周规则、Stage退出
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import StrategyConfig
from risk_manager import RiskManager, Position


@dataclass
class Trade:
    """交易记录"""
    code: str
    entry_date: str
    entry_price: float
    exit_date: str = ""
    exit_price: float = 0.0
    shares: int = 0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_days: int = 0
    exit_reason: str = ""
    strategy_id: str = ""
    entry_reason: str = ""
    entry_phase: str = ""
    entry_heat: float = 0.0
    entry_valuation: float = 0.0
    entry_crowding: float = 0.0


@dataclass
class BacktestResult:
    """回测结果"""
    initial_capital: float = 0.0
    final_capital: float = 0.0
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    turnover_ratio: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_hold_days: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    max_consecutive_losses: int = 0
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    trades: list = field(default_factory=list)


class Backtester:
    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()
        self.risk_manager = RiskManager(self.config.risk)
        self.bt = self.config.backtest

    def run(
        self,
        signal_data: dict[str, pd.DataFrame],
        market_regime_df: pd.DataFrame | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> BacktestResult:
        """
        运行回测。
        signal_data: {code: DataFrame with buy_signal, trend_pass, ma*, vol_ma50, spread_ma20}
        market_regime_df: 含 market_ok 列的大盘数据
        """
        all_dates = self._build_date_index(signal_data, start_date, end_date)
        if all_dates.empty:
            return BacktestResult()

        # 预构建市场环境查询
        market_ok_map = {}
        if market_regime_df is not None and "market_ok" in market_regime_df.columns:
            for _, row in market_regime_df.iterrows():
                market_ok_map[pd.Timestamp(row["date"])] = bool(row["market_ok"])

        capital = self.bt.initial_capital
        cash = capital
        positions: dict[str, Position] = {}
        trades: list[Trade] = []
        equity_records = []
        pending_buys: list[dict] = []

        for current_date in all_dates:
            date_str = current_date.strftime("%Y-%m-%d")

            # 市场环境判断 (第9章) — 使用前一交易日信号，避免前视偏差。
            prev_dates = [d for d in all_dates if d < current_date]
            prev_date = prev_dates[-1] if prev_dates else None
            market_is_ok = market_ok_map.get(prev_date, True) if prev_date else True

            # ===========================================================
            # 1. 执行前日挂起的买入 (T+1)
            # ===========================================================
            for buy in pending_buys:
                code = buy["code"]
                if code not in signal_data or code in positions:
                    continue
                day_data = self._get_day_data(signal_data[code], current_date)
                if day_data is None or self._is_limit_up(day_data):
                    continue

                entry_price = float(day_data["open"])
                entry_price = self._apply_slippage(entry_price, "buy")
                shares = buy["shares"]
                cost = entry_price * shares
                commission = max(cost * self.bt.commission_rate, 5)
                total_cost = cost + commission

                if total_cost <= cash:
                    cash -= total_cost
                    stop_loss = self.risk_manager.get_stop_loss_price(entry_price)
                    positions[code] = Position(
                        code=code,
                        entry_date=date_str,
                        entry_price=entry_price,
                        shares=shares,
                        stop_loss=stop_loss,
                        strategy_id=buy.get("strategy_id", ""),
                        entry_reason=buy.get("entry_reason", ""),
                        entry_phase=buy.get("entry_phase", ""),
                        entry_heat=float(buy.get("entry_heat", 0.0) or 0.0),
                        entry_valuation=float(buy.get("entry_valuation", 0.0) or 0.0),
                        entry_crowding=float(buy.get("entry_crowding", 0.0) or 0.0),
                    )
            pending_buys.clear()

            # ===========================================================
            # 2. 检查现有持仓的卖出信号 (第10-12章完整规则)
            # ===========================================================
            codes_to_remove = []
            for code, pos in positions.items():
                if code not in signal_data:
                    continue
                df_code = signal_data[code]
                day_data = self._get_day_data(df_code, current_date)
                if day_data is None:
                    # 退市/数据断裂：连续缺失超过 5 个交易日强制平仓。
                    if not hasattr(pos, "_missing_days"):
                        pos._missing_days = 0
                    pos._missing_days += 1
                    if pos._missing_days >= 5:
                        cash += self._force_exit(pos, date_str, "数据断裂/疑似退市", trades, codes_to_remove)
                    continue
                if hasattr(pos, "_missing_days"):
                    pos._missing_days = 0

                current_price = float(day_data["close"])
                current_high = float(day_data["high"])
                current_low = float(day_data["low"])
                current_volume = float(day_data.get("volume", 0))

                # 获取到当前日的历史数据(用于阶段分析和高潮顶检测)
                idx_list = df_code.index[df_code["date"] == current_date].tolist()
                df_history = None
                if idx_list:
                    df_history = df_code.iloc[:idx_list[0] + 1]

                # 策略特有卖出规则优先于通用风控，用于体现不同体系的退出逻辑差异。
                if bool(day_data.get("strategy_exit_signal", False)):
                    exit_signal = {
                        "action": "full_sell",
                        "reason": str(day_data.get("strategy_exit_reason", "策略规则退出")),
                    }
                else:
                    exit_signal = self.risk_manager.check_exit_signals(
                        position=pos,
                        current_price=current_price,
                        current_high=current_high,
                        current_low=current_low,
                        current_volume=current_volume,
                        day_data=day_data,
                        df_history=df_history,
                    )

                if exit_signal["action"] == "full_sell":
                    if self._is_limit_down(day_data):
                        continue
                    cash += self._execute_full_sell(
                        pos, current_price, date_str, exit_signal["reason"],
                        trades, codes_to_remove,
                    )

                elif exit_signal["action"] == "partial_sell":
                    if self._is_limit_down(day_data):
                        continue
                    sell_shares = self.risk_manager.execute_partial_sell(pos)
                    if sell_shares >= pos.shares:
                        cash += self._execute_full_sell(
                            pos, current_price, date_str, exit_signal["reason"],
                            trades, codes_to_remove,
                        )
                    else:
                        cash += self._execute_partial_sell(
                            pos, sell_shares, current_price, date_str,
                            exit_signal["reason"], trades,
                        )

            for code in codes_to_remove:
                positions.pop(code, None)

            # ===========================================================
            # 3. 扫描新买入信号 (仅市场环境允许时)
            # ===========================================================
            if market_is_ok and self.risk_manager.can_open_position(len(positions)):
                buy_candidates = []
                for code, df in signal_data.items():
                    if code in positions:
                        continue
                    day_data = self._get_day_data(df, current_date)
                    if day_data is None:
                        continue
                    if day_data.get("buy_signal", False):
                        rs = day_data.get("rs_rating", 0)
                        buy_candidates.append((code, rs, day_data))

                buy_candidates.sort(key=lambda x: x[1], reverse=True)
                slots = self.config.risk.max_positions - len(positions) - len(pending_buys)

                for code, rs, day_data in buy_candidates[:max(slots, 0)]:
                    entry_est = float(day_data["close"])
                    stop = self.risk_manager.get_stop_loss_price(entry_est)
                    shares = self.risk_manager.calculate_position_size(cash, entry_est, stop)
                    unit_scale = float(day_data.get("risk_unit_scale", 1.0))
                    if unit_scale > 0:
                        shares = int((shares * unit_scale) // 100) * 100
                    if shares >= 100:
                        pending_buys.append({
                            "code": code,
                            "shares": shares,
                            "strategy_id": str(day_data.get("strategy_id", "")),
                            "entry_reason": str(day_data.get("strategy_entry_reason", "")),
                            "entry_phase": str(day_data.get("emotion_phase", "")),
                            "entry_heat": float(day_data.get("sector_heat_score", 0.0) or 0.0),
                            "entry_valuation": float(day_data.get("valuation_score", 0.0) or 0.0),
                            "entry_crowding": float(day_data.get("crowding_score", 0.0) or 0.0),
                        })

            # ===========================================================
            # 4. 记录当日权益
            # ===========================================================
            position_value = 0.0
            for code, pos in positions.items():
                day_data = self._get_day_data(signal_data.get(code, pd.DataFrame()), current_date)
                if day_data is not None:
                    position_value += float(day_data["close"]) * pos.shares
                else:
                    position_value += pos.entry_price * pos.shares

            total_equity = cash + position_value
            equity_records.append({
                "date": current_date,
                "cash": cash,
                "position_value": position_value,
                "total_equity": total_equity,
                "num_positions": len(positions),
                "market_ok": market_is_ok,
            })

        equity_df = pd.DataFrame(equity_records)
        return self._compute_metrics(equity_df, trades, capital)

    # ------------------------------------------------------------------
    # 卖出执行
    # ------------------------------------------------------------------

    def _execute_full_sell(
        self, pos: Position, current_price: float, date_str: str,
        reason: str, trades: list, codes_to_remove: list,
    ) -> float:
        """记录完全卖出交易，返回回收现金"""
        sell_price = self._apply_slippage(current_price, "sell")
        entry_cost = pos.entry_price * pos.shares
        revenue = sell_price * pos.shares
        commission = max(revenue * self.bt.commission_rate, 5)
        stamp_tax = revenue * self.bt.stamp_tax_rate
        net_revenue = revenue - commission - stamp_tax
        pnl = net_revenue - entry_cost

        trades.append(Trade(
            code=pos.code,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=date_str,
            exit_price=sell_price,
            shares=pos.shares,
            pnl=pnl,
            pnl_pct=pnl / entry_cost if entry_cost > 0 else 0,
            hold_days=self._calc_hold_days(pos.entry_date, date_str),
            exit_reason=reason,
            strategy_id=pos.strategy_id,
            entry_reason=pos.entry_reason,
            entry_phase=pos.entry_phase,
            entry_heat=pos.entry_heat,
            entry_valuation=pos.entry_valuation,
            entry_crowding=pos.entry_crowding,
        ))
        codes_to_remove.append(pos.code)
        return net_revenue

    def _execute_partial_sell(
        self, pos: Position, sell_shares: int, current_price: float,
        date_str: str, reason: str, trades: list,
    ) -> float:
        """记录部分止盈交易，返回回收现金"""
        sell_price = self._apply_slippage(current_price, "sell")
        entry_cost_partial = pos.entry_price * sell_shares
        revenue = sell_price * sell_shares
        commission = max(revenue * self.bt.commission_rate, 5)
        stamp_tax = revenue * self.bt.stamp_tax_rate
        net_revenue = revenue - commission - stamp_tax
        pnl = net_revenue - entry_cost_partial

        trades.append(Trade(
            code=pos.code,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=date_str,
            exit_price=sell_price,
            shares=sell_shares,
            pnl=pnl,
            pnl_pct=pnl / entry_cost_partial if entry_cost_partial > 0 else 0,
            hold_days=self._calc_hold_days(pos.entry_date, date_str),
            exit_reason=f"部分止盈({reason})",
            strategy_id=pos.strategy_id,
            entry_reason=pos.entry_reason,
            entry_phase=pos.entry_phase,
            entry_heat=pos.entry_heat,
            entry_valuation=pos.entry_valuation,
            entry_crowding=pos.entry_crowding,
        ))
        pos.shares -= sell_shares
        pos.partial_sold = True
        return net_revenue

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _build_date_index(self, signal_data, start_date, end_date) -> pd.DatetimeIndex:
        all_dates = set()
        for df in signal_data.values():
            all_dates.update(df["date"].tolist())
        dates = sorted(all_dates)
        idx = pd.DatetimeIndex(dates)
        if start_date:
            idx = idx[idx >= pd.Timestamp(start_date)]
        if end_date:
            idx = idx[idx <= pd.Timestamp(end_date)]
        return idx

    @staticmethod
    def _get_day_data(df: pd.DataFrame, date) -> dict | None:
        if df.empty:
            return None
        mask = df["date"] == date
        if not mask.any():
            return None
        return df.loc[mask].iloc[0].to_dict()

    def _is_limit_up(self, day_data: dict) -> bool:
        pct = day_data.get("pct_change", 0)
        if isinstance(pct, str):
            try:
                pct = float(pct)
            except (ValueError, TypeError):
                return False
        code = str(day_data.get("code", ""))
        limit = self.bt.limit_up_pct_star if code.startswith(("30", "68")) else self.bt.limit_up_pct
        return pct >= limit * 100 - 0.1

    def _is_limit_down(self, day_data: dict) -> bool:
        pct = day_data.get("pct_change", 0)
        if isinstance(pct, str):
            try:
                pct = float(pct)
            except (ValueError, TypeError):
                return False
        code = str(day_data.get("code", ""))
        limit = self.bt.limit_up_pct_star if code.startswith(("30", "68")) else self.bt.limit_up_pct
        return pct <= -(limit * 100 - 0.1)

    def _apply_slippage(self, price: float, direction: str,
                        volume: float = 0, shares: int = 0) -> float:
        """
        成交量加权滑点模型：
        基础滑点 + 订单量占比带来的额外冲击（大单在低流动性下滑点更大）。
        """
        base = self.bt.slippage
        impact = 0.0
        if volume > 0 and shares > 0:
            fill_ratio = shares / max(volume, 1.0)
            impact = fill_ratio * 0.005
        total_slip = base + impact
        if direction == "buy":
            return round(price * (1 + total_slip), 2)
        return round(price * (1 - total_slip), 2)

    def _force_exit(self, pos: "Position", date_str: str, reason: str,
                    trades: list, codes_to_remove: list) -> float:
        """退市/数据断裂时强制平仓（按买入价 × 0.5 估值，模拟最差情形）。"""
        est_price = pos.entry_price * 0.5
        entry_cost = pos.entry_price * pos.shares
        revenue = est_price * pos.shares
        commission = max(revenue * self.bt.commission_rate, 5)
        stamp_tax = revenue * self.bt.stamp_tax_rate
        net_revenue = revenue - commission - stamp_tax
        pnl = net_revenue - entry_cost
        trades.append(Trade(
            code=pos.code,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=date_str,
            exit_price=est_price,
            shares=pos.shares,
            pnl=pnl,
            pnl_pct=pnl / entry_cost if entry_cost > 0 else 0,
            hold_days=self._calc_hold_days(pos.entry_date, date_str),
            exit_reason=reason,
            strategy_id=getattr(pos, "strategy_id", ""),
            entry_reason=getattr(pos, "entry_reason", ""),
        ))
        codes_to_remove.append(pos.code)
        return net_revenue

    @staticmethod
    def _calc_hold_days(entry_date: str, exit_date: str) -> int:
        return (pd.Timestamp(exit_date) - pd.Timestamp(entry_date)).days

    # ------------------------------------------------------------------
    # 绩效指标
    # ------------------------------------------------------------------

    def _compute_metrics(self, equity_df, trades, initial_capital) -> BacktestResult:
        result = BacktestResult()
        result.initial_capital = initial_capital
        result.equity_curve = equity_df
        result.trades = trades

        if equity_df.empty:
            return result

        result.final_capital = float(equity_df["total_equity"].iloc[-1])
        result.total_return = (result.final_capital - initial_capital) / initial_capital

        days = (equity_df["date"].iloc[-1] - equity_df["date"].iloc[0]).days
        if days > 0:
            result.annual_return = (1 + result.total_return) ** (365 / days) - 1

        equity = equity_df["total_equity"].values
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        result.max_drawdown = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

        daily_returns = equity_df["total_equity"].pct_change().dropna()
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            excess_return = daily_returns.mean() - 0.03 / 250
            result.sharpe_ratio = round(excess_return / daily_returns.std() * np.sqrt(250), 2)
            downside = daily_returns[daily_returns < 0]
            if len(downside) > 1 and downside.std() > 0:
                result.sortino_ratio = round(excess_return / downside.std() * np.sqrt(250), 2)
        if result.max_drawdown > 0:
            result.calmar_ratio = round(result.annual_return / result.max_drawdown, 2)

        result.total_trades = len(trades)
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]
        result.winning_trades = len(winning)
        result.losing_trades = len(losing)

        if result.total_trades > 0:
            result.win_rate = result.winning_trades / result.total_trades
            result.avg_hold_days = np.mean([t.hold_days for t in trades])

        if winning:
            result.avg_win_pct = np.mean([t.pnl_pct for t in winning])
        if losing:
            result.avg_loss_pct = np.mean([t.pnl_pct for t in losing])

        avg_win = np.mean([t.pnl for t in winning]) if winning else 0
        avg_loss = abs(np.mean([t.pnl for t in losing])) if losing else 1
        result.profit_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

        # 最大连续亏损
        result.max_consecutive_losses = self._max_consecutive_losses(trades)
        # 换手率（近似）：总成交额 / 平均权益
        if trades and not equity_df.empty:
            total_turnover = 0.0
            for t in trades:
                total_turnover += t.entry_price * t.shares
                total_turnover += t.exit_price * t.shares
            avg_equity = float(equity_df["total_equity"].mean()) if len(equity_df) > 0 else initial_capital
            if avg_equity > 0:
                result.turnover_ratio = total_turnover / avg_equity

        return result

    @staticmethod
    def _max_consecutive_losses(trades: list) -> int:
        max_streak = 0
        current_streak = 0
        for t in trades:
            if t.pnl <= 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        return max_streak
