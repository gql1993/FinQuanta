"""
板块轮动 + 离线策略评估工具。

系统不再维护「主策略」：19 种策略在竞技场平行赛跑，选股雷达由 UI 手动/多策略扫描，
或可选 daemon 多策略扫描（FINQUANTA_DAEMON_AUTO_SCAN=1）。
"""
import os
import json
import logging
import numpy as np
from datetime import datetime, date

from desktop.strategy_engine import build_context, score_candidate
from desktop.data_access import RepoCompatConnection

_log = logging.getLogger("strategy_rotator")

ALL_STRATEGIES = [
    "sepa", "canslim", "turtle", "graham",
    "buffett", "lynch", "domestic_trend", "domestic_value",
]

STRATEGY_NAMES = {
    "sepa": "SEPA(股票魔法师)", "canslim": "CANSLIM",
    "turtle": "海龟交易法", "graham": "格雷厄姆(价值)",
    "buffett": "巴菲特(品质)", "lynch": "彼得林奇(动量)",
    "domestic_trend": "国内趋势", "domestic_value": "国内价值",
}


def run_all_strategies_scan(sample: int = 300) -> dict:
    """
    对每种策略执行一次扫描，返回各策略的候选数量和 Top10。
    复用 daemon_scheduler 的扫描逻辑。
    """
    conn = RepoCompatConnection()
    cur = conn.execute(
        "SELECT code, COUNT(*) FROM daily_kline GROUP BY code "
        "HAVING COUNT(*) >= 50 ORDER BY COUNT(*) DESC LIMIT ?",
        (sample,),
    )
    codes = [r[0] for r in cur.fetchall()]

    names = {}
    try:
        names = {r[0]: r[1] for r in conn.execute("SELECT code, name FROM stock_list").fetchall()}
    except Exception:
        pass

    # 预加载所有数据（避免重复查询）
    stock_data = {}
    for code in codes:
        rows = conn.execute(
            "SELECT close, high, low, volume FROM daily_kline "
            "WHERE code=? ORDER BY date DESC LIMIT 260",
            (code,),
        ).fetchall()
        if len(rows) >= 50:
            rows = rows[::-1]
            stock_data[code] = {
                "closes": np.array([r[0] for r in rows]),
                "highs": np.array([r[1] for r in rows]),
                "lows": np.array([r[2] for r in rows]),
                "vols": np.array([r[3] for r in rows]),
            }
    conn.close()

    results = {}
    for sid in ALL_STRATEGIES:
        candidates = _score_strategy(sid, stock_data, names)
        candidates.sort(key=lambda x: x["score"], reverse=True)
        results[sid] = {
            "total": len(candidates),
            "top10": candidates[:10],
            "avg_score": round(np.mean([c["score"] for c in candidates]), 1) if candidates else 0,
        }
    return results


def _score_strategy(sid: str, stock_data: dict, names: dict) -> list:
    """对单一策略评分，返回候选列表。"""
    candidates = []
    for code, d in stock_data.items():
        closes = d["closes"]
        highs = d["highs"]
        lows = d["lows"]
        vols = d["vols"]
        n = len(closes)
        price = float(closes[-1])
        if price <= 0:
            continue

        ctx = build_context(code, closes, highs, lows, vols)
        scored = score_candidate(sid, ctx)
        score = scored["score"]
        if score >= 40:
            candidates.append({
                "code": code,
                "name": names.get(code, code),
                "score": score,
                "signals": scored["signals"],
                "strategy": scored["strategy"],
            })
    return candidates


def get_strategy_performance() -> dict:
    """从走势验证历史统计各策略的准确率和收益。"""
    conn = RepoCompatConnection()
    perf = {}
    for sid in ALL_STRATEGIES:
        rows = conn.execute(
            "SELECT correct, pnl_5d FROM trend_verify WHERE strategy=? AND correct>=0",
            (sid.upper(),),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                "SELECT correct, pnl_5d FROM trend_verify WHERE strategy=? AND correct>=0",
                (sid,),
            ).fetchall()
        total = len(rows)
        wins = sum(1 for r in rows if r[0] == 1)
        pnl5_list = [r[1] for r in rows if r[1] is not None]
        perf[sid] = {
            "total": total,
            "accuracy": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_pnl_5d": round(np.mean(pnl5_list), 2) if pnl5_list else 0,
        }
    conn.close()
    return perf


