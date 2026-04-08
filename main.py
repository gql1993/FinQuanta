"""
股票魔法师 SEPA 策略 - 主入口
支持两种模式：
  1. screen   - 当日选股，输出符合条件的候选列表
  2. backtest - 历史回测，输出绩效报告
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from config import StrategyConfig
from data_fetcher import DataFetcher
from strategy import SEPAStrategy
from backtester import Backtester
from report import ReportGenerator


def run_screen(config: StrategyConfig, top_n: int = 20, use_fundamental: bool = False):
    """选股模式"""
    print("=" * 60)
    print("  股票魔法师 SEPA 策略 - 选股模式")
    print("  (趋势模板 + VCP形态 + 紧密收盘确认)")
    print("=" * 60)

    fetcher = DataFetcher(config.data)
    strategy = SEPAStrategy(config)

    print("\n[1/5] 获取 A 股股票列表...")
    stock_list = fetcher.get_stock_list()
    print(f"  共 {len(stock_list)} 只股票")

    print("\n[2/5] 下载日线数据（首次运行较慢，后续使用缓存）...")
    all_data = fetcher.get_all_daily_data(stock_list)
    print(f"  有效数据: {len(all_data)} 只")

    # 市场环境检查
    print("\n[3/5] 检查市场环境（分布日分析）...")
    index_df = fetcher.get_index_data()
    if not index_df.empty:
        market_df = strategy.market_filter.compute_regime(index_df)
        latest_market = bool(market_df["market_ok"].iloc[-1]) if not market_df.empty else True
        dist_count = int(market_df["dist_count"].iloc[-1]) if "dist_count" in market_df.columns else 0
        status = "正常，可以买入" if latest_market else f"警告: 市场转弱({dist_count}个分布日)，谨慎买入"
        print(f"  市场状态: {status}")

    print("\n[4/5] 执行 SEPA 选股流程...")
    financial_df = None
    get_finance_fn = None
    if use_fundamental:
        print("  加载基本面数据...")
        financial_df = fetcher.get_financial_data()
        get_finance_fn = fetcher.get_stock_financial_report

    candidates = strategy.screen_stocks(
        all_data,
        financial_df=financial_df,
        get_finance_fn=get_finance_fn if use_fundamental else None,
    )

    print(f"\n[5/5] 选股结果")
    print("=" * 60)

    if not candidates:
        print("  当前无符合条件的股票。")
        return

    stock_names = dict(zip(stock_list["code"], stock_list["name"]))

    print(f"\n  共 {len(candidates)} 只股票通过筛选，显示前 {top_n} 只:\n")
    header = (f"  {'排名':>4}  {'代码':>8}  {'名称':<8}  {'价格':>8}  {'RS评级':>6}  "
              f"{'收缩次数':>8}  {'枢纽点':>8}  {'紧密收盘':>8}  {'突破':>4}")
    print(header)
    print("  " + "-" * 90)

    for i, c in enumerate(candidates[:top_n], 1):
        code = c["code"]
        name = stock_names.get(code, "")
        tight = "是" if c.get("tight_closes", False) else "否"
        breakout = "是" if c["breakout_today"] else "否"
        print(
            f"  {i:>4}  {code:>8}  {name:<8}  {c['close']:>8.2f}  "
            f"{c['rs_rating']:>6.0f}  {c['num_contractions']:>8}  "
            f"{c['pivot_price']:>8.2f}  {tight:>8}  {breakout:>4}"
        )

    print("\n  [提示] 紧密收盘 + 突破 = 最佳买入信号")
    print("  [风控] 买入后立即设置止损 = 入场价 × 92%")
    print()


def run_backtest(
    config: StrategyConfig,
    sample_size: int = 100,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """回测模式"""
    print("=" * 60)
    print("  股票魔法师 SEPA 策略 - 回测模式")
    print("  (含: 渐进止损/高潮顶/时间止损/8周规则/市场过滤)")
    print("=" * 60)

    fetcher = DataFetcher(config.data)
    strategy = SEPAStrategy(config)
    backtester = Backtester(config)
    reporter = ReportGenerator()

    print("\n[1/6] 获取股票列表...")
    stock_list = fetcher.get_stock_list()

    if sample_size and sample_size < len(stock_list):
        print(f"  使用随机子集: {sample_size} 只（总共 {len(stock_list)} 只）")
        stock_list = stock_list.sample(n=sample_size, random_state=42)

    print("\n[2/6] 下载日线数据...")
    all_data = fetcher.get_all_daily_data(stock_list)
    print(f"  有效数据: {len(all_data)} 只")

    if not all_data:
        print("  无有效数据，退出。")
        return

    print("\n[3/6] 下载大盘指数数据（市场环境分析）...")
    index_df = fetcher.get_index_data()

    print("\n[4/6] 生成交易信号（逐日计算趋势+VCP+紧密收盘）...")
    signal_data, market_df = strategy.generate_signals_for_backtest(all_data, index_df)
    print(f"  处理完成: {len(signal_data)} 只股票")

    print("\n[5/6] 运行回测引擎...")
    result = backtester.run(
        signal_data,
        market_regime_df=market_df,
        start_date=start_date,
        end_date=end_date,
    )

    print("\n[6/6] 生成绩效报告...")
    benchmark_df = index_df
    reporter.generate(result, benchmark_df=benchmark_df, show=False)


def main():
    parser = argparse.ArgumentParser(
        description="股票魔法师 SEPA 策略 - A 股量化选股与回测系统"
    )
    parser.add_argument(
        "mode", choices=["screen", "backtest"],
        help="运行模式: screen=当日选股, backtest=历史回测",
    )
    parser.add_argument("--start-date", type=str, default="20210101",
                        help="回测起始日期 (默认: 20210101)")
    parser.add_argument("--end-date", type=str, default="",
                        help="回测结束日期 (默认: 至今)")
    parser.add_argument("--sample-size", type=int, default=100,
                        help="回测股票数量 (默认: 100, 0=全部)")
    parser.add_argument("--top-n", type=int, default=20,
                        help="选股显示前N只 (默认: 20)")
    parser.add_argument("--fundamental", action="store_true",
                        help="启用基本面过滤")

    args = parser.parse_args()
    config = StrategyConfig()

    if args.start_date:
        config.data.start_date = args.start_date

    if args.mode == "screen":
        run_screen(config, top_n=args.top_n, use_fundamental=args.fundamental)
    elif args.mode == "backtest":
        sample = args.sample_size if args.sample_size > 0 else None
        run_backtest(config, sample_size=sample,
                     start_date=args.start_date, end_date=args.end_date or None)


if __name__ == "__main__":
    main()
