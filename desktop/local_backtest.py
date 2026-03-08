"""
客户端本地回测引擎
纯 SQLite + numpy，不依赖 Streamlit/akshare。
"""
import os
import sqlite3
import numpy as np
from dataclasses import dataclass, field

DB_PATH = os.path.join("data_cache", "quant.db")


@dataclass
class LocalBacktestResult:
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_hold_days: float = 0.0
    max_consecutive_losses: int = 0
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)


def run_local_backtest(
    strategy: str = "trend",
    sample_size: int = 100,
    start_date: str = "2022-06-01",
    initial_capital: float = 1_000_000,
    stop_loss_pct: float = 0.08,
    max_positions: int = 5,
    progress_callback=None,
) -> LocalBacktestResult:
    """
    纯本地回测：从 SQLite 读日线数据，模拟买卖。
    strategy: trend / breakout / value / momentum
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)

    # 获取有足够数据的股票
    cur = conn.execute(
        "SELECT DISTINCT code FROM daily_kline GROUP BY code HAVING COUNT(*) >= 200"
    )
    all_codes = [r[0] for r in cur.fetchall()]
    if not all_codes:
        conn.close()
        return LocalBacktestResult()

    rng = np.random.RandomState(2024)
    codes = list(rng.choice(all_codes, size=min(sample_size, len(all_codes)), replace=False))

    # 加载所有日线数据
    stock_data = {}
    for i, code in enumerate(codes):
        if progress_callback and i % 20 == 0:
            progress_callback(i / len(codes) * 0.3, f"加载数据 {i}/{len(codes)}")
        cur = conn.execute(
            "SELECT date, open, high, low, close, volume FROM daily_kline WHERE code=? AND date>=? ORDER BY date",
            (code, start_date),
        )
        rows = cur.fetchall()
        if len(rows) >= 60:
            stock_data[code] = rows

    conn.close()

    if not stock_data:
        return LocalBacktestResult()

    # 构建统一日期序列
    all_dates = sorted({r[0] for rows in stock_data.values() for r in rows})
    if not all_dates:
        return LocalBacktestResult()

    # 回测主循环
    cash = initial_capital
    positions = {}  # {code: {entry_price, shares, entry_date, entry_idx, highest}}
    trades = []
    equity_curve = []
    pending_buys = []

    for day_idx, date_str in enumerate(all_dates):
        if progress_callback and day_idx % 50 == 0:
            progress_callback(0.3 + day_idx / len(all_dates) * 0.6, f"回测中 {date_str}")

        # 执行挂单买入 (T+1)
        for buy in pending_buys:
            code = buy["code"]
            if code in positions or code not in stock_data:
                continue
            day_data = _get_day(stock_data[code], date_str)
            if not day_data:
                continue
            entry_price = day_data[1] * 1.001  # open + 滑点
            shares = int(cash * 0.15 / entry_price / 100) * 100
            if shares < 100:
                continue
            cost = entry_price * shares * 1.0003
            if cost > cash:
                continue
            cash -= cost
            positions[code] = {
                "entry_price": entry_price, "shares": shares,
                "entry_date": date_str, "entry_idx": day_idx,
                "highest": entry_price,
            }
        pending_buys.clear()

        # 检查卖出
        codes_to_remove = []
        for code, pos in positions.items():
            day_data = _get_day(stock_data[code], date_str)
            if not day_data:
                continue
            close = day_data[4]
            high = day_data[2]
            pos["highest"] = max(pos["highest"], high)
            entry = pos["entry_price"]
            hold_days = day_idx - pos["entry_idx"]
            profit_pct = (close - entry) / entry

            sell = False
            reason = ""
            if close <= entry * (1 - stop_loss_pct):
                sell, reason = True, "止损"
            elif profit_pct >= 0.20 and (pos["highest"] - close) / pos["highest"] >= 0.10:
                sell, reason = True, "止盈回撤"
            elif hold_days >= 20 and profit_pct < 0.02:
                sell, reason = True, "时间止损"
            elif close < _get_ma(stock_data[code], date_str, 50):
                sell, reason = True, "跌破MA50"

            if sell:
                sell_price = close * 0.999
                revenue = sell_price * pos["shares"]
                commission = revenue * 0.0003
                tax = revenue * 0.001
                net = revenue - commission - tax
                pnl = net - entry * pos["shares"]
                trades.append({
                    "code": code, "entry_date": pos["entry_date"],
                    "entry_price": round(entry, 2),
                    "exit_date": date_str, "exit_price": round(sell_price, 2),
                    "shares": pos["shares"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl / (entry * pos["shares"]), 4),
                    "hold_days": hold_days, "reason": reason,
                })
                cash += net
                codes_to_remove.append(code)

        for code in codes_to_remove:
            positions.pop(code, None)

        # 寻找买入信号
        if len(positions) + len(pending_buys) < max_positions:
            candidates = []
            for code, rows in stock_data.items():
                if code in positions:
                    continue
                day_data = _get_day(rows, date_str)
                if not day_data:
                    continue
                score = _compute_buy_score(rows, date_str, strategy)
                if score > 0:
                    candidates.append((code, score))

            candidates.sort(key=lambda x: x[1], reverse=True)
            slots = max_positions - len(positions) - len(pending_buys)
            for code, score in candidates[:slots]:
                pending_buys.append({"code": code})

        # 记录权益
        pos_value = 0
        for code, pos in positions.items():
            day_data = _get_day(stock_data[code], date_str)
            if day_data:
                pos_value += day_data[4] * pos["shares"]
            else:
                pos_value += pos["entry_price"] * pos["shares"]
        equity_curve.append({"date": date_str, "equity": cash + pos_value})

    if progress_callback:
        progress_callback(0.95, "计算指标...")

    return _compute_metrics(trades, equity_curve, initial_capital)


def _get_day(rows, date_str):
    for r in rows:
        if r[0] == date_str:
            return r
    return None


def _get_ma(rows, date_str, period):
    closes = []
    for r in rows:
        if r[0] <= date_str:
            closes.append(r[4])
    if len(closes) >= period:
        return float(np.mean(closes[-period:]))
    return 0.0


def _compute_buy_score(rows, date_str, strategy):
    closes = [r[4] for r in rows if r[0] <= date_str]
    highs = [r[2] for r in rows if r[0] <= date_str]
    volumes = [r[5] for r in rows if r[0] <= date_str]
    n = len(closes)
    if n < 60:
        return 0

    price = closes[-1]
    ma50 = float(np.mean(closes[-50:]))
    ma150 = float(np.mean(closes[-150:])) if n >= 150 else ma50
    ma200 = float(np.mean(closes[-200:])) if n >= 200 else ma150

    if strategy == "trend":
        if price <= ma50 or ma50 <= ma150:
            return 0
        high20 = max(closes[-21:-1]) if n >= 21 else price
        if price < high20 * 0.98:
            return 0
        vol_recent = np.std(closes[-20:]) / max(np.mean(closes[-20:]), 1e-6)
        vol_early = np.std(closes[-40:-20]) / max(np.mean(closes[-40:-20]), 1e-6) if n >= 40 else vol_recent
        score = 50
        if n >= 200 and ma50 > ma150 > ma200:
            score += 20
        if vol_recent < vol_early * 0.8:
            score += 15
        if price >= high20:
            score += 15
        return score

    elif strategy == "breakout":
        if n < 55:
            return 0
        high55 = max(closes[-56:-1])
        if price < high55:
            return 0
        vol_ma = float(np.mean(volumes[-50:])) if n >= 50 else 1
        vol_today = volumes[-1]
        if vol_ma > 0 and vol_today > vol_ma * 1.5:
            return 60 + (price / high55 - 1) * 100
        return 0

    elif strategy == "value":
        if price > ma200 * 0.9:
            return 0
        mom60 = (price / closes[-61] - 1) if n >= 61 and closes[-61] > 0 else 0
        if mom60 > -0.1:
            return 0
        return 50 + abs(mom60) * 100

    elif strategy == "momentum":
        if price <= ma50:
            return 0
        mom20 = (price / closes[-21] - 1) if n >= 21 and closes[-21] > 0 else 0
        if mom20 < 0.03:
            return 0
        return 50 + mom20 * 200

    return 0


def _compute_metrics(trades, equity_curve, initial_capital):
    result = LocalBacktestResult()
    result.trades = trades
    result.equity_curve = equity_curve

    if not equity_curve:
        return result

    final = equity_curve[-1]["equity"]
    result.total_return = (final - initial_capital) / initial_capital

    days = len(equity_curve)
    if days > 0:
        result.annual_return = (1 + result.total_return) ** (250 / max(days, 1)) - 1

    equities = np.array([e["equity"] for e in equity_curve])
    peak = np.maximum.accumulate(equities)
    dd = (peak - equities) / np.maximum(peak, 1)
    result.max_drawdown = float(np.max(dd)) if len(dd) > 0 else 0

    if len(equities) > 1:
        daily_ret = np.diff(equities) / equities[:-1]
        if np.std(daily_ret) > 0:
            result.sharpe_ratio = round(
                (np.mean(daily_ret) - 0.03 / 250) / np.std(daily_ret) * np.sqrt(250), 2
            )

    result.total_trades = len(trades)
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    result.winning_trades = len(winning)
    result.losing_trades = len(losing)
    if result.total_trades > 0:
        result.win_rate = result.winning_trades / result.total_trades
        result.avg_hold_days = np.mean([t["hold_days"] for t in trades])
    avg_win = np.mean([t["pnl"] for t in winning]) if winning else 0
    avg_loss = abs(np.mean([t["pnl"] for t in losing])) if losing else 1
    result.profit_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    streak = 0
    max_streak = 0
    for t in trades:
        if t["pnl"] <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    result.max_consecutive_losses = max_streak

    return result


def run_monte_carlo(base_result: LocalBacktestResult, n_sim: int = 1000) -> dict:
    """
    蒙特卡洛模拟：对交易记录做随机重采样，统计收益分布。
    """
    trades = base_result.trades
    if len(trades) < 5:
        return {"error": "交易笔数不足（至少需要5笔）"}

    pnl_pcts = [t.get("pnl_pct", 0) for t in trades]
    n_trades = len(pnl_pcts)
    actual_return = base_result.total_return
    actual_sharpe = base_result.sharpe_ratio
    actual_mdd = base_result.max_drawdown

    sim_returns = []
    sim_sharpes = []
    sim_mdds = []

    for _ in range(n_sim):
        sampled = np.random.choice(pnl_pcts, size=n_trades, replace=True)
        equity = [1.0]
        for p in sampled:
            equity.append(equity[-1] * (1 + p))
        eq = np.array(equity)
        sim_ret = eq[-1] / eq[0] - 1
        sim_returns.append(sim_ret)

        peak = np.maximum.accumulate(eq)
        dd = (peak - eq) / np.maximum(peak, 1e-9)
        sim_mdds.append(float(np.max(dd)))

        daily_r = np.diff(eq) / eq[:-1]
        if np.std(daily_r) > 0:
            sim_sharpes.append(float(np.mean(daily_r) / np.std(daily_r) * np.sqrt(250)))
        else:
            sim_sharpes.append(0)

    sim_returns = np.array(sim_returns)
    sim_sharpes = np.array(sim_sharpes)
    sim_mdds = np.array(sim_mdds)

    def _rank(actual, arr):
        return round(float(np.sum(arr <= actual) / len(arr) * 100), 1)

    metrics = [
        {
            "name": "总收益率",
            "actual": f"{actual_return:.2%}",
            "sim_mean": f"{np.mean(sim_returns):.2%}",
            "p5": f"{np.percentile(sim_returns, 5):.2%}",
            "p95": f"{np.percentile(sim_returns, 95):.2%}",
            "rank": f"{_rank(actual_return, sim_returns):.0f}%",
        },
        {
            "name": "夏普比率",
            "actual": f"{actual_sharpe:.2f}",
            "sim_mean": f"{np.mean(sim_sharpes):.2f}",
            "p5": f"{np.percentile(sim_sharpes, 5):.2f}",
            "p95": f"{np.percentile(sim_sharpes, 95):.2f}",
            "rank": f"{_rank(actual_sharpe, sim_sharpes):.0f}%",
        },
        {
            "name": "最大回撤",
            "actual": f"{actual_mdd:.2%}",
            "sim_mean": f"{np.mean(sim_mdds):.2%}",
            "p5": f"{np.percentile(sim_mdds, 5):.2%}",
            "p95": f"{np.percentile(sim_mdds, 95):.2%}",
            "rank": f"{_rank(actual_mdd, sim_mdds):.0f}%",
        },
        {
            "name": "胜率",
            "actual": f"{base_result.win_rate:.1%}",
            "sim_mean": f"{np.mean([np.mean(np.random.choice(pnl_pcts, n_trades, True) > 0) for _ in range(200)]):.1%}" if n_trades > 0 else "-",
            "p5": "-", "p95": "-",
            "rank": "-",
        },
    ]

    rank_return = _rank(actual_return, sim_returns)
    if rank_return >= 70:
        grade = f"🟢 优秀（超越 {rank_return:.0f}% 模拟路径）"
    elif rank_return >= 40:
        grade = f"🔵 合格（超越 {rank_return:.0f}% 模拟路径）"
    else:
        grade = f"🔴 较弱（仅超越 {rank_return:.0f}% 模拟路径，策略可能过拟合）"

    return {"metrics": metrics, "grade": grade}


def run_walk_forward(strategy: str = "trend", sample_size: int = 200,
                     n_windows: int = 4, train_ratio: float = 0.7) -> dict:
    """
    Walk-Forward 分析：将数据分为多个窗口，训练期 + 验证期，检验策略稳定性。
    """
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cur = conn.execute("""
        SELECT DISTINCT code FROM daily_kline
        GROUP BY code HAVING COUNT(*) >= 200
        ORDER BY RANDOM() LIMIT ?
    """, (sample_size,))
    codes = [r[0] for r in cur.fetchall()]

    all_dates = set()
    for code in codes[:50]:
        cur2 = conn.execute("SELECT DISTINCT date FROM daily_kline WHERE code=?", (code,))
        for r in cur2.fetchall():
            all_dates.add(r[0])
    conn.close()

    sorted_dates = sorted(all_dates)
    if len(sorted_dates) < 120:
        return {"error": "数据日期不足（至少需要120个交易日）", "windows": []}

    total_days = len(sorted_dates)
    window_size = total_days // n_windows
    if window_size < 30:
        n_windows = max(2, total_days // 60)
        window_size = total_days // n_windows

    windows = []
    for w in range(n_windows):
        start_idx = w * window_size
        end_idx = min(start_idx + window_size, total_days)
        split_idx = start_idx + int((end_idx - start_idx) * train_ratio)

        train_start = sorted_dates[start_idx]
        train_end = sorted_dates[min(split_idx, total_days - 1)]
        val_start = sorted_dates[min(split_idx + 1, total_days - 1)]
        val_end = sorted_dates[min(end_idx - 1, total_days - 1)]

        train_result = run_local_backtest(strategy, min(sample_size, 80), train_start)
        val_result = run_local_backtest(strategy, min(sample_size, 80), val_start)

        train_ret = train_result.total_return
        val_ret = val_result.total_return
        decay = 0
        if abs(train_ret) > 0.001:
            decay = round((1 - val_ret / train_ret) * 100, 1) if train_ret != 0 else 0

        windows.append({
            "window": f"W{w + 1}",
            "train_period": f"{train_start}~{train_end}",
            "val_period": f"{val_start}~{val_end}",
            "train_return": f"{train_ret:.2%}",
            "train_sharpe": f"{train_result.sharpe_ratio:.2f}",
            "train_winrate": f"{train_result.win_rate:.1%}",
            "val_return": f"{val_ret:.2%}",
            "val_sharpe": f"{val_result.sharpe_ratio:.2f}",
            "val_winrate": f"{val_result.win_rate:.1%}",
            "val_mdd": f"{val_result.max_drawdown:.2%}",
            "decay": f"{decay:+.1f}%",
        })

    avg_decay = np.mean([
        float(w["decay"].replace("%", "").replace("+", "")) for w in windows
    ]) if windows else 0

    if avg_decay < 20:
        summary = f"🟢 策略稳定（平均衰减 {avg_decay:.1f}%，训练→验证一致性好）"
    elif avg_decay < 50:
        summary = f"🔵 策略可用（平均衰减 {avg_decay:.1f}%，有一定过拟合风险）"
    else:
        summary = f"🔴 过拟合风险高（平均衰减 {avg_decay:.1f}%，策略需要优化）"

    return {"windows": windows, "summary": summary}


def run_multi_strategy_backtest(
    strategies: list[str] = None,
    sample_size: int = 150,
    start_date: str = "2022-06-01",
) -> dict:
    """
    多策略同时回测并对比。
    返回每个策略的指标 + 综合排名。
    """
    if not strategies:
        strategies = ["trend", "breakout", "value", "momentum"]

    results = {}
    for sid in strategies:
        try:
            r = run_local_backtest(
                strategy=sid, sample_size=sample_size,
                start_date=start_date, max_positions=5,
            )
            results[sid] = {
                "total_return": r.total_return,
                "annual_return": r.annual_return,
                "max_drawdown": r.max_drawdown,
                "sharpe_ratio": r.sharpe_ratio,
                "win_rate": r.win_rate,
                "profit_loss_ratio": r.profit_loss_ratio,
                "total_trades": r.total_trades,
                "avg_hold_days": r.avg_hold_days,
                "max_consecutive_losses": r.max_consecutive_losses,
                "trades": r.trades,
                "equity_curve": r.equity_curve,
            }
        except Exception as e:
            results[sid] = {"error": str(e)}

    # 排名
    valid = {k: v for k, v in results.items() if "error" not in v and v.get("total_trades", 0) > 0}
    if valid:
        rank_return = sorted(valid.keys(), key=lambda k: valid[k]["total_return"], reverse=True)
        rank_sharpe = sorted(valid.keys(), key=lambda k: valid[k]["sharpe_ratio"], reverse=True)
        rank_winrate = sorted(valid.keys(), key=lambda k: valid[k]["win_rate"], reverse=True)
        rank_mdd = sorted(valid.keys(), key=lambda k: valid[k]["max_drawdown"])

        for sid in valid:
            results[sid]["rank_return"] = rank_return.index(sid) + 1
            results[sid]["rank_sharpe"] = rank_sharpe.index(sid) + 1
            results[sid]["rank_winrate"] = rank_winrate.index(sid) + 1
            results[sid]["rank_mdd"] = rank_mdd.index(sid) + 1
            results[sid]["avg_rank"] = round(np.mean([
                results[sid]["rank_return"], results[sid]["rank_sharpe"],
                results[sid]["rank_winrate"], results[sid]["rank_mdd"],
            ]), 1)

        best = min(valid.keys(), key=lambda k: results[k]["avg_rank"])
        results["_best"] = best
        results["_summary"] = (
            f"最优策略: {best}（综合排名 {results[best]['avg_rank']:.1f}，"
            f"收益 {results[best]['total_return']:.2%}，夏普 {results[best]['sharpe_ratio']:.2f}）"
        )

    return results
