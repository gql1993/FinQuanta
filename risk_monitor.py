"""
组合风险监控模块
实时计算持仓组合的 VaR、预期最大回撤、集中度等风险指标，
并在触发阈值时输出预警信号。

使用方式:
    from risk_monitor import PortfolioRiskMonitor
    monitor = PortfolioRiskMonitor()
    report = monitor.assess(positions, live_prices, daily_data_map)
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class RiskReport:
    """组合风险评估报告"""
    total_value: float = 0.0
    num_positions: int = 0

    var_95_1d: float = 0.0
    var_99_1d: float = 0.0
    cvar_95_1d: float = 0.0

    current_drawdown: float = 0.0
    peak_equity: float = 0.0
    max_single_exposure: float = 0.0
    max_single_name: str = ""
    concentration_hhi: float = 0.0

    alerts: list = field(default_factory=list)
    position_risks: list = field(default_factory=list)


class PortfolioRiskMonitor:
    def __init__(
        self,
        var_window: int = 60,
        var_confidence_95: float = 0.95,
        var_confidence_99: float = 0.99,
        max_drawdown_warn: float = 0.08,
        max_drawdown_danger: float = 0.15,
        max_single_exposure_warn: float = 0.30,
        max_concentration_hhi: float = 0.35,
    ):
        self.var_window = var_window
        self.var_95 = var_confidence_95
        self.var_99 = var_confidence_99
        self.max_dd_warn = max_drawdown_warn
        self.max_dd_danger = max_drawdown_danger
        self.max_single_warn = max_single_exposure_warn
        self.max_hhi = max_concentration_hhi

    def assess(
        self,
        positions: list[dict],
        live_prices: dict[str, float],
        daily_data_map: dict[str, pd.DataFrame],
        cash: float = 0.0,
        peak_equity: float = 0.0,
    ) -> RiskReport:
        report = RiskReport()
        if not positions:
            return report

        weights = []
        returns_matrix = []
        pos_risks = []

        for pos in positions:
            code = pos.get("code", "")
            shares = pos.get("shares", 0)
            entry = pos.get("entry_price", 0)
            price = live_prices.get(code, entry)
            mv = price * shares
            weights.append(mv)

            df = daily_data_map.get(code)
            ret_series = np.zeros(self.var_window)
            if df is not None and "close" in df.columns and len(df) >= 10:
                close = pd.to_numeric(df["close"], errors="coerce").dropna().values.astype(float)
                if len(close) >= 2:
                    daily_ret = np.diff(close) / close[:-1]
                    tail = daily_ret[-self.var_window:]
                    ret_series = np.zeros(self.var_window)
                    ret_series[-len(tail):] = tail

            returns_matrix.append(ret_series)

            vol = float(np.std(ret_series[-20:])) if len(ret_series) >= 20 else 0.0
            pos_risks.append({
                "代码": code,
                "名称": pos.get("name", ""),
                "市值": round(mv, 2),
                "日波动率": round(vol * 100, 2),
                "年化波动率": round(vol * np.sqrt(250) * 100, 1),
                "VaR_95_1d": round(mv * vol * 1.645, 2),
            })

        report.position_risks = pos_risks
        total_value = sum(weights)
        report.total_value = round(total_value, 2)
        report.num_positions = len(positions)

        if total_value <= 0:
            return report

        w = np.array(weights) / total_value
        ret_mat = np.array(returns_matrix)

        port_returns = np.dot(w, ret_mat)
        port_std = float(np.std(port_returns[-20:])) if len(port_returns) >= 20 else 0.0

        report.var_95_1d = round(total_value * port_std * 1.645, 2)
        report.var_99_1d = round(total_value * port_std * 2.326, 2)

        cutoff = np.percentile(port_returns, 5) if len(port_returns) >= 20 else 0
        tail_returns = port_returns[port_returns <= cutoff] if cutoff < 0 else port_returns[:1]
        report.cvar_95_1d = round(total_value * abs(float(np.mean(tail_returns))), 2) if len(tail_returns) > 0 else 0.0

        total_equity = total_value + cash
        report.peak_equity = max(peak_equity, total_equity)
        if report.peak_equity > 0:
            report.current_drawdown = round((report.peak_equity - total_equity) / report.peak_equity, 4)

        max_mv = max(weights) if weights else 0
        report.max_single_exposure = round(max_mv / total_value, 4) if total_value > 0 else 0
        max_idx = int(np.argmax(weights)) if weights else 0
        report.max_single_name = positions[max_idx].get("name", positions[max_idx].get("code", "")) if positions else ""

        report.concentration_hhi = round(float(np.sum(w ** 2)), 4)

        report.alerts = self._generate_alerts(report)
        return report

    def _generate_alerts(self, report: RiskReport) -> list[dict]:
        alerts = []

        if report.current_drawdown >= self.max_dd_danger:
            alerts.append({
                "level": "danger",
                "title": f"组合回撤达 {report.current_drawdown:.1%}",
                "action": "建议减仓至半仓以下",
                "reason": f"当前从峰值回撤 {report.current_drawdown:.1%}，超过危险阈值 {self.max_dd_danger:.0%}。",
            })
        elif report.current_drawdown >= self.max_dd_warn:
            alerts.append({
                "level": "warning",
                "title": f"组合回撤达 {report.current_drawdown:.1%}",
                "action": "关注并收紧止损",
                "reason": f"当前从峰值回撤 {report.current_drawdown:.1%}，接近警戒线 {self.max_dd_warn:.0%}。",
            })

        if report.max_single_exposure >= self.max_single_warn:
            alerts.append({
                "level": "warning",
                "title": f"单股集中度过高：{report.max_single_name}（{report.max_single_exposure:.0%}）",
                "action": "建议分散持仓",
                "reason": f"单只股票占组合 {report.max_single_exposure:.0%}，超过 {self.max_single_warn:.0%} 阈值。",
            })

        if report.concentration_hhi >= self.max_hhi:
            alerts.append({
                "level": "warning",
                "title": f"组合集中度偏高（HHI={report.concentration_hhi:.2f}）",
                "action": "建议增加持仓数或均衡仓位",
                "reason": f"HHI 指数 {report.concentration_hhi:.2f}，超过 {self.max_hhi:.2f} 阈值。",
            })

        if report.var_95_1d > report.total_value * 0.03:
            alerts.append({
                "level": "info",
                "title": f"日 VaR(95%) = ¥{report.var_95_1d:,.0f}",
                "action": "注意波动风险",
                "reason": f"95% 置信度下单日最大预期损失 ¥{report.var_95_1d:,.0f}，占组合 {report.var_95_1d / max(report.total_value, 1) * 100:.1f}%。",
            })

        if not alerts:
            alerts.append({
                "level": "success",
                "title": "组合风险可控",
                "action": "正常持有",
                "reason": "回撤、集中度、VaR 均在安全区间内。",
            })

        return alerts

    @staticmethod
    def summarize(report: RiskReport) -> pd.DataFrame:
        rows = [
            {"指标": "组合总市值", "值": f"¥{report.total_value:,.2f}"},
            {"指标": "持仓数", "值": str(report.num_positions)},
            {"指标": "VaR(95%) 1日", "值": f"¥{report.var_95_1d:,.2f}"},
            {"指标": "VaR(99%) 1日", "值": f"¥{report.var_99_1d:,.2f}"},
            {"指标": "CVaR(95%) 1日", "值": f"¥{report.cvar_95_1d:,.2f}"},
            {"指标": "当前回撤", "值": f"{report.current_drawdown:.2%}"},
            {"指标": "峰值权益", "值": f"¥{report.peak_equity:,.2f}"},
            {"指标": "最大单股敞口", "值": f"{report.max_single_exposure:.1%}（{report.max_single_name}）"},
            {"指标": "集中度HHI", "值": f"{report.concentration_hhi:.3f}"},
        ]
        return pd.DataFrame(rows)
