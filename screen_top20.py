"""
全面筛选 A 股潜力股（Top 20）
基于 Minervini SEPA 策略:
  1. 趋势模板 8 大条件
  2. VCP 波动收缩形态
  3. 相对强度评级 (RS Rating)
  4. 接近枢纽点 / 突破状态
  5. 紧密收盘确认
  6. 市场环境判断
"""
import time
import numpy as np
import pandas as pd

from config import StrategyConfig
from data_fetcher import DataFetcher
from trend_template import TrendTemplate
from vcp_detector import VCPDetector
from strategy import MarketRegimeFilter


def main():
    config = StrategyConfig()
    config.data.start_date = "20220101"

    fetcher = DataFetcher(config.data)
    tt = TrendTemplate(config.trend)
    vcp = VCPDetector(config.vcp)
    mrf = MarketRegimeFilter(config.market)

    print("=" * 70)
    print("  SEPA 策略 A 股潜力股筛选 (Top 20)")
    print("  基于《股票魔法师》Mark Minervini 选股体系")
    print("=" * 70)

    # ================================================================
    # 第1步: 获取股票列表，采样 500 只
    # ================================================================
    print("\n[1/6] 获取 A 股列表...")
    stock_list = fetcher.get_stock_list()
    total = len(stock_list)
    print(f"  全市场: {total} 只")

    sample_size = 500
    stock_sample = stock_list.sample(n=min(sample_size, total), random_state=42)
    print(f"  采样: {len(stock_sample)} 只")

    # ================================================================
    # 第2步: 下载日线数据
    # ================================================================
    print(f"\n[2/6] 下载日线数据（已缓存的会秒读取）...")
    t0 = time.time()
    all_data = fetcher.get_all_daily_data(stock_sample)
    print(f"  有效数据: {len(all_data)} 只, 耗时 {time.time()-t0:.0f}s")

    if not all_data:
        print("  无有效数据，退出。")
        return

    # ================================================================
    # 第3步: 市场环境判断
    # ================================================================
    print("\n[3/6] 判断当前市场环境...")
    index_df = fetcher.get_index_data()
    market_df = mrf.compute_regime(index_df)

    if not market_df.empty:
        latest = market_df.iloc[-1]
        market_ok = latest["market_ok"]
        dist_count = latest["dist_count"]
        status = "健康（适合买入）" if market_ok else f"转弱（分布日={int(dist_count)}，谨慎操作）"
        print(f"  沪深300 最新状态: {status}")
    else:
        market_ok = True

    # ================================================================
    # 第4步: 趋势模板筛选
    # ================================================================
    print("\n[4/6] 趋势模板筛选（8大条件）...")
    trend_passed = tt.screen(all_data)
    print(f"  通过趋势模板: {len(trend_passed)} / {len(all_data)} 只")

    if trend_passed.empty:
        print("  当前无股票通过趋势模板，市场可能处于弱势期。")
        return

    stock_names = dict(zip(stock_list["code"], stock_list["name"]))

    # ================================================================
    # 第5步: VCP 形态 + 综合评分
    # ================================================================
    print("\n[5/6] VCP 形态检测 + 综合评分...")
    candidates = []

    for _, row in trend_passed.iterrows():
        code = row["code"]
        rs = float(row["rs_rating"])
        df = all_data[code]

        if len(df) < 200:
            continue

        vcp_result = vcp.detect(df)

        close = float(df["close"].iloc[-1])
        high_52w = float(df["high"].iloc[-250:].max()) if len(df) >= 250 else float(df["high"].max())
        low_52w = float(df["low"].iloc[-250:].min()) if len(df) >= 250 else float(df["low"].min())
        ma50 = float(df["close"].iloc[-50:].mean())
        ma200 = float(df["close"].iloc[-200:].mean())

        # 紧密收盘检测
        n = config.vcp.tight_close_days
        recent_closes = df["close"].iloc[-(n + 1):-1].values
        if len(recent_closes) >= n and np.min(recent_closes) > 0:
            tight_spread = (np.max(recent_closes) - np.min(recent_closes)) / np.min(recent_closes)
            tight = tight_spread <= config.vcp.tight_close_range
        else:
            tight = False

        # 成交量趋势
        vol_20 = float(df["volume"].iloc[-20:].mean())
        vol_50 = float(df["volume"].iloc[-50:].mean()) if len(df) >= 50 else vol_20
        vol_ratio = vol_20 / vol_50 if vol_50 > 0 else 1.0

        # 距离枢纽点的距离
        pivot = vcp_result.get("pivot_price", 0)
        if pivot > 0:
            dist_to_pivot = (close - pivot) / pivot
        else:
            pivot = float(df["close"].iloc[-20:].max())
            dist_to_pivot = (close - pivot) / pivot

        # 综合评分
        score = 0
        score += rs * 0.3                                         # RS 权重 30%
        score += (1 if vcp_result["has_vcp"] else 0) * 20        # VCP 形态 20 分
        score += vcp_result.get("num_contractions", 0) * 3       # 收缩次数
        score += (1 if tight else 0) * 10                        # 紧密收盘 10 分
        score += (1 if vcp_result.get("breakout_today") else 0) * 25  # 突破 25 分
        score += max(0, -dist_to_pivot * 100) * 0.5              # 越接近枢纽越高（但不超过枢纽）
        score += (1 if vol_ratio < 0.8 else 0) * 5               # 缩量构建 5 分
        score += (close / high_52w) * 10                          # 接近52周高点 10 分

        candidates.append({
            "code": code,
            "name": stock_names.get(code, "?"),
            "close": close,
            "rs_rating": rs,
            "score": round(score, 1),
            "has_vcp": vcp_result["has_vcp"],
            "contractions": vcp_result.get("num_contractions", 0),
            "pivot": round(pivot, 2),
            "dist_to_pivot": round(dist_to_pivot * 100, 1),
            "breakout": vcp_result.get("breakout_today", False),
            "tight_close": tight,
            "vol_slope": vcp_result.get("vol_slope", 0),
            "ma50": round(ma50, 2),
            "ma200": round(ma200, 2),
            "high_52w": round(high_52w, 2),
            "pct_from_high": round((close / high_52w - 1) * 100, 1),
            "vol_ratio": round(vol_ratio, 2),
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    # ================================================================
    # 第6步: 输出 Top 20
    # ================================================================
    top_n = 20
    top = candidates[:top_n]

    print(f"\n{'=' * 70}")
    print(f"  Top {top_n} 潜力股（综合评分排序）")
    print(f"  筛选范围: {len(all_data)} 只 → 趋势通过 {len(trend_passed)} 只 → 评分排序")
    print(f"{'=' * 70}\n")

    header = (f"  {'#':>2}  {'代码':>8}  {'名称':<8}  {'价格':>8}  {'RS':>3}  "
              f"{'评分':>5}  {'VCP':>3}  {'收缩':>2}  {'枢纽':>8}  {'距枢纽':>6}  "
              f"{'突破':>2}  {'紧密':>2}  {'缩量':>4}  {'离高点':>6}")
    print(header)
    print("  " + "-" * 100)

    for i, c in enumerate(top, 1):
        vcp_flag = "Y" if c["has_vcp"] else "-"
        bo_flag = "!!!" if c["breakout"] else ("-" if c["dist_to_pivot"] < -5 else "~")
        tight_flag = "Y" if c["tight_close"] else "-"
        print(
            f"  {i:>2}  {c['code']:>8}  {c['name']:<8}  {c['close']:>8.2f}  "
            f"{c['rs_rating']:>3.0f}  {c['score']:>5.1f}  {vcp_flag:>3}  "
            f"{c['contractions']:>2}  {c['pivot']:>8.2f}  {c['dist_to_pivot']:>5.1f}%  "
            f"{bo_flag:>3}  {tight_flag:>2}  {c['vol_ratio']:>4.2f}  "
            f"{c['pct_from_high']:>5.1f}%"
        )

    # 详细分析
    print(f"\n{'=' * 70}")
    print(f"  详细分析")
    print(f"{'=' * 70}")

    for i, c in enumerate(top[:10], 1):
        print(f"\n  [{i}] {c['code']} {c['name']}  综合评分: {c['score']}")
        print(f"      价格: {c['close']}  |  MA50: {c['ma50']}  |  MA200: {c['ma200']}")
        print(f"      RS评级: {c['rs_rating']:.0f}  |  52周高点: {c['high_52w']}  |  距高点: {c['pct_from_high']}%")
        print(f"      VCP形态: {'有' if c['has_vcp'] else '无'}  |  收缩{c['contractions']}次  |  波动率斜率: {c['vol_slope']:.4f}")
        print(f"      枢纽点: {c['pivot']}  |  距枢纽: {c['dist_to_pivot']}%  |  突破: {'是' if c['breakout'] else '否'}")
        print(f"      紧密收盘: {'是' if c['tight_close'] else '否'}  |  量比(20/50): {c['vol_ratio']}")

        signals = []
        if c["breakout"]:
            signals.append("VCP突破确认，可考虑入场")
        elif c["dist_to_pivot"] > -3:
            signals.append("接近枢纽点，关注放量突破")
        if c["tight_close"]:
            signals.append("紧密收盘，供需平衡")
        if c["vol_ratio"] < 0.7:
            signals.append("成交量萎缩，基底构建中")
        if c["rs_rating"] >= 90:
            signals.append("RS极强，领涨股")
        if c["pct_from_high"] > -10:
            signals.append("接近52周新高")

        if signals:
            print(f"      >>> {'  |  '.join(signals)}")

    # 操作建议
    print(f"\n{'=' * 70}")
    print(f"  操作建议")
    print(f"{'=' * 70}")

    if not market_ok:
        print("\n  [警告] 当前大盘环境偏弱，Minervini 建议减少仓位或暂停买入。")
        print("  即使个股形态良好，也应控制总仓位不超过 30%。")
    else:
        print("\n  当前大盘环境健康，可正常执行选股策略。")

    breakouts = [c for c in top if c["breakout"]]
    near_pivot = [c for c in top if not c["breakout"] and c["dist_to_pivot"] > -5]
    building = [c for c in top if c["has_vcp"] and c["dist_to_pivot"] <= -5]

    if breakouts:
        print(f"\n  [突破型] 以下股票已突破枢纽点，优先关注:")
        for c in breakouts:
            print(f"    - {c['code']} {c['name']}: 突破 {c['pivot']}，放量确认")

    if near_pivot:
        print(f"\n  [待突破] 以下股票接近枢纽点（5%以内），设置价格预警:")
        for c in near_pivot:
            print(f"    - {c['code']} {c['name']}: 枢纽 {c['pivot']}，当前距离 {c['dist_to_pivot']}%")

    if building:
        print(f"\n  [基底构建] 以下股票仍在收缩，持续跟踪:")
        for c in building[:5]:
            print(f"    - {c['code']} {c['name']}: 收缩{c['contractions']}次，等待右侧信号")

    print(f"\n  止损建议: 入场后设 8% 硬止损，单笔风险不超过总资金 1%")
    print(f"  仓位建议: 最多同时持有 6-8 只，分批建仓")
    print()


if __name__ == "__main__":
    main()