def evaluate_rotation() -> dict:
    """
    执行策略轮动评估：
    1. 扫描全部策略
    2. 获取历史表现
    3. 综合评分
    4. 选出最强策略
    """
    _log.info("evaluating strategy rotation...")

    scan_results = run_all_strategies_scan(300)
    perf = get_strategy_performance()

    rankings = []
    for sid in ALL_STRATEGIES:
        sr = scan_results.get(sid, {})
        sp = perf.get(sid, {})

        n_candidates = sr.get("total", 0)
        accuracy = sp.get("accuracy", 0)
        avg_pnl = sp.get("avg_pnl_5d", 0)
        sample_count = sp.get("total", 0)

        # 综合评分（准确率主导，候选数量为辅，样本不足打折）
        # 核心原则：准确率 0% 的策略不应排第一
        sample_confidence = min(1.0, sample_count / 10)  # 样本<10时降权
        accuracy_score = accuracy / 100 * 50 * sample_confidence  # 准确率占50分
        pnl_score = max(0, min(avg_pnl, 10)) / 10 * 30 * sample_confidence  # 收益占30分
        candidate_score = min(n_candidates, 50) / 50 * 20  # 候选数量仅占20分

        # 准确率为0时，总分封顶20分（只有候选数量分）
        if accuracy <= 0 and sample_count > 0:
            composite = candidate_score * 0.5  # 准确率0%再打5折
        elif sample_count == 0:
            composite = candidate_score * 0.3  # 无样本，候选分打3折
        else:
            composite = accuracy_score + pnl_score + candidate_score

        rankings.append({
            "strategy": sid,
            "name": STRATEGY_NAMES.get(sid, sid),
            "candidates": n_candidates,
            "accuracy": accuracy,
            "avg_pnl_5d": avg_pnl,
            "composite_score": round(composite, 1),
            "top3": [c["code"] for c in sr.get("top10", [])[:3]],
        })

    rankings.sort(key=lambda x: x["composite_score"], reverse=True)

    best = rankings[0] if rankings else None
    result = {
        "rankings": rankings,
        "best_strategy": best["strategy"] if best else "sepa",
        "best_name": best["name"] if best else "SEPA",
        "best_score": best["composite_score"] if best else 0,
        "timestamp": datetime.now().isoformat(),
    }

    # 保存到 kv_store
    conn = RepoCompatConnection()
    conn.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
        ("strategy_rotation", json.dumps(result, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    _log.info(f"rotation result: best={result['best_name']}({result['best_score']:.1f})")
    return result


def evaluate_sector_rotation() -> dict:
    """
    板块轮动：分析各板块近期表现，识别最强板块。
    使用板块成分股的平均涨幅排名。
    """
    _log.info("evaluating sector rotation...")
    conn = RepoCompatConnection()

    # 获取所有板块
    boards = conn.execute(
        "SELECT board, COUNT(*) FROM board_stocks GROUP BY board HAVING COUNT(*) >= 5"
    ).fetchall()

    sector_perf = []
    for board_name, n_stocks in boards:
        codes = [r[0] for r in conn.execute(
            "SELECT code FROM board_stocks WHERE board=? LIMIT 30", (board_name,)
        ).fetchall()]

        pct_5d_list = []
        pct_20d_list = []
        for code in codes:
            rows = conn.execute(
                "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 25",
                (code,),
            ).fetchall()
            if len(rows) >= 6:
                pct5 = (rows[0][0] / rows[5][0] - 1) * 100 if rows[5][0] > 0 else 0
                pct_5d_list.append(pct5)
            if len(rows) >= 21:
                pct20 = (rows[0][0] / rows[20][0] - 1) * 100 if rows[20][0] > 0 else 0
                pct_20d_list.append(pct20)

        if pct_5d_list:
            avg_5d = round(float(np.mean(pct_5d_list)), 2)
            avg_20d = round(float(np.mean(pct_20d_list)), 2) if pct_20d_list else 0
            # 综合得分 = 5日涨幅×0.6 + 20日涨幅×0.4
            composite = avg_5d * 0.6 + avg_20d * 0.4
            sector_perf.append({
                "board": board_name,
                "n_stocks": n_stocks,
                "avg_5d": avg_5d,
                "avg_20d": avg_20d,
                "composite": round(composite, 2),
            })

    conn.close()

    sector_perf.sort(key=lambda x: x["composite"], reverse=True)

    result = {
        "rankings": sector_perf,
        "top3": [s["board"] for s in sector_perf[:3]],
        "bottom3": [s["board"] for s in sector_perf[-3:]],
        "timestamp": datetime.now().isoformat(),
    }

    # 保存
    conn = RepoCompatConnection()
    conn.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
        ("sector_rotation", json.dumps(result, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    top = sector_perf[:3] if sector_perf else []
    _log.info(f"sector rotation: top3={[s['board'] for s in top]}")
    return result
