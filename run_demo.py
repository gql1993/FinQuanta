"""
快速演示: 选取 200 只代表性 A 股进行 SEPA 策略选股 + 回测
避免全市场 5000+ 只股票的下载时间。
"""
import time
import pandas as pd

from config import StrategyConfig
from data_fetcher import DataFetcher
from strategy import SEPAStrategy
from backtester import Backtester
from report import ReportGenerator


def main():
    config = StrategyConfig()
    config.data.start_date = "20220101"

    fetcher = DataFetcher(config.data)
    strategy = SEPAStrategy(config)
    backtester = Backtester(config)
    reporter = ReportGenerator()

    # ================================================================
    # 第1步: 获取股票列表，随机采样 200 只
    # ================================================================
    print("=" * 60)
    print("  股票魔法师 SEPA 策略 - 快速演示")
    print("=" * 60)

    print("\n[1/7] 获取 A 股列表...")
    stock_list = fetcher.get_stock_list()
    total = len(stock_list)
    print(f"  全市场: {total} 只")

    sample_size = 200
    stock_sample = stock_list.sample(n=sample_size, random_state=2024)
    print(f"  采样: {sample_size} 只（用于快速演示）")

    # ================================================================
    # 第2步: 下载日线数据
    # ================================================================
    print(f"\n[2/7] 下载 {sample_size} 只股票日线数据...")
    t0 = time.time()
    all_data = fetcher.get_all_daily_data(stock_sample)
    print(f"  有效数据: {len(all_data)} 只, 耗时 {time.time()-t0:.0f}s")

    if not all_data:
        print("  无有效数据，退出。")
        return

    # ================================================================
    # 第3步: 下载大盘指数
    # ================================================================
    print("\n[3/7] 下载沪深300指数数据...")
    index_df = fetcher.get_index_data()
    print(f"  数据量: {len(index_df)} 天")

    # ================================================================
    # 第4步: 当日选股
    # ================================================================
    print("\n[4/7] 执行 SEPA 选股（趋势模板 + VCP + 紧密收盘）...")
    candidates = strategy.screen_stocks(all_data)

    stock_names = dict(zip(stock_list["code"], stock_list["name"]))

    if candidates:
        print(f"\n  === 选股结果: {len(candidates)} 只通过 ===\n")
        header = f"  {'#':>3}  {'代码':>8}  {'名称':<8}  {'价格':>8}  {'RS':>4}  {'收缩':>4}  {'枢纽':>8}  {'紧密':>4}  {'突破':>4}"
        print(header)
        print("  " + "-" * 75)
        for i, c in enumerate(candidates[:30], 1):
            code = c["code"]
            name = stock_names.get(code, "?")
            tight = "是" if c.get("tight_closes") else "否"
            bo = "是" if c.get("breakout_today") else "否"
            print(f"  {i:>3}  {code:>8}  {name:<8}  {c['close']:>8.2f}  "
                  f"{c['rs_rating']:>4.0f}  {c['num_contractions']:>4}  "
                  f"{c['pivot_price']:>8.2f}  {tight:>4}  {bo:>4}")
    else:
        print("\n  当前样本中无完全符合条件的股票（正常，非牛市时候选较少）")

    # ================================================================
    # 第5步: 生成回测信号
    # ================================================================
    print(f"\n[5/7] 生成回测交易信号...")
    t0 = time.time()
    signal_data, market_df = strategy.generate_signals_for_backtest(all_data, index_df)
    print(f"  处理完成: {len(signal_data)} 只, 耗时 {time.time()-t0:.0f}s")

    # 统计信号数量
    total_signals = sum(df["buy_signal"].sum() for df in signal_data.values())
    print(f"  总买入信号: {total_signals} 个")

    # ================================================================
    # 第6步: 运行回测
    # ================================================================
    print(f"\n[6/7] 运行回测引擎（2022-01 至今）...")
    t0 = time.time()
    result = backtester.run(
        signal_data,
        market_regime_df=market_df,
        start_date="20220601",
    )
    print(f"  回测完成, 耗时 {time.time()-t0:.0f}s")

    # ================================================================
    # 第7步: 生成报告
    # ================================================================
    print(f"\n[7/7] 生成绩效报告...")
    report_dir = reporter.generate(result, benchmark_df=index_df, show=False)

    # 打印关键交易记录
    if result.trades:
        print(f"\n  === 最近 10 笔交易 ===\n")
        print(f"  {'代码':>8}  {'买入日':>12}  {'买入价':>8}  {'卖出日':>12}  {'卖出价':>8}  {'盈亏%':>8}  {'天数':>4}  {'原因'}")
        print("  " + "-" * 95)
        for t in result.trades[-10:]:
            name = stock_names.get(t.code, "")
            print(f"  {t.code:>8}  {t.entry_date:>12}  {t.entry_price:>8.2f}  "
                  f"{t.exit_date:>12}  {t.exit_price:>8.2f}  {t.pnl_pct:>7.1%}  "
                  f"{t.hold_days:>4}  {t.exit_reason[:30]}")

    print(f"\n  报告目录: {report_dir}")
    print("\n  完成!")


if __name__ == "__main__":
    main()
