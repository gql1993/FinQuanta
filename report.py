"""
绩效报告与可视化模块
生成资金曲线、回撤分析、交易统计、卖出原因分布等图表和报告。
"""
import os
from collections import Counter
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from backtester import BacktestResult

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


class ReportGenerator:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(
        self,
        result: BacktestResult,
        benchmark_df: pd.DataFrame | None = None,
        show: bool = True,
    ) -> str:
        """生成完整回测报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = os.path.join(self.output_dir, f"report_{timestamp}")
        os.makedirs(report_dir, exist_ok=True)

        summary = self._build_summary(result)
        with open(os.path.join(report_dir, "summary.txt"), "w", encoding="utf-8") as f:
            f.write(summary)
        print(summary)

        for name, fn, args in [
            ("equity_curve", self._plot_equity_curve, (result, benchmark_df, report_dir, show)),
            ("drawdown", self._plot_drawdown, (result, report_dir, show)),
            ("monthly_returns", self._plot_monthly_returns, (result, report_dir, show)),
            ("exit_reasons", self._plot_exit_reasons, (result, report_dir, show)),
            ("pnl_distribution", self._plot_pnl_distribution, (result, report_dir, show)),
        ]:
            try:
                fn(*args)
            except Exception as e:
                print(f"  [WARN] 生成 {name} 图表失败: {e}")

        self._save_trade_log(result, report_dir)

        print(f"\n报告已保存到: {report_dir}")
        return report_dir

    # ------------------------------------------------------------------
    # 文字摘要 (含新增指标)
    # ------------------------------------------------------------------

    def _build_summary(self, result: BacktestResult) -> str:
        lines = [
            "=" * 60,
            "    SEPA 策略回测报告 (《股票魔法师》完整规则)",
            "=" * 60,
            "",
            "  --- 收益指标 ---",
            f"  初始资金:        {result.initial_capital:>15,.2f} 元",
            f"  最终资金:        {result.final_capital:>15,.2f} 元",
            f"  总收益率:        {result.total_return:>14.2%}",
            f"  年化收益率:      {result.annual_return:>14.2%}",
            "",
            "  --- 风险指标 ---",
            f"  最大回撤:        {result.max_drawdown:>14.2%}",
            f"  夏普比率:        {result.sharpe_ratio:>14.2f}",
            f"  最大连续亏损:    {result.max_consecutive_losses:>14d} 笔",
            "",
            "  --- 交易统计 ---",
            f"  总交易次数:      {result.total_trades:>14d}",
            f"  盈利次数:        {result.winning_trades:>14d}",
            f"  亏损次数:        {result.losing_trades:>14d}",
            f"  胜率:            {result.win_rate:>14.2%}",
            f"  盈亏比:          {result.profit_loss_ratio:>14.2f}",
            f"  平均盈利幅度:    {result.avg_win_pct:>14.2%}",
            f"  平均亏损幅度:    {result.avg_loss_pct:>14.2%}",
            f"  平均持仓天数:    {result.avg_hold_days:>14.1f}",
            "",
            "  --- 卖出规则触发统计 ---",
        ]

        if result.trades:
            reasons = Counter(t.exit_reason.split(":")[0] for t in result.trades)
            for reason, count in reasons.most_common():
                lines.append(f"    {reason:<20} {count:>5} 次")

        lines.extend(["", "=" * 60])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 资金曲线
    # ------------------------------------------------------------------

    def _plot_equity_curve(self, result, benchmark_df, report_dir, show):
        eq = result.equity_curve
        if eq.empty:
            return

        fig, axes = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1], sharex=True)

        # 上图: 净值曲线
        ax = axes[0]
        equity_norm = eq["total_equity"] / result.initial_capital
        ax.plot(eq["date"], equity_norm, label="SEPA策略", linewidth=1.5)

        if benchmark_df is not None and not benchmark_df.empty:
            bench = benchmark_df.copy()
            bench["date"] = pd.to_datetime(bench["date"])
            bench = bench[(bench["date"] >= eq["date"].iloc[0])
                          & (bench["date"] <= eq["date"].iloc[-1])]
            if not bench.empty:
                bench_norm = bench["close"] / bench["close"].iloc[0]
                ax.plot(bench["date"], bench_norm, label="沪深300", linewidth=1, alpha=0.7)

        ax.set_title("资金曲线（归一化净值）", fontsize=14)
        ax.set_ylabel("净值")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # 下图: 持仓数量 + 市场状态
        ax2 = axes[1]
        ax2.fill_between(eq["date"], 0, eq["num_positions"], alpha=0.5, label="持仓数")
        if "market_ok" in eq.columns:
            market_bad = eq[~eq["market_ok"]]
            if not market_bad.empty:
                ax2.scatter(market_bad["date"],
                            [0.1] * len(market_bad),
                            c="red", s=2, label="市场转弱", zorder=5)
        ax2.set_ylabel("持仓数")
        ax2.set_xlabel("日期")
        ax2.legend(loc="upper left")
        ax2.grid(True, alpha=0.3)

        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(os.path.join(report_dir, "equity_curve.png"), dpi=150)
        if show:
            plt.show()
        plt.close(fig)

    # ------------------------------------------------------------------
    # 回撤分析
    # ------------------------------------------------------------------

    def _plot_drawdown(self, result, report_dir, show):
        eq = result.equity_curve
        if eq.empty:
            return

        equity = eq["total_equity"].values
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak * 100

        fig, ax = plt.subplots(figsize=(14, 4))
        ax.fill_between(eq["date"], 0, -drawdown, color="red", alpha=0.4)
        ax.set_title("回撤分析", fontsize=14)
        ax.set_xlabel("日期")
        ax.set_ylabel("回撤 (%)")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(os.path.join(report_dir, "drawdown.png"), dpi=150)
        if show:
            plt.show()
        plt.close(fig)

    # ------------------------------------------------------------------
    # 月度收益热力图
    # ------------------------------------------------------------------

    def _plot_monthly_returns(self, result, report_dir, show):
        eq = result.equity_curve
        if eq.empty:
            return

        df = eq[["date", "total_equity"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        monthly = df["total_equity"].resample("ME").last()
        monthly_ret = monthly.pct_change().dropna()
        if monthly_ret.empty:
            return

        monthly_ret_df = pd.DataFrame({
            "year": monthly_ret.index.year,
            "month": monthly_ret.index.month,
            "return": monthly_ret.values,
        })

        pivot = monthly_ret_df.pivot_table(index="year", columns="month", values="return", aggfunc="first")
        pivot.columns = [f"{m}月" for m in pivot.columns]

        fig, ax = plt.subplots(figsize=(12, max(3, len(pivot) * 0.6 + 1)))
        im = ax.imshow(pivot.values * 100, cmap="RdYlGn", aspect="auto", vmin=-10, vmax=10)

        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index)

        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                val = pivot.values[i, j]
                if not np.isnan(val):
                    ax.text(j, i, f"{val*100:.1f}%", ha="center", va="center", fontsize=8)

        ax.set_title("月度收益率 (%)", fontsize=14)
        fig.colorbar(im, ax=ax, shrink=0.8, label="%")
        fig.tight_layout()
        fig.savefig(os.path.join(report_dir, "monthly_returns.png"), dpi=150)
        if show:
            plt.show()
        plt.close(fig)

    # ------------------------------------------------------------------
    # 卖出原因分布饼图
    # ------------------------------------------------------------------

    def _plot_exit_reasons(self, result, report_dir, show):
        if not result.trades:
            return

        reasons = Counter()
        for t in result.trades:
            key = t.exit_reason.split(":")[0] if ":" in t.exit_reason else t.exit_reason
            reasons[key] += 1

        if not reasons:
            return

        fig, ax = plt.subplots(figsize=(8, 8))
        labels = list(reasons.keys())
        sizes = list(reasons.values())
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90)
        ax.set_title("卖出原因分布", fontsize=14)
        fig.tight_layout()
        fig.savefig(os.path.join(report_dir, "exit_reasons.png"), dpi=150)
        if show:
            plt.show()
        plt.close(fig)

    # ------------------------------------------------------------------
    # 单笔盈亏分布直方图
    # ------------------------------------------------------------------

    def _plot_pnl_distribution(self, result, report_dir, show):
        if not result.trades:
            return

        pnl_pcts = [t.pnl_pct * 100 for t in result.trades]

        fig, ax = plt.subplots(figsize=(10, 5))
        colors = ["green" if p > 0 else "red" for p in pnl_pcts]
        ax.bar(range(len(pnl_pcts)), pnl_pcts, color=colors, width=1.0, alpha=0.7)
        ax.axhline(y=0, color="black", linewidth=0.5)
        ax.set_title("单笔交易盈亏分布 (%)", fontsize=14)
        ax.set_xlabel("交易序号")
        ax.set_ylabel("盈亏 (%)")
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(os.path.join(report_dir, "pnl_distribution.png"), dpi=150)
        if show:
            plt.show()
        plt.close(fig)

    # ------------------------------------------------------------------
    # 交易记录
    # ------------------------------------------------------------------

    def _save_trade_log(self, result, report_dir):
        if not result.trades:
            return

        records = []
        for t in result.trades:
            records.append({
                "股票代码": t.code,
                "买入日期": t.entry_date,
                "买入价格": round(t.entry_price, 2),
                "卖出日期": t.exit_date,
                "卖出价格": round(t.exit_price, 2),
                "股数": t.shares,
                "盈亏(元)": round(t.pnl, 2),
                "盈亏(%)": f"{t.pnl_pct:.2%}",
                "持仓天数": t.hold_days,
                "卖出原因": t.exit_reason,
            })

        df = pd.DataFrame(records)
        df.to_csv(os.path.join(report_dir, "trades.csv"), index=False, encoding="utf-8-sig")
        print(f"\n交易记录: {len(records)} 笔")
